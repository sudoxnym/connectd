#!/usr/bin/env python3
"""
connectd - people discovery and matchmaking daemon
finds isolated builders and connects them
also finds LOST builders who need encouragement

usage:
    connectd scout              # run all scrapers
    connectd scout --github     # github only
    connectd scout --reddit     # reddit only
    connectd scout --mastodon   # mastodon only
    connectd scout --lobsters   # lobste.rs only
    connectd scout --matrix     # matrix only
    connectd scout --lost       # show lost builder stats after scout

    connectd match              # find all matches
    connectd match --top 20     # show top 20 matches
    connectd match --mine       # show YOUR matches (priority user)
    connectd match --lost       # find matches for lost builders

    connectd intro              # generate intros for top matches
    connectd intro --match 123  # generate intro for specific match
    connectd intro --dry-run    # preview intros without saving
    connectd intro --lost       # generate intros for lost builders

    connectd review             # interactive review queue
    connectd send               # send all approved intros
    connectd send --export      # export for manual sending

    connectd daemon             # run as continuous daemon
    connectd daemon --oneshot   # run once then exit
    connectd daemon --dry-run   # run but never send intros
    connectd daemon --oneshot --dry-run  # one cycle, preview only

    connectd user               # show your priority user profile
    connectd user --setup       # setup/update your profile
    connectd user --matches     # show matches found for you

    connectd status             # show database stats (including lost builders)
    connectd lost               # show lost builders ready for outreach
"""

import argparse
import sys
from pathlib import Path

# add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from db import Database
from db.users import (init_users_table, add_priority_user, get_priority_users,
                      get_priority_user_matches, score_priority_user, auto_match_priority_user,
                      update_priority_user_profile)
from scoutd import scrape_github, scrape_reddit, scrape_mastodon, scrape_lobsters, scrape_matrix
from scoutd.deep import deep_scrape_github_user
from scoutd.lost import get_signal_descriptions
from introd.deliver import (deliver_intro, deliver_batch, get_delivery_stats,
                            review_manual_queue, determine_best_contact, load_manual_queue,
                            save_manual_queue)
from matchd import find_all_matches, generate_fingerprint
from matchd.rank import get_top_matches
from matchd.lost import find_matches_for_lost_builders, get_lost_match_summary
from introd import draft_intro
from introd.draft import draft_intros_for_match
from introd.lost_intro import draft_lost_intro, get_lost_intro_config
from introd.review import review_all_pending, get_pending_intros
from introd.send import send_all_approved, export_manual_intros


def cmd_scout(args, db):
    """run discovery scrapers"""
    from scoutd.deep import deep_scrape_github_user, save_deep_profile

    print("=" * 60)
    print("connectd scout - discovering aligned humans")
    print("=" * 60)

    # deep scrape specific user
    if args.user:
        print(f"\ndeep scraping github user: {args.user}")
        profile = deep_scrape_github_user(args.user)
        if profile:
            save_deep_profile(db, profile)
            print(f"\n=== {profile['username']} ===")
            print(f"real name: {profile.get('real_name')}")
            print(f"location: {profile.get('location')}")
            print(f"company: {profile.get('company')}")
            print(f"email: {profile.get('email')}")
            print(f"twitter: {profile.get('twitter')}")
            print(f"mastodon: {profile.get('mastodon')}")
            print(f"orgs: {', '.join(profile.get('orgs', []))}")
            print(f"languages: {', '.join(list(profile.get('languages', {}).keys())[:5])}")
            print(f"topics: {', '.join(profile.get('topics', [])[:10])}")
            print(f"signals: {', '.join(profile.get('signals', []))}")
            print(f"score: {profile.get('score')}")
            if profile.get('linked_profiles'):
                print(f"linked profiles: {list(profile['linked_profiles'].keys())}")
        else:
            print("failed to scrape user")
        return

    run_all = not any([args.github, args.reddit, args.mastodon, args.lobsters, args.matrix, args.twitter, args.bluesky, args.lemmy, args.discord])

    if args.github or run_all:
        if args.deep:
            # deep scrape mode - slower but more thorough
            print("\nrunning DEEP github scrape (follows all links)...")
            from scoutd.github import get_repo_contributors
            from scoutd.signals import ECOSYSTEM_REPOS

            all_logins = set()
            for repo in ECOSYSTEM_REPOS[:5]:  # limit for deep mode
                contributors = get_repo_contributors(repo, per_page=20)
                for c in contributors:
                    login = c.get('login')
                    if login and not login.endswith('[bot]'):
                        all_logins.add(login)
                print(f"  {repo}: {len(contributors)} contributors")

            print(f"\ndeep scraping {len(all_logins)} users...")
            for login in all_logins:
                try:
                    profile = deep_scrape_github_user(login)
                    if profile and profile.get('score', 0) > 0:
                        save_deep_profile(db, profile)
                        if profile['score'] >= 30:
                            print(f"  ★ {login}: {profile['score']} pts")
                            if profile.get('email'):
                                print(f"      email: {profile['email']}")
                            if profile.get('mastodon'):
                                print(f"      mastodon: {profile['mastodon']}")
                except Exception as e:
                    print(f"  error on {login}: {e}")
        else:
            scrape_github(db)

    if args.reddit or run_all:
        scrape_reddit(db)

    if args.mastodon or run_all:
        scrape_mastodon(db)

    if args.lobsters or run_all:
        scrape_lobsters(db)

    if args.matrix or run_all:
        scrape_matrix(db)

    if args.twitter or run_all:
        from scoutd.twitter import scrape_twitter
        scrape_twitter(db)

    if args.bluesky or run_all:
        from scoutd.bluesky import scrape_bluesky
        scrape_bluesky(db)

    if args.lemmy or run_all:
        from scoutd.lemmy import scrape_lemmy
        scrape_lemmy(db)

    if args.discord or run_all:
        from scoutd.discord import scrape_discord
        scrape_discord(db)

    # show stats
    stats = db.stats()
    print("\n" + "=" * 60)
    print("SCOUT COMPLETE")
    print("=" * 60)
    print(f"total humans: {stats['total_humans']}")
    for platform, count in stats.get('by_platform', {}).items():
        print(f"  {platform}: {count}")

    # show lost builder stats if requested
    if args.lost or True:  # always show lost stats now
        print("\n--- lost builder stats ---")
        print(f"active builders: {stats.get('active_builders', 0)}")
        print(f"lost builders: {stats.get('lost_builders', 0)}")
        print(f"recovering builders: {stats.get('recovering_builders', 0)}")
        print(f"high lost score (40+): {stats.get('high_lost_score', 0)}")
        print(f"lost outreach sent: {stats.get('lost_outreach_sent', 0)}")


def cmd_match(args, db):
    """find and rank matches"""
    import json as json_mod

    print("=" * 60)
    print("connectd match - finding aligned pairs")
    print("=" * 60)

    # lost builder matching
    if args.lost:
        print("\n--- LOST BUILDER MATCHING ---")
        print("finding inspiring builders for lost souls...\n")

        matches, error = find_matches_for_lost_builders(db, limit=args.top or 20)

        if error:
            print(f"error: {error}")
            return

        if not matches:
            print("no lost builders ready for outreach")
            return

        print(f"found {len(matches)} lost builders with matching active builders\n")

        for i, match in enumerate(matches, 1):
            lost = match['lost_user']
            builder = match['inspiring_builder']

            lost_name = lost.get('name') or lost.get('username')
            builder_name = builder.get('name') or builder.get('username')

            print(f"{i}. {lost_name} ({lost.get('platform')}) → needs inspiration from")
            print(f"   {builder_name} ({builder.get('platform')})")
            print(f"   lost score: {lost.get('lost_potential_score', 0)} | values: {lost.get('score', 0)}")
            print(f"   shared interests: {', '.join(match.get('shared_interests', []))}")
            print(f"   builder has: {match.get('builder_repos', 0)} repos, {match.get('builder_stars', 0)} stars")
            print()

        return

    if args.mine:
        # show matches for priority user
        init_users_table(db.conn)
        users = get_priority_users(db.conn)
        if not users:
            print("no priority user configured. run: connectd user --setup")
            return

        for user in users:
            print(f"\n=== matches for {user['name']} ===\n")
            matches = get_priority_user_matches(db.conn, user['id'], limit=args.top or 20)

            if not matches:
                print("no matches yet - run: connectd scout && connectd match")
                continue

            for i, match in enumerate(matches, 1):
                print(f"{i}. {match['username']} ({match['platform']})")
                print(f"   score: {match['overlap_score']:.0f}")
                print(f"   url: {match['url']}")
                reasons = match.get('overlap_reasons', '[]')
                if isinstance(reasons, str):
                    reasons = json_mod.loads(reasons)
                if reasons:
                    print(f"   why: {reasons[0]}")
                print()
        return

    if args.top and not args.mine:
        # just show existing top matches
        matches = get_top_matches(db, limit=args.top)
    else:
        # run full matching
        matches = find_all_matches(db, min_score=args.min_score, min_overlap=args.min_overlap)

    print("\n" + "-" * 60)
    print(f"TOP {min(len(matches), args.top or 20)} MATCHES")
    print("-" * 60)

    for i, match in enumerate(matches[:args.top or 20], 1):
        human_a = match.get('human_a', {})
        human_b = match.get('human_b', {})

        print(f"\n{i}. {human_a.get('username')} <-> {human_b.get('username')}")
        print(f"   platforms: {human_a.get('platform')} / {human_b.get('platform')}")
        print(f"   overlap: {match.get('overlap_score', 0):.0f} pts")

        reasons = match.get('overlap_reasons', [])
        if isinstance(reasons, str):
            reasons = json_mod.loads(reasons)
        if reasons:
            print(f"   why: {' | '.join(reasons[:3])}")

        if match.get('geographic_match'):
            print(f"   location: compatible ✓")


def cmd_intro(args, db):
    """generate intro drafts"""
    import json as json_mod

    print("=" * 60)
    print("connectd intro - drafting introductions")
    print("=" * 60)

    if args.dry_run:
        print("*** DRY RUN MODE - previewing only ***\n")

    # lost builder intros - different tone entirely
    if args.lost:
        print("\n--- LOST BUILDER INTROS ---")
        print("drafting encouragement for lost souls...\n")

        matches, error = find_matches_for_lost_builders(db, limit=args.limit or 10)

        if error:
            print(f"error: {error}")
            return

        if not matches:
            print("no lost builders ready for outreach")
            return

        config = get_lost_intro_config()
        count = 0

        for match in matches:
            lost = match['lost_user']
            builder = match['inspiring_builder']

            lost_name = lost.get('name') or lost.get('username')
            builder_name = builder.get('name') or builder.get('username')

            # draft intro
            draft, error = draft_lost_intro(lost, builder, config)

            if error:
                print(f"  error drafting intro for {lost_name}: {error}")
                continue

            if args.dry_run:
                print("=" * 60)
                print(f"TO: {lost_name} ({lost.get('platform')})")
                print(f"LOST SCORE: {lost.get('lost_potential_score', 0)}")
                print(f"INSPIRING: {builder_name} ({builder.get('url')})")
                print("-" * 60)
                print("MESSAGE:")
                print(draft)
                print("-" * 60)
                print("[DRY RUN - NOT SAVED]")
                print("=" * 60)
            else:
                print(f"  drafted intro for {lost_name} → {builder_name}")

            count += 1

        if args.dry_run:
            print(f"\npreviewed {count} lost builder intros (dry run)")
        else:
            print(f"\ndrafted {count} lost builder intros")
            print("these require manual review before sending")

        return

    if args.match:
        # specific match
        matches = [m for m in get_top_matches(db, limit=1000) if m.get('id') == args.match]
    else:
        # top matches
        matches = get_top_matches(db, limit=args.limit or 10)

    if not matches:
        print("no matches found")
        return

    print(f"generating intros for {len(matches)} matches...")

    count = 0
    for match in matches:
        intros = draft_intros_for_match(match)

        for intro in intros:
            recipient = intro['recipient_human']
            other = intro['other_human']

            if args.dry_run:
                # get contact info
                contact = recipient.get('contact', {})
                if isinstance(contact, str):
                    contact = json_mod.loads(contact)
                email = contact.get('email', 'no email')

                # get overlap reasons
                reasons = match.get('overlap_reasons', [])
                if isinstance(reasons, str):
                    reasons = json_mod.loads(reasons)
                reason_summary = ', '.join(reasons[:3]) if reasons else 'aligned values'

                # print preview
                print("\n" + "=" * 60)
                print(f"TO: {recipient.get('username')} ({recipient.get('platform')})")
                print(f"EMAIL: {email}")
                print(f"SUBJECT: you might want to meet {other.get('username')}")
                print(f"SCORE: {match.get('overlap_score', 0):.0f} ({reason_summary})")
                print("-" * 60)
                print("MESSAGE:")
                print(intro['draft'])
                print("-" * 60)
                print("[DRY RUN - NOT SENT]")
                print("=" * 60)
            else:
                print(f"\n  {recipient.get('username')} ({intro['channel']})")

                # save to db
                db.save_intro(
                    match.get('id'),
                    recipient.get('id'),
                    intro['channel'],
                    intro['draft']
                )

            count += 1

    if args.dry_run:
        print(f"\npreviewed {count} intros (dry run - nothing saved)")
    else:
        print(f"\ngenerated {count} intro drafts")
        print("run 'connectd review' to approve before sending")


def cmd_review(args, db):
    """interactive review queue"""
    review_all_pending(db)


def cmd_send(args, db):
    """send approved intros"""
    import json as json_mod

    if args.export:
        # export manual queue to file for review
        queue = load_manual_queue()
        pending = [q for q in queue if q.get('status') == 'pending']

        with open(args.export, 'w') as f:
            json.dump(pending, f, indent=2)

        print(f"exported {len(pending)} pending intros to {args.export}")
        return

    # send all approved from manual queue
    queue = load_manual_queue()
    approved = [q for q in queue if q.get('status') == 'approved']

    if not approved:
        print("no approved intros to send")
        print("use 'connectd review' to approve intros first")
        return

    print(f"sending {len(approved)} approved intros...")

    for item in approved:
        match_data = item.get('match', {})
        intro_draft = item.get('draft', '')
        recipient = item.get('recipient', {})

        success, error, method = deliver_intro(
            {'human_b': recipient, **match_data},
            intro_draft,
            dry_run=args.dry_run if hasattr(args, 'dry_run') else False
        )

        status = 'ok' if success else f'failed: {error}'
        print(f"  {recipient.get('username')}: {method} - {status}")

        # update queue status
        item['status'] = 'sent' if success else 'failed'
        item['error'] = error

    save_manual_queue(queue)

    # show stats
    stats = get_delivery_stats()
    print(f"\ndelivery stats: {stats['sent']} sent, {stats['failed']} failed")


def cmd_lost(args, db):
    """show lost builders ready for outreach"""
    import json as json_mod

    print("=" * 60)
    print("connectd lost - lost builders who need encouragement")
    print("=" * 60)

    # get lost builders
    lost_builders = db.get_lost_builders_for_outreach(
        min_lost_score=args.min_score or 40,
        min_values_score=20,
        limit=args.limit or 50
    )

    if not lost_builders:
        print("\nno lost builders ready for outreach")
        print("run 'connectd scout' to discover more")
        return

    print(f"\n{len(lost_builders)} lost builders ready for outreach:\n")

    for i, lost in enumerate(lost_builders, 1):
        name = lost.get('name') or lost.get('username')
        platform = lost.get('platform')
        lost_score = lost.get('lost_potential_score', 0)
        values_score = lost.get('score', 0)

        # parse lost signals
        lost_signals = lost.get('lost_signals', [])
        if isinstance(lost_signals, str):
            lost_signals = json_mod.loads(lost_signals) if lost_signals else []

        # get signal descriptions
        signal_descriptions = get_signal_descriptions(lost_signals)

        print(f"{i}. {name} ({platform})")
        print(f"   lost score: {lost_score} | values score: {values_score}")
        print(f"   url: {lost.get('url')}")
        if signal_descriptions:
            print(f"   why lost: {', '.join(signal_descriptions[:3])}")
        print()

    if args.verbose:
        print("-" * 60)
        print("these people need encouragement, not networking.")
        print("the goal: show them someone like them made it.")
        print("-" * 60)


def cmd_status(args, db):
    """show database stats"""
    import json as json_mod

    init_users_table(db.conn)
    stats = db.stats()

    print("=" * 60)
    print("connectd status")
    print("=" * 60)

    # priority users
    users = get_priority_users(db.conn)
    print(f"\npriority users: {len(users)}")
    for user in users:
        print(f"  - {user['name']} ({user['email']})")

    print(f"\nhumans discovered: {stats['total_humans']}")
    print(f"  high-score (50+): {stats['high_score_humans']}")

    print("\nby platform:")
    for platform, count in stats.get('by_platform', {}).items():
        print(f"  {platform}: {count}")

    print(f"\nstranger matches: {stats['total_matches']}")
    print(f"intros created: {stats['total_intros']}")
    print(f"intros sent: {stats['sent_intros']}")

    # lost builder stats
    print("\n--- lost builder stats ---")
    print(f"active builders: {stats.get('active_builders', 0)}")
    print(f"lost builders: {stats.get('lost_builders', 0)}")
    print(f"recovering builders: {stats.get('recovering_builders', 0)}")
    print(f"high lost score (40+): {stats.get('high_lost_score', 0)}")
    print(f"lost outreach sent: {stats.get('lost_outreach_sent', 0)}")

    # priority user matches
    for user in users:
        matches = get_priority_user_matches(db.conn, user['id'])
        print(f"\nmatches for {user['name']}: {len(matches)}")

    # pending intros
    pending = get_pending_intros(db)
    print(f"\nintros pending review: {len(pending)}")


def cmd_daemon(args, db):
    """run as continuous daemon"""
    from daemon import ConnectDaemon

    daemon = ConnectDaemon(dry_run=args.dry_run)

    if args.oneshot:
        print("running one cycle...")
        if args.dry_run:
            print("*** DRY RUN MODE - no intros will be sent ***")
        daemon.scout_cycle()
        daemon.match_priority_users()
        daemon.match_strangers()
        daemon.send_stranger_intros()
        print("done")
    else:
        daemon.run()


def cmd_user(args, db):
    """manage priority user profile"""
    import json as json_mod

    init_users_table(db.conn)

    if args.setup:
        # interactive setup
        print("=" * 60)
        print("connectd priority user setup")
        print("=" * 60)
        print("\nlink your profiles so connectd finds matches for YOU\n")

        name = input("name: ").strip()
        email = input("email: ").strip()
        github = input("github username: ").strip() or None
        reddit = input("reddit username: ").strip() or None
        mastodon = input("mastodon (user@instance): ").strip() or None
        location = input("location (e.g. seattle): ").strip() or None

        print("\ninterests (comma separated):")
        interests_raw = input("> ").strip()
        interests = [i.strip() for i in interests_raw.split(',')] if interests_raw else []

        looking_for = input("looking for: ").strip() or None

        user_data = {
            'name': name, 'email': email, 'github': github,
            'reddit': reddit, 'mastodon': mastodon,
            'location': location, 'interests': interests,
            'looking_for': looking_for,
        }
        user_id = add_priority_user(db.conn, user_data)
        print(f"\n✓ added as priority user #{user_id}")

    elif args.matches:
        # show matches
        users = get_priority_users(db.conn)
        if not users:
            print("no priority user. run: connectd user --setup")
            return

        for user in users:
            print(f"\n=== matches for {user['name']} ===\n")
            matches = get_priority_user_matches(db.conn, user['id'], limit=20)

            if not matches:
                print("no matches yet")
                continue

            for i, match in enumerate(matches, 1):
                print(f"{i}. {match['username']} ({match['platform']})")
                print(f"   {match['url']}")
                print(f"   score: {match['overlap_score']:.0f}")
                print()

    else:
        # show profile
        users = get_priority_users(db.conn)
        if not users:
            print("no priority user configured")
            print("run: connectd user --setup")
            return

        for user in users:
            print("=" * 60)
            print(f"priority user #{user['id']}: {user['name']}")
            print("=" * 60)
            print(f"email: {user['email']}")
            if user['github']:
                print(f"github: {user['github']}")
            if user['reddit']:
                print(f"reddit: {user['reddit']}")
            if user['mastodon']:
                print(f"mastodon: {user['mastodon']}")
            if user['location']:
                print(f"location: {user['location']}")
            if user['interests']:
                interests = json_mod.loads(user['interests']) if isinstance(user['interests'], str) else user['interests']
                print(f"interests: {', '.join(interests)}")
            if user['looking_for']:
                print(f"looking for: {user['looking_for']}")


def cmd_me(args, db):
    """auto-score and auto-match for priority user with optional groq intros"""
    import json as json_mod

    init_users_table(db.conn)

    # get priority user
    users = get_priority_users(db.conn)
    if not users:
        print("no priority user configured")
        print("run: connectd user --setup")
        return

    user = users[0]  # first/main user
    print("=" * 60)
    print(f"connectd me - {user['name']}")
    print("=" * 60)

    # step 1: scrape github profile
    if user.get('github') and not args.skip_scrape:
        print(f"\n[1/4] scraping github profile: {user['github']}")
        profile = deep_scrape_github_user(user['github'], scrape_commits=False)
        if profile:
            print(f"  repos: {len(profile.get('top_repos', []))}")
            print(f"  languages: {', '.join(list(profile.get('languages', {}).keys())[:5])}")
        else:
            print("  failed to scrape (rate limited?)")
            profile = None
    else:
        print("\n[1/4] skipping github scrape (using saved profile)")
        # use saved profile if available
        saved = user.get('scraped_profile')
        if saved:
            profile = json_mod.loads(saved) if isinstance(saved, str) else saved
            print(f"  loaded saved profile: {len(profile.get('top_repos', []))} repos")
        else:
            profile = None

    # step 2: calculate score
    print(f"\n[2/4] calculating your score...")
    result = score_priority_user(db.conn, user['id'], profile)
    if result:
        print(f"  score: {result['score']}")
        print(f"  signals: {', '.join(sorted(result['signals'])[:10])}")

    # step 3: find matches
    print(f"\n[3/4] finding matches...")
    matches = auto_match_priority_user(db.conn, user['id'], min_overlap=args.min_overlap)
    print(f"  found {len(matches)} matches")

    # step 4: show results (optionally with groq intros)
    print(f"\n[4/4] top matches:")
    print("-" * 60)

    limit = args.limit or 10
    for i, m in enumerate(matches[:limit], 1):
        human = m['human']
        shared = m['shared']

        print(f"\n{i}. {human.get('name') or human['username']} ({human['platform']})")
        print(f"   {human.get('url', '')}")
        print(f"   score: {human.get('score', 0):.0f} | overlap: {m['overlap_score']:.0f}")
        print(f"   location: {human.get('location') or 'unknown'}")
        print(f"   why: {', '.join(shared[:5])}")

        # groq intro draft
        if args.groq:
            try:
                from introd.groq_draft import draft_intro_with_llm
                match_data = {
                    'human_a': {'name': user['name'], 'username': user.get('github'),
                                'platform': 'github', 'signals': result.get('signals', []) if result else [],
                                'bio': user.get('bio'), 'location': user.get('location'),
                                'extra': profile or {}},
                    'human_b': human,
                    'overlap_score': m['overlap_score'],
                    'overlap_reasons': shared,
                }
                intro, err = draft_intro_with_llm(match_data, recipient='b')
                if intro:
                    print(f"\n   --- groq draft ({intro.get('contact_method', 'manual')}) ---")
                    if intro.get('contact_info'):
                        print(f"   deliver via: {intro['contact_info']}")
                    for line in intro['draft'].split('\n'):
                        print(f"   {line}")
                    print(f"   ------------------")
                elif err:
                    print(f"   [groq error: {err}]")
            except Exception as e:
                print(f"   [groq error: {e}]")

    # summary
    print("\n" + "=" * 60)
    print(f"your score: {result['score'] if result else 'unknown'}")
    print(f"matches found: {len(matches)}")
    if args.groq:
        print("groq intros: enabled")
    else:
        print("tip: add --groq to generate ai intro drafts")


def main():
    parser = argparse.ArgumentParser(
        description='connectd - people discovery and matchmaking daemon',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='commands')

    # scout command
    scout_parser = subparsers.add_parser('scout', help='discover aligned humans')
    scout_parser.add_argument('--github', action='store_true', help='github only')
    scout_parser.add_argument('--reddit', action='store_true', help='reddit only')
    scout_parser.add_argument('--mastodon', action='store_true', help='mastodon only')
    scout_parser.add_argument('--lobsters', action='store_true', help='lobste.rs only')
    scout_parser.add_argument('--matrix', action='store_true', help='matrix only')
    scout_parser.add_argument('--twitter', action='store_true', help='twitter/x via nitter')
    scout_parser.add_argument('--bluesky', action='store_true', help='bluesky/atproto')
    scout_parser.add_argument('--lemmy', action='store_true', help='lemmy (fediverse reddit)')
    scout_parser.add_argument('--discord', action='store_true', help='discord servers')
    scout_parser.add_argument('--deep', action='store_true', help='deep scrape - follow all links')
    scout_parser.add_argument('--user', type=str, help='deep scrape specific github user')
    scout_parser.add_argument('--lost', action='store_true', help='show lost builder stats')

    # match command
    match_parser = subparsers.add_parser('match', help='find and rank matches')
    match_parser.add_argument('--top', type=int, help='show top N matches')
    match_parser.add_argument('--mine', action='store_true', help='show YOUR matches')
    match_parser.add_argument('--lost', action='store_true', help='find matches for lost builders')
    match_parser.add_argument('--min-score', type=int, default=30, help='min human score')
    match_parser.add_argument('--min-overlap', type=int, default=20, help='min overlap score')

    # intro command
    intro_parser = subparsers.add_parser('intro', help='generate intro drafts')
    intro_parser.add_argument('--match', type=int, help='specific match id')
    intro_parser.add_argument('--limit', type=int, default=10, help='number of matches')
    intro_parser.add_argument('--dry-run', action='store_true', help='preview only, do not save')
    intro_parser.add_argument('--lost', action='store_true', help='generate intros for lost builders')

    # lost command - show lost builders ready for outreach
    lost_parser = subparsers.add_parser('lost', help='show lost builders who need encouragement')
    lost_parser.add_argument('--min-score', type=int, default=40, help='min lost score')
    lost_parser.add_argument('--limit', type=int, default=50, help='max results')
    lost_parser.add_argument('--verbose', '-v', action='store_true', help='show philosophy')

    # review command
    review_parser = subparsers.add_parser('review', help='review intro queue')

    # send command
    send_parser = subparsers.add_parser('send', help='send approved intros')
    send_parser.add_argument('--export', type=str, help='export to file for manual sending')

    # status command
    status_parser = subparsers.add_parser('status', help='show stats')

    # daemon command
    daemon_parser = subparsers.add_parser('daemon', help='run as continuous daemon')
    daemon_parser.add_argument('--oneshot', action='store_true', help='run once then exit')
    daemon_parser.add_argument('--dry-run', action='store_true', help='preview intros, do not send')

    # user command
    user_parser = subparsers.add_parser('user', help='manage priority user profile')
    user_parser.add_argument('--setup', action='store_true', help='setup/update profile')
    user_parser.add_argument('--matches', action='store_true', help='show your matches')

    # me command - auto score + match + optional groq intros
    me_parser = subparsers.add_parser('me', help='auto-score and match yourself')
    me_parser.add_argument('--groq', action='store_true', help='generate groq llama intro drafts')
    me_parser.add_argument('--skip-scrape', action='store_true', help='skip github scraping')
    me_parser.add_argument('--min-overlap', type=int, default=40, help='min overlap score')
    me_parser.add_argument('--limit', type=int, default=10, help='number of matches to show')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # init database
    db = Database()

    try:
        if args.command == 'scout':
            cmd_scout(args, db)
        elif args.command == 'match':
            cmd_match(args, db)
        elif args.command == 'intro':
            cmd_intro(args, db)
        elif args.command == 'review':
            cmd_review(args, db)
        elif args.command == 'send':
            cmd_send(args, db)
        elif args.command == 'status':
            cmd_status(args, db)
        elif args.command == 'daemon':
            cmd_daemon(args, db)
        elif args.command == 'user':
            cmd_user(args, db)
        elif args.command == 'me':
            cmd_me(args, db)
        elif args.command == 'lost':
            cmd_lost(args, db)
    finally:
        db.close()


if __name__ == '__main__':
    main()
