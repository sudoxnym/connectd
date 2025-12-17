#!/usr/bin/env python3
"""
connectd daemon - continuous discovery and matchmaking
REWIRED TO USE CENTRAL DATABASE
"""

import time
import json
import signal
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from db import Database
from db.users import (init_users_table, get_priority_users, save_priority_match,
                      get_priority_user_matches, discover_host_user, mark_match_viewed)
from scoutd import scrape_github, scrape_reddit, scrape_mastodon, scrape_lobsters, scrape_lemmy, scrape_discord
from scoutd.forges import scrape_all_forges
from config import HOST_USER
from scoutd.github import analyze_github_user, get_github_user
from scoutd.signals import analyze_text
from matchd.fingerprint import generate_fingerprint, fingerprint_similarity
from matchd.overlap import find_overlap
from matchd.lost import find_matches_for_lost_builders
from introd.draft import draft_intro, summarize_human, summarize_overlap
from introd.lost_intro import draft_lost_intro, get_lost_intro_config
from introd.send import send_email
from introd.deliver import deliver_intro, determine_best_contact
from config import get_lost_config
from api import start_api_thread, update_daemon_state
from central_client import CentralClient, get_client


class DummyDb:
    """dummy db that does nothing - scrapers save here but we push to central"""
    def save_human(self, human): pass
    def save_match(self, *args, **kwargs): pass
    def get_human(self, *args, **kwargs): return None
    def close(self): pass


# daemon config
SCOUT_INTERVAL = 3600 * 4      # full scout every 4 hours
MATCH_INTERVAL = 3600          # check matches every hour
INTRO_INTERVAL = 3600 * 2      # send intros every 2 hours
LOST_INTERVAL = 3600 * 6       # lost builder outreach every 6 hours
from config import MAX_INTROS_PER_DAY

MIN_OVERLAP_PRIORITY = 30
MIN_OVERLAP_STRANGERS = 50


class ConnectDaemon:
    def __init__(self, dry_run=False):
        # local db only for priority_users (host-specific)
        self.local_db = Database()
        init_users_table(self.local_db.conn)

        # CENTRAL for all humans/matches
        self.central = get_client()
        if not self.central:
            raise RuntimeError("CENTRAL API REQUIRED - set CONNECTD_API_KEY and CONNECTD_CENTRAL_API")

        self.log("connected to CENTRAL database")

        self.running = True
        self.dry_run = dry_run
        self.started_at = datetime.now()
        self.last_scout = None
        self.last_match = None
        self.last_intro = None
        self.last_lost = None
        self.intros_today = 0
        self.lost_intros_today = 0
        self.today = datetime.now().date()

        # register instance
        instance_id = os.environ.get('CONNECTD_INSTANCE_ID', 'daemon')
        self.central.register_instance(instance_id, os.environ.get('CONNECTD_INSTANCE_IP', 'unknown'))

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        if HOST_USER:
            self.log(f"HOST_USER set: {HOST_USER}")
            discover_host_user(self.local_db.conn, HOST_USER)

        self._update_api_state()

    def _shutdown(self, signum, frame):
        print("\nconnectd: shutting down...")
        self.running = False
        self._update_api_state()

    def _update_api_state(self):
        now = datetime.now()

        def secs_until(last, interval):
            base = last if last else self.started_at
            next_run = base + timedelta(seconds=interval)
            remaining = (next_run - now).total_seconds()
            return max(0, int(remaining))

        update_daemon_state({
            'running': self.running,
            'dry_run': self.dry_run,
            'last_scout': self.last_scout.isoformat() if self.last_scout else None,
            'last_match': self.last_match.isoformat() if self.last_match else None,
            'last_intro': self.last_intro.isoformat() if self.last_intro else None,
            'last_lost': self.last_lost.isoformat() if self.last_lost else None,
            'intros_today': self.intros_today,
            'lost_intros_today': self.lost_intros_today,
            'started_at': self.started_at.isoformat(),
            'countdown_scout': secs_until(self.last_scout, SCOUT_INTERVAL),
            'countdown_match': secs_until(self.last_match, MATCH_INTERVAL),
            'countdown_intro': secs_until(self.last_intro, INTRO_INTERVAL),
            'countdown_lost': secs_until(self.last_lost, LOST_INTERVAL),
        })

    def log(self, msg):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def reset_daily_limits(self):
        if datetime.now().date() != self.today:
            self.today = datetime.now().date()
            self.intros_today = 0
            self.lost_intros_today = 0
            self.log("reset daily intro limits")

    def scout_cycle(self):
        """run discovery - scrape to CENTRAL"""
        self.log("starting scout cycle (-> CENTRAL)...")

        # dummy db - scrapers save here but we push to central
        dummy_db = DummyDb()
        scraped_humans = []

        try:
            # github - returns list of humans
            from scoutd.github import scrape_github
            gh_humans = scrape_github(dummy_db, limit_per_source=30)
            if gh_humans:
                scraped_humans.extend(gh_humans)
            self.log(f"  github: {len(gh_humans) if gh_humans else 0} humans")
        except Exception as e:
            self.log(f"github scout error: {e}")

        try:
            from scoutd.reddit import scrape_reddit
            reddit_humans = scrape_reddit(dummy_db, limit_per_sub=30)
            if reddit_humans:
                scraped_humans.extend(reddit_humans)
            self.log(f"  reddit: {len(reddit_humans) if reddit_humans else 0} humans")
        except Exception as e:
            self.log(f"reddit scout error: {e}")

        try:
            from scoutd.mastodon import scrape_mastodon
            masto_humans = scrape_mastodon(dummy_db, limit_per_instance=30)
            if masto_humans:
                scraped_humans.extend(masto_humans)
            self.log(f"  mastodon: {len(masto_humans) if masto_humans else 0} humans")
        except Exception as e:
            self.log(f"mastodon scout error: {e}")

        try:
            forge_humans = scrape_all_forges(limit_per_instance=30)
            if forge_humans:
                scraped_humans.extend(forge_humans)
            self.log(f"  forges: {len(forge_humans) if forge_humans else 0} humans")
        except Exception as e:
            self.log(f"forge scout error: {e}")

        try:
            from scoutd.lobsters import scrape_lobsters
            lob_humans = scrape_lobsters(dummy_db)
            if lob_humans:
                scraped_humans.extend(lob_humans)
            self.log(f"  lobsters: {len(lob_humans) if lob_humans else 0} humans")
        except Exception as e:
            self.log(f"lobsters scout error: {e}")

        # push all to central
        if scraped_humans:
            self.log(f"pushing {len(scraped_humans)} humans to CENTRAL...")
            try:
                created, updated = self.central.upsert_humans_bulk(scraped_humans)
                self.log(f"  central: {created} created, {updated} updated")
            except Exception as e:
                self.log(f"  central push error: {e}")

        self.last_scout = datetime.now()
        stats = self.central.get_stats()
        self.log(f"scout complete: {stats.get('total_humans', 0)} humans in CENTRAL")

    def match_priority_users(self):
        """find matches for priority users (hosts) using CENTRAL data"""
        priority_users = get_priority_users(self.local_db.conn)

        if not priority_users:
            return

        self.log(f"matching for {len(priority_users)} priority users (from CENTRAL)...")

        # get humans from CENTRAL
        humans = self.central.get_all_humans(min_score=20)

        for puser in priority_users:
            # use stored signals first (from discovery/scoring)
            puser_signals = []
            if puser.get('signals'):
                stored = puser['signals']
                if isinstance(stored, str):
                    try:
                        stored = json.loads(stored)
                    except:
                        stored = []
                puser_signals.extend(stored)

            # supplement with interests if no signals stored
            if not puser_signals and puser.get('interests'):
                interests = json.loads(puser['interests']) if isinstance(puser['interests'], str) else puser['interests']
                puser_signals.extend(interests)

            if not puser_signals:
                self.log(f"  skipping {puser.get('name')} - no signals")
                continue

            matches_found = 0
            for human in humans:
                human_user = human.get('username', '').lower()
                if puser.get('github') and human_user == puser['github'].lower():
                    continue
                if puser.get('reddit') and human_user == puser['reddit'].lower():
                    continue
                if puser.get('mastodon') and human_user == puser['mastodon'].lower().split('@')[0]:
                    continue

                human_signals = human.get('signals', [])
                if isinstance(human_signals, str):
                    try:
                        human_signals = json.loads(human_signals)
                    except:
                        human_signals = []

                shared = set(puser_signals) & set(human_signals)
                overlap_score = len(shared) * 10

                if puser.get('location') and human.get('location'):
                    if 'seattle' in str(human.get('location', '')).lower() or 'pnw' in str(human.get('location', '')).lower():
                        overlap_score += 20

                if overlap_score >= MIN_OVERLAP_PRIORITY:
                    overlap_data = {
                        'overlap_score': overlap_score,
                        'overlap_reasons': [f"shared: {', '.join(list(shared)[:5])}"] if shared else [],
                    }
                    save_priority_match(self.local_db.conn, puser['id'], human['id'], overlap_data)
                    matches_found += 1

            if matches_found:
                self.log(f"  found {matches_found} matches for {puser['name'] or puser['email']}")

    def match_strangers(self):
        """find matches between discovered humans - save to CENTRAL"""
        self.log("matching strangers (-> CENTRAL)...")

        humans = self.central.get_all_humans(min_score=40)

        if len(humans) < 2:
            return

        fingerprints = {}
        for human in humans:
            fp = generate_fingerprint(human)
            fingerprints[human['id']] = fp

        matches_found = 0
        new_matches = []
        from itertools import combinations

        for human_a, human_b in combinations(humans, 2):
            if human_a['platform'] == human_b['platform']:
                if human_a['username'] == human_b['username']:
                    continue

            fp_a = fingerprints.get(human_a['id'])
            fp_b = fingerprints.get(human_b['id'])

            overlap = find_overlap(human_a, human_b, fp_a, fp_b)

            if overlap and overlap["overlap_score"] >= MIN_OVERLAP_STRANGERS:
                new_matches.append({
                    'human_a_id': human_a['id'],
                    'human_b_id': human_b['id'],
                    'overlap_score': overlap['overlap_score'],
                    'overlap_reasons': json.dumps(overlap.get('overlap_reasons', []))
                })
                matches_found += 1

        # bulk push to central
        if new_matches:
            self.log(f"pushing {len(new_matches)} matches to CENTRAL...")
            try:
                created = self.central.create_matches_bulk(new_matches)
                self.log(f"  central: {created} matches created")
            except Exception as e:
                self.log(f"  central push error: {e}")

        self.last_match = datetime.now()

    def send_stranger_intros(self):
        """send intros using CENTRAL data"""
        self.reset_daily_limits()

        if not self.dry_run and self.intros_today >= MAX_INTROS_PER_DAY:
            self.log("daily intro limit reached")
            return

        # get pending matches from CENTRAL
        matches = self.central.get_matches(min_score=MIN_OVERLAP_STRANGERS, limit=20)

        if self.dry_run:
            self.log(f"DRY RUN: previewing {len(matches)} potential intros")

        for match in matches:
            if not self.dry_run and self.intros_today >= MAX_INTROS_PER_DAY:
                break

            # get full human data
            human_a = self.central.get_human(match['human_a_id'])
            human_b = self.central.get_human(match['human_b_id'])

            if not human_a or not human_b:
                continue

            match_data = {
                'id': match['id'],
                'human_a': human_a,
                'human_b': human_b,
                'overlap_score': match['overlap_score'],
                'overlap_reasons': match.get('overlap_reasons', ''),
            }

            for recipient, other in [(human_a, human_b), (human_b, human_a)]:
                contact = recipient.get('contact', {})
                if isinstance(contact, str):
                    try:
                        contact = json.loads(contact)
                    except:
                        contact = {}

                email = contact.get('email')
                if not email:
                    continue

                # check if already contacted
                if self.central.already_contacted(recipient['id']):
                    continue

                # get token and interest count for recipient
                try:
                    recipient_token = self.central.get_token(recipient['id'], match.get('id'))
                    interested_count = self.central.get_interested_count(recipient['id'])
                except Exception as e:
                    print(f"[intro] failed to get token/count: {e}")
                    recipient_token = None
                    interested_count = 0

                intro = draft_intro(match_data, 
                                   recipient='a' if recipient == human_a else 'b',
                                   recipient_token=recipient_token,
                                   interested_count=interested_count)

                reasons = match.get('overlap_reasons', '')
                if isinstance(reasons, str):
                    try:
                        reasons = json.loads(reasons)
                    except:
                        reasons = []
                reason_summary = ', '.join(reasons[:3]) if reasons else 'aligned values'

                if self.dry_run:
                    print("\n" + "=" * 60)
                    print(f"TO: {recipient['username']} ({recipient['platform']})")
                    print(f"EMAIL: {email}")
                    print(f"SUBJECT: you might want to meet {other['username']}")
                    print(f"SCORE: {match['overlap_score']:.0f} ({reason_summary})")
                    print("-" * 60)
                    print("MESSAGE:")
                    print(intro['draft'])
                    print("-" * 60)
                    print("[DRY RUN - NOT SENT]")
                    print("=" * 60)
                    break
                else:
                    outreach_id = self.central.claim_outreach(recipient['id'], match['id'], 'intro')
                    if outreach_id is None:
                        self.log(f"skipping {recipient['username']} - already claimed")
                        continue

                    success, error = send_email(
                        email,
                        f"connectd: you might want to meet {other['username']}",
                        intro['draft']
                    )

                    if success:
                        self.log(f"sent intro to {recipient['username']} ({email})")
                        self.intros_today += 1
                        self.central.complete_outreach(outreach_id, 'sent', 'email', intro['draft'])
                        break
                    else:
                        self.log(f"failed to send to {email}: {error}")
                        self.central.complete_outreach(outreach_id, 'failed', error=error)

        self.last_intro = datetime.now()

    def send_priority_user_intros(self):
        """send intros TO priority users (hosts) about their matches"""
        self.reset_daily_limits()

        priority_users = get_priority_users(self.local_db.conn)
        if not priority_users:
            return

        self.log(f"checking intros for {len(priority_users)} priority users...")

        for puser in priority_users:
            if not self.dry_run and self.intros_today >= MAX_INTROS_PER_DAY:
                break

            # get email
            email = puser.get('email')
            if not email:
                continue

            # get their matches from local priority_matches table
            matches = get_priority_user_matches(self.local_db.conn, puser['id'], status='new', limit=5)

            if not matches:
                continue

            for match in matches:
                if not self.dry_run and self.intros_today >= MAX_INTROS_PER_DAY:
                    break

                # get the matched human from CENTRAL (matched_human_id is central id)
                human_id = match.get('matched_human_id')
                if not human_id:
                    continue

                human = self.central.get_human(human_id)
                if not human:
                    continue

                # build match data for drafting
                overlap_reasons = match.get('overlap_reasons', '[]')
                if isinstance(overlap_reasons, str):
                    try:
                        overlap_reasons = json.loads(overlap_reasons)
                    except:
                        overlap_reasons = []

                puser_name = puser.get('name') or puser.get('email', '').split('@')[0]
                human_name = human.get('name') or human.get('username')

                # draft intro TO priority user ABOUT the matched human
                match_data = {
                    'id': match.get('id'),
                    'human_a': {
                        'username': puser_name,
                        'platform': 'host',
                        'name': puser_name,
                        'bio': puser.get('bio', ''),
                        'signals': puser.get('signals', []),
                    },
                    'human_b': human,
                    'overlap_score': match.get('overlap_score', 0),
                    'overlap_reasons': overlap_reasons,
                }

                # try to get token for priority user (they might have a central ID)
                recipient_token = None
                interested_count = 0
                if puser.get('central_id'):
                    try:
                        recipient_token = self.central.get_token(puser['central_id'], match.get('id'))
                        interested_count = self.central.get_interested_count(puser['central_id'])
                    except:
                        pass

                intro = draft_intro(match_data, recipient='a',
                                   recipient_token=recipient_token,
                                   interested_count=interested_count)

                reason_summary = ', '.join(overlap_reasons[:3]) if overlap_reasons else 'aligned values'

                if self.dry_run:
                    print("\n" + "=" * 60)
                    print("PRIORITY USER INTRO")
                    print("=" * 60)
                    print(f"TO: {puser_name} ({email})")
                    print(f"ABOUT: {human_name} ({human.get('platform')})")
                    print(f"SCORE: {match.get('overlap_score', 0):.0f} ({reason_summary})")
                    print("-" * 60)
                    print("MESSAGE:")
                    print(intro['draft'])
                    print("-" * 60)
                    print("[DRY RUN - NOT SENT]")
                    print("=" * 60)
                else:
                    success, error = send_email(
                        email,
                        f"connectd: you might want to meet {human_name}",
                        intro['draft']
                    )

                    if success:
                        self.log(f"sent priority intro to {puser_name} about {human_name}")
                        self.intros_today += 1
                        # mark match as notified
                        mark_match_viewed(self.local_db.conn, match['id'])
                    else:
                        self.log(f"failed to send priority intro to {email}: {error}")

    def send_lost_builder_intros(self):
        """reach out to lost builders using CENTRAL data"""
        self.reset_daily_limits()

        lost_config = get_lost_config()

        if not lost_config.get('enabled', True):
            return

        max_per_day = lost_config.get('max_per_day', 5)
        if not self.dry_run and self.lost_intros_today >= max_per_day:
            self.log("daily lost builder intro limit reached")
            return

        # get lost builders from CENTRAL
        lost_builders = self.central.get_lost_builders(
            min_score=lost_config.get('min_lost_score', 40),
            limit=max_per_day - self.lost_intros_today
        )

        # get active builders from CENTRAL
        builders = self.central.get_builders(min_score=50, limit=100)

        if not lost_builders or not builders:
            self.log("no lost builders or builders available")
            return

        if self.dry_run:
            self.log(f"DRY RUN: previewing {len(lost_builders)} lost builder intros")

        for lost in lost_builders:
            if not self.dry_run and self.lost_intros_today >= max_per_day:
                break

            # find matching builder
            best_builder = None
            best_score = 0
            for builder in builders:
                lost_signals = lost.get('signals', [])
                builder_signals = builder.get('signals', [])
                if isinstance(lost_signals, str):
                    try:
                        lost_signals = json.loads(lost_signals)
                    except:
                        lost_signals = []
                if isinstance(builder_signals, str):
                    try:
                        builder_signals = json.loads(builder_signals)
                    except:
                        builder_signals = []

                shared = set(lost_signals) & set(builder_signals)
                if len(shared) > best_score:
                    best_score = len(shared)
                    best_builder = builder

            if not best_builder:
                continue

            lost_name = lost.get('name') or lost.get('username')
            builder_name = best_builder.get('name') or best_builder.get('username')

            draft, draft_error = draft_lost_intro(lost, best_builder, lost_config)

            if draft_error:
                self.log(f"error drafting lost intro for {lost_name}: {draft_error}")
                continue

            method, contact_info = determine_best_contact(lost)

            if self.dry_run:
                print("\n" + "=" * 60)
                print("LOST BUILDER OUTREACH")
                print("=" * 60)
                print(f"TO: {lost_name} ({lost.get('platform')})")
                print(f"DELIVERY: {method} → {contact_info}")
                print(f"LOST SCORE: {lost.get('lost_potential_score', 0)}")
                print(f"INSPIRING BUILDER: {builder_name}")
                print("-" * 60)
                print("MESSAGE:")
                print(draft)
                print("-" * 60)
                print("[DRY RUN - NOT SENT]")
                print("=" * 60)
            else:
                match_data = {
                    'human_a': best_builder,
                    'human_b': lost,
                    'overlap_score': best_score * 10,
                    'overlap_reasons': [],
                }

                success, error, delivery_method = deliver_intro(match_data, draft)

                if success:
                    self.log(f"sent lost builder intro to {lost_name} via {delivery_method}")
                    self.lost_intros_today += 1
                else:
                    self.log(f"failed to reach {lost_name} via {delivery_method}: {error}")

        self.last_lost = datetime.now()
        self.log(f"lost builder cycle complete: {self.lost_intros_today} sent today")

    def run(self):
        """main daemon loop"""
        self.log("connectd daemon starting (CENTRAL MODE)...")

        start_api_thread()
        self.log("api server started on port 8099")

        if self.dry_run:
            self.log("*** DRY RUN MODE - no intros will be sent ***")
        self.log(f"scout interval: {SCOUT_INTERVAL}s")
        self.log(f"match interval: {MATCH_INTERVAL}s")
        self.log(f"intro interval: {INTRO_INTERVAL}s")
        self.log(f"lost interval: {LOST_INTERVAL}s")
        self.log(f"max intros/day: {MAX_INTROS_PER_DAY}")

        # initial scout
        self.scout_cycle()
        self._update_api_state()

        while self.running:
            now = datetime.now()

            if not self.last_scout or (now - self.last_scout).seconds >= SCOUT_INTERVAL:
                self.scout_cycle()
                self._update_api_state()

            if not self.last_match or (now - self.last_match).seconds >= MATCH_INTERVAL:
                self.match_priority_users()
                self.match_strangers()
                self._update_api_state()

            if not self.last_intro or (now - self.last_intro).seconds >= INTRO_INTERVAL:
                self.send_stranger_intros()
                self.send_priority_user_intros()
                self._update_api_state()

            if not self.last_lost or (now - self.last_lost).seconds >= LOST_INTERVAL:
                self.send_lost_builder_intros()
                self._update_api_state()

            time.sleep(60)

        self.log("connectd daemon stopped")
        self.local_db.close()


def run_daemon(dry_run=False):
    daemon = ConnectDaemon(dry_run=dry_run)
    daemon.run()


if __name__ == '__main__':
    import sys
    dry_run = '--dry-run' in sys.argv
    run_daemon(dry_run=dry_run)
