#!/usr/bin/env python3
"""
connectd daemon - continuous discovery and matchmaking

two modes of operation:
1. priority matching: find matches FOR hosts who run connectd
2. altruistic matching: connect strangers to each other

runs continuously, respects rate limits, sends intros automatically
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
                      get_priority_user_matches, discover_host_user)
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

# daemon config
SCOUT_INTERVAL = 3600 * 4      # full scout every 4 hours
MATCH_INTERVAL = 3600          # check matches every hour
INTRO_INTERVAL = 3600 * 2      # send intros every 2 hours
LOST_INTERVAL = 3600 * 6       # lost builder outreach every 6 hours (lower volume)
from config import MAX_INTROS_PER_DAY

# central coordination (optional - for distributed instances)
try:
    from central_client import CentralClient
    CENTRAL_ENABLED = bool(os.environ.get('CONNECTD_API_KEY'))
except ImportError:
    CENTRAL_ENABLED = False
    CentralClient = None  # from config.py
MIN_OVERLAP_PRIORITY = 30      # min score for priority user matches
MIN_OVERLAP_STRANGERS = 50     # higher bar for stranger intros


class ConnectDaemon:
    def __init__(self, dry_run=False):
        self.db = Database()
        init_users_table(self.db.conn)
        purged = self.db.purge_disqualified()
        if any(purged.values()):
            self.log(f"purged disqualified: {purged}")
        self.running = True
        self.dry_run = dry_run
        self.started_at = datetime.now()
        self.last_scout = None
        self.last_match = None
        self.last_intro = None
        self.last_lost = None
        self.intros_today = 0
        self.lost_intros_today = 0

        # central coordination
        self.central = None
        if CENTRAL_ENABLED:
            try:
                self.central = CentralClient()
                instance_id = os.environ.get('CONNECTD_INSTANCE_ID', 'unknown')
                self.central.register_instance(instance_id, os.environ.get('CONNECTD_INSTANCE_IP', 'unknown'))
                self.log(f"connected to central API as {instance_id}")
            except Exception as e:
                self.log(f"central API unavailable: {e}")
                self.central = None
        self.today = datetime.now().date()

        # handle shutdown gracefully
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        # auto-discover host user from env
        if HOST_USER:
            self.log(f"HOST_USER set: {HOST_USER}")
            discover_host_user(self.db.conn, HOST_USER)

        # update API state
        self._update_api_state()

    def _shutdown(self, signum, frame):
        print("\nconnectd: shutting down...")
        self.running = False
        self._update_api_state()

    def _update_api_state(self):
        """update API state for HA integration"""
        now = datetime.now()

        # calculate countdowns - if no cycle has run, use started_at
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
        """timestamped log"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def reset_daily_limits(self):
        """reset daily intro count"""
        if datetime.now().date() != self.today:
            self.today = datetime.now().date()
            self.intros_today = 0
            self.lost_intros_today = 0

        # central coordination
        self.central = None
        if CENTRAL_ENABLED:
            try:
                self.central = CentralClient()
                instance_id = os.environ.get('CONNECTD_INSTANCE_ID', 'unknown')
                self.central.register_instance(instance_id, os.environ.get('CONNECTD_INSTANCE_IP', 'unknown'))
                self.log(f"connected to central API as {instance_id}")
            except Exception as e:
                self.log(f"central API unavailable: {e}")
                self.central = None
            self.log("reset daily intro limits")

    def scout_cycle(self):
        """run discovery on all platforms"""
        self.log("starting scout cycle...")

        try:
            scrape_github(self.db, limit_per_source=30)
        except Exception as e:
            self.log(f"github scout error: {e}")

        try:
            scrape_reddit(self.db, limit_per_sub=30)
        except Exception as e:
            self.log(f"reddit scout error: {e}")

        try:
            scrape_mastodon(self.db, limit_per_instance=30)

            # scrape self-hosted git forges (highest signal)
            self.log("scraping self-hosted git forges...")
            try:
                forge_humans = scrape_all_forges(limit_per_instance=30)
                for h in forge_humans:
                    self.db.upsert_human(h)
                self.log(f"  forges: {len(forge_humans)} humans")
            except Exception as e:
                self.log(f"  forge scrape error: {e}")
        except Exception as e:
            self.log(f"mastodon scout error: {e}")

        try:
            scrape_lobsters(self.db)
        except Exception as e:
            self.log(f"lobsters scout error: {e}")

        try:
            scrape_lemmy(self.db, limit_per_community=30)
        except Exception as e:
            self.log(f"lemmy scout error: {e}")

        try:
            scrape_discord(self.db, limit_per_channel=50)
        except Exception as e:
            self.log(f"discord scout error: {e}")

        self.last_scout = datetime.now()
        stats = self.db.stats()
        self.log(f"scout complete: {stats['total_humans']} humans in db")

    def match_priority_users(self):
        """find matches for priority users (hosts)"""
        priority_users = get_priority_users(self.db.conn)

        if not priority_users:
            return

        self.log(f"matching for {len(priority_users)} priority users...")

        humans = self.db.get_all_humans(min_score=20)

        for puser in priority_users:
            # build priority user's fingerprint from their linked profiles
            puser_signals = []
            puser_text = []

            if puser.get('bio'):
                puser_text.append(puser['bio'])
            if puser.get('interests'):
                interests = json.loads(puser['interests']) if isinstance(puser['interests'], str) else puser['interests']
                puser_signals.extend(interests)
            if puser.get('looking_for'):
                puser_text.append(puser['looking_for'])

            # analyze their linked github if available
            if puser.get('github'):
                gh_user = analyze_github_user(puser['github'])
                if gh_user:
                    puser_signals.extend(gh_user.get('signals', []))

            puser_fingerprint = {
                'values_vector': {},
                'skills': {},
                'interests': list(set(puser_signals)),
                'location_pref': 'pnw' if puser.get('location') and 'seattle' in puser['location'].lower() else None,
            }

            # score text
            if puser_text:
                _, text_signals, _ = analyze_text(' '.join(puser_text))
                puser_signals.extend(text_signals)

            # find matches
            matches_found = 0
            for human in humans:
                # skip if it's their own profile on another platform
                human_user = human.get('username', '').lower()
                if puser.get('github') and human_user == puser['github'].lower():
                    continue
                if puser.get('reddit') and human_user == puser['reddit'].lower():
                    continue
                if puser.get('mastodon') and human_user == puser['mastodon'].lower().split('@')[0]:
                    continue

                # calculate overlap
                human_signals = human.get('signals', [])
                if isinstance(human_signals, str):
                    human_signals = json.loads(human_signals)

                shared = set(puser_signals) & set(human_signals)
                overlap_score = len(shared) * 10

                # location bonus
                if puser.get('location') and human.get('location'):
                    if 'seattle' in human['location'].lower() or 'pnw' in human['location'].lower():
                        overlap_score += 20

                if overlap_score >= MIN_OVERLAP_PRIORITY:
                    overlap_data = {
                        'overlap_score': overlap_score,
                        'overlap_reasons': [f"shared: {', '.join(list(shared)[:5])}"] if shared else [],
                    }
                    save_priority_match(self.db.conn, puser['id'], human['id'], overlap_data)
                    matches_found += 1

            if matches_found:
                self.log(f"  found {matches_found} matches for {puser['name'] or puser['email']}")

    def match_strangers(self):
        """find matches between discovered humans (altruistic)"""
        self.log("matching strangers...")

        humans = self.db.get_all_humans(min_score=40)

        if len(humans) < 2:
            return

        # generate fingerprints
        fingerprints = {}
        for human in humans:
            fp = generate_fingerprint(human)
            fingerprints[human['id']] = fp

        # find pairs
        matches_found = 0
        from itertools import combinations

        for human_a, human_b in combinations(humans, 2):
            # skip same platform same user
            if human_a['platform'] == human_b['platform']:
                if human_a['username'] == human_b['username']:
                    continue

            fp_a = fingerprints.get(human_a['id'])
            fp_b = fingerprints.get(human_b['id'])

            overlap = find_overlap(human_a, human_b, fp_a, fp_b)

            if overlap and overlap["overlap_score"] >= MIN_OVERLAP_STRANGERS:
                # save match
                self.db.save_match(human_a['id'], human_b['id'], overlap)
                matches_found += 1

        if matches_found:
            self.log(f"found {matches_found} stranger matches")

        self.last_match = datetime.now()

    def claim_from_central(self, human_id, match_id=None, outreach_type='intro'):
        """claim outreach from central - returns outreach_id or None if already claimed"""
        if not self.central:
            return -1  # local mode, always allow
        try:
            return self.central.claim_outreach(human_id, match_id, outreach_type)
        except Exception as e:
            self.log(f"central claim error: {e}")
            return -1  # allow local if central fails

    def complete_on_central(self, outreach_id, status, sent_via=None, draft=None, error=None):
        """mark outreach complete on central"""
        if not self.central or outreach_id == -1:
            return
        try:
            self.central.complete_outreach(outreach_id, status, sent_via, draft, error)
        except Exception as e:
            self.log(f"central complete error: {e}")

    def sync_to_central(self, humans=None, matches=None):
        """sync local data to central"""
        if not self.central:
            return
        try:
            if humans:
                self.central.upsert_humans_bulk(humans)
            if matches:
                self.central.create_matches_bulk(matches)
        except Exception as e:
            self.log(f"central sync error: {e}")

    def send_stranger_intros(self):
        """send intros to connect strangers (or preview in dry-run mode)"""
        self.reset_daily_limits()

        if not self.dry_run and self.intros_today >= MAX_INTROS_PER_DAY:
            self.log("daily intro limit reached")
            return

        # get unsent matches
        c = self.db.conn.cursor()
        c.execute('''SELECT m.*,
                            ha.id as a_id, ha.username as a_user, ha.platform as a_platform,
                            ha.name as a_name, ha.url as a_url, ha.contact as a_contact,
                            ha.signals as a_signals, ha.extra as a_extra,
                            hb.id as b_id, hb.username as b_user, hb.platform as b_platform,
                            hb.name as b_name, hb.url as b_url, hb.contact as b_contact,
                            hb.signals as b_signals, hb.extra as b_extra
                     FROM matches m
                     JOIN humans ha ON m.human_a_id = ha.id
                     JOIN humans hb ON m.human_b_id = hb.id
                     WHERE m.status = 'pending'
                     ORDER BY m.overlap_score DESC
                     LIMIT 10''')

        matches = c.fetchall()

        if self.dry_run:
            self.log(f"DRY RUN: previewing {len(matches)} potential intros")

        for match in matches:
            if not self.dry_run and self.intros_today >= MAX_INTROS_PER_DAY:
                break

            match = dict(match)

            # build human dicts
            human_a = {
                'id': match['a_id'],
                'username': match['a_user'],
                'platform': match['a_platform'],
                'name': match['a_name'],
                'url': match['a_url'],
                'contact': match['a_contact'],
                'signals': match['a_signals'],
                'extra': match['a_extra'],
            }
            human_b = {
                'id': match['b_id'],
                'username': match['b_user'],
                'platform': match['b_platform'],
                'name': match['b_name'],
                'url': match['b_url'],
                'contact': match['b_contact'],
                'signals': match['b_signals'],
                'extra': match['b_extra'],
            }

            match_data = {
                'id': match['id'],
                'human_a': human_a,
                'human_b': human_b,
                'overlap_score': match['overlap_score'],
                'overlap_reasons': match['overlap_reasons'],
            }

            # try to send intro to person with email
            for recipient, other in [(human_a, human_b), (human_b, human_a)]:
                contact = recipient.get('contact', {})
                if isinstance(contact, str):
                    contact = json.loads(contact)

                email = contact.get('email')
                if not email:
                    continue

                # draft intro
                intro = draft_intro(match_data, recipient='a' if recipient == human_a else 'b')

                # parse overlap reasons for display
                reasons = match['overlap_reasons']
                if isinstance(reasons, str):
                    reasons = json.loads(reasons)
                reason_summary = ', '.join(reasons[:3]) if reasons else 'aligned values'

                if self.dry_run:
                    # print preview
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
                    # claim from central first
                    outreach_id = self.claim_from_central(recipient['id'], match['id'], 'intro')
                    if outreach_id is None:
                        self.log(f"skipping {recipient['username']} - already claimed by another instance")
                        continue

                    # actually send
                    success, error = send_email(
                        email,
                        f"connectd: you might want to meet {other['username']}",
                        intro['draft']
                    )

                    if success:
                        self.log(f"sent intro to {recipient['username']} ({email})")
                        self.intros_today += 1
                        self.complete_on_central(outreach_id, 'sent', 'email', intro['draft'])

                        # mark match as intro_sent
                        c.execute('UPDATE matches SET status = "intro_sent" WHERE id = ?',
                                  (match['id'],))
                        self.db.conn.commit()
                        break
                    else:
                        self.log(f"failed to send to {email}: {error}")
                        self.complete_on_central(outreach_id, 'failed', error=error)

        self.last_intro = datetime.now()

    def send_lost_builder_intros(self):
        """
        reach out to lost builders - different tone, lower volume.
        these people need encouragement, not networking.
        """
        self.reset_daily_limits()

        lost_config = get_lost_config()

        if not lost_config.get('enabled', True):
            return

        max_per_day = lost_config.get('max_per_day', 5)
        if not self.dry_run and self.lost_intros_today >= max_per_day:
            self.log("daily lost builder intro limit reached")
            return

        # find lost builders with matching active builders
        matches, error = find_matches_for_lost_builders(
            self.db,
            min_lost_score=lost_config.get('min_lost_score', 40),
            min_values_score=lost_config.get('min_values_score', 20),
            limit=max_per_day - self.lost_intros_today
        )

        if error:
            self.log(f"lost builder matching error: {error}")
            return

        if not matches:
            self.log("no lost builders ready for outreach")
            return

        if self.dry_run:
            self.log(f"DRY RUN: previewing {len(matches)} lost builder intros")

        for match in matches:
            if not self.dry_run and self.lost_intros_today >= max_per_day:
                break

            lost = match['lost_user']
            builder = match['inspiring_builder']

            lost_name = lost.get('name') or lost.get('username')
            builder_name = builder.get('name') or builder.get('username')

            # draft intro
            draft, draft_error = draft_lost_intro(lost, builder, lost_config)

            if draft_error:
                self.log(f"error drafting lost intro for {lost_name}: {draft_error}")
                continue

            # determine best contact method (activity-based)
            method, contact_info = determine_best_contact(lost)

            if self.dry_run:
                print("\n" + "=" * 60)
                print("LOST BUILDER OUTREACH")
                print("=" * 60)
                print(f"TO: {lost_name} ({lost.get('platform')})")
                print(f"DELIVERY: {method} → {contact_info}")
                print(f"LOST SCORE: {lost.get('lost_potential_score', 0)}")
                print(f"VALUES SCORE: {lost.get('score', 0)}")
                print(f"INSPIRING BUILDER: {builder_name}")
                print(f"SHARED INTERESTS: {', '.join(match.get('shared_interests', []))}")
                print("-" * 60)
                print("MESSAGE:")
                print(draft)
                print("-" * 60)
                print("[DRY RUN - NOT SENT]")
                print("=" * 60)
            else:
                # build match data for unified delivery
                match_data = {
                    'human_a': builder,  # inspiring builder
                    'human_b': lost,     # lost builder (recipient)
                    'overlap_score': match.get('match_score', 0),
                    'overlap_reasons': match.get('shared_interests', []),
                }

                success, error, delivery_method = deliver_intro(match_data, draft)

                if success:
                    self.log(f"sent lost builder intro to {lost_name} via {delivery_method}")
                    self.lost_intros_today += 1
                    self.db.mark_lost_outreach(lost['id'])
                else:
                    self.log(f"failed to reach {lost_name} via {delivery_method}: {error}")

        self.last_lost = datetime.now()
        self.log(f"lost builder cycle complete: {self.lost_intros_today} sent today")

    def run(self):
        """main daemon loop"""
        self.log("connectd daemon starting...")

        # start API server
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

            # scout cycle
            if not self.last_scout or (now - self.last_scout).seconds >= SCOUT_INTERVAL:
                self.scout_cycle()
                self._update_api_state()

            # match cycle
            if not self.last_match or (now - self.last_match).seconds >= MATCH_INTERVAL:
                self.match_priority_users()
                self.match_strangers()
                self._update_api_state()

            # intro cycle
            if not self.last_intro or (now - self.last_intro).seconds >= INTRO_INTERVAL:
                self.send_stranger_intros()
                self._update_api_state()

            # lost builder cycle
            if not self.last_lost or (now - self.last_lost).seconds >= LOST_INTERVAL:
                self.send_lost_builder_intros()
                self._update_api_state()

            # sleep between checks
            time.sleep(60)

        self.log("connectd daemon stopped")
        self.db.close()


def run_daemon(dry_run=False):
    """entry point"""
    daemon = ConnectDaemon(dry_run=dry_run)
    daemon.run()


if __name__ == '__main__':
    import sys
    dry_run = '--dry-run' in sys.argv
    run_daemon(dry_run=dry_run)
