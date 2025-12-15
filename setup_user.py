#!/usr/bin/env python3
"""
setup priority user - add yourself to get matches

usage:
    python setup_user.py                    # interactive setup
    python setup_user.py --show             # show your profile
    python setup_user.py --matches          # show your matches
"""

import argparse
import json
from db import Database
from db.users import (init_users_table, add_priority_user, get_priority_users,
                      get_priority_user_matches)


def interactive_setup(db):
    """interactive priority user setup"""
    print("=" * 60)
    print("connectd priority user setup")
    print("=" * 60)
    print("\nlink your profiles so connectd can find matches for YOU\n")

    name = input("name: ").strip()
    email = input("email (for notifications): ").strip()
    github = input("github username (optional): ").strip() or None
    reddit = input("reddit username (optional): ").strip() or None
    mastodon = input("mastodon handle e.g. user@instance (optional): ").strip() or None
    lobsters = input("lobste.rs username (optional): ").strip() or None
    matrix = input("matrix id e.g. @user:matrix.org (optional): ").strip() or None
    location = input("location (e.g. seattle, remote): ").strip() or None

    print("\nwhat are you interested in? (comma separated)")
    print("examples: self-hosting, cooperatives, solarpunk, home automation")
    interests_raw = input("interests: ").strip()
    interests = [i.strip() for i in interests_raw.split(',')] if interests_raw else []

    print("\nwhat kind of people are you looking to connect with?")
    looking_for = input("looking for: ").strip() or None

    user_data = {
        'name': name,
        'email': email,
        'github': github,
        'reddit': reddit,
        'mastodon': mastodon,
        'lobsters': lobsters,
        'matrix': matrix,
        'location': location,
        'interests': interests,
        'looking_for': looking_for,
    }

    user_id = add_priority_user(db.conn, user_data)
    print(f"\n✓ added as priority user #{user_id}")
    print("connectd will now find matches for you")


def show_profile(db):
    """show current priority user profile"""
    users = get_priority_users(db.conn)

    if not users:
        print("no priority users configured")
        print("run: python setup_user.py")
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
        if user['lobsters']:
            print(f"lobsters: {user['lobsters']}")
        if user['matrix']:
            print(f"matrix: {user['matrix']}")
        if user['location']:
            print(f"location: {user['location']}")
        if user['interests']:
            interests = json.loads(user['interests']) if isinstance(user['interests'], str) else user['interests']
            print(f"interests: {', '.join(interests)}")
        if user['looking_for']:
            print(f"looking for: {user['looking_for']}")


def show_matches(db):
    """show matches for priority user"""
    users = get_priority_users(db.conn)

    if not users:
        print("no priority users configured")
        return

    for user in users:
        print(f"\n=== matches for {user['name']} ===\n")

        matches = get_priority_user_matches(db.conn, user['id'], limit=20)

        if not matches:
            print("no matches yet - run the daemon to discover people")
            continue

        for i, match in enumerate(matches, 1):
            print(f"{i}. {match['username']} ({match['platform']})")
            print(f"   score: {match['overlap_score']:.0f}")
            print(f"   url: {match['url']}")

            reasons = match.get('overlap_reasons', '[]')
            if isinstance(reasons, str):
                reasons = json.loads(reasons)
            if reasons:
                print(f"   why: {reasons[0] if reasons else ''}")
            print()


def main():
    parser = argparse.ArgumentParser(description='setup priority user')
    parser.add_argument('--show', action='store_true', help='show your profile')
    parser.add_argument('--matches', action='store_true', help='show your matches')
    args = parser.parse_args()

    db = Database()
    init_users_table(db.conn)

    if args.show:
        show_profile(db)
    elif args.matches:
        show_matches(db)
    else:
        interactive_setup(db)

    db.close()


if __name__ == '__main__':
    main()
