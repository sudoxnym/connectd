"""
scoutd/lemmy.py - lemmy (fediverse reddit) discovery

lemmy is federated so we hit multiple instances.
great for finding lost builders in communities like:
- /c/programming, /c/technology, /c/linux
- /c/antiwork, /c/workreform (lost builders!)
- /c/selfhosted, /c/privacy, /c/opensource

no auth needed for public posts.
"""

import requests
import json
import time
import os
from datetime import datetime
from pathlib import Path

from .signals import analyze_text
from .lost import (
    analyze_social_for_lost_signals,
    analyze_text_for_lost_signals,
    classify_user,
)

# popular lemmy instances
LEMMY_INSTANCES = [
    'lemmy.ml',
    'lemmy.world',
    'programming.dev',
    'lemm.ee',
    'sh.itjust.works',
]

# communities to scout (format: community@instance or just community for local)
TARGET_COMMUNITIES = [
    # builder communities
    'programming',
    'selfhosted',
    'linux',
    'opensource',
    'privacy',
    'technology',
    'webdev',
    'rust',
    'python',
    'golang',

    # lost builder communities (people struggling, stuck, seeking)
    'antiwork',
    'workreform',
    'careerguidance',
    'cscareerquestions',
    'learnprogramming',
    'findapath',
]

CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'lemmy'
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_community_posts(instance, community, limit=50, sort='New'):
    """get posts from a lemmy community"""
    try:
        url = f"https://{instance}/api/v3/post/list"
        params = {
            'community_name': community,
            'sort': sort,
            'limit': limit,
        }

        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json().get('posts', [])
        return []
    except Exception as e:
        return []


def get_user_profile(instance, username):
    """get lemmy user profile"""
    try:
        url = f"https://{instance}/api/v3/user"
        params = {'username': username}

        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def analyze_lemmy_user(instance, username, posts=None):
    """analyze a lemmy user for values alignment and lost signals"""
    profile = get_user_profile(instance, username)
    if not profile:
        return None

    person = profile.get('person_view', {}).get('person', {})
    counts = profile.get('person_view', {}).get('counts', {})

    bio = person.get('bio', '') or ''
    display_name = person.get('display_name') or person.get('name', username)

    # analyze bio
    bio_score, bio_signals, bio_reasons = analyze_text(bio)

    # analyze posts if provided
    post_signals = []
    post_text = []
    if posts:
        for post in posts[:10]:
            post_data = post.get('post', {})
            title = post_data.get('name', '')
            body = post_data.get('body', '')
            post_text.append(f"{title} {body}")

            _, signals, _ = analyze_text(f"{title} {body}")
            post_signals.extend(signals)

    all_signals = list(set(bio_signals + post_signals))
    total_score = bio_score + len(post_signals) * 5

    # lost builder detection
    profile_for_lost = {
        'bio': bio,
        'post_count': counts.get('post_count', 0),
        'comment_count': counts.get('comment_count', 0),
    }
    posts_for_lost = [{'text': t} for t in post_text]

    lost_signals, lost_weight = analyze_social_for_lost_signals(profile_for_lost, posts_for_lost)
    lost_potential_score = lost_weight
    user_type = classify_user(lost_potential_score, 50, total_score)

    return {
        'platform': 'lemmy',
        'username': f"{username}@{instance}",
        'url': f"https://{instance}/u/{username}",
        'name': display_name,
        'bio': bio,
        'location': None,
        'score': total_score,
        'confidence': min(0.9, 0.3 + len(all_signals) * 0.1),
        'signals': all_signals,
        'negative_signals': [],
        'reasons': bio_reasons,
        'contact': {},
        'extra': {
            'instance': instance,
            'post_count': counts.get('post_count', 0),
            'comment_count': counts.get('comment_count', 0),
        },
        'lost_potential_score': lost_potential_score,
        'lost_signals': lost_signals,
        'user_type': user_type,
    }


def scrape_lemmy(db, limit_per_community=30):
    """scrape lemmy instances for aligned builders"""
    print("scouting lemmy...")

    found = 0
    lost_found = 0
    seen_users = set()

    for instance in LEMMY_INSTANCES:
        print(f"  instance: {instance}")

        for community in TARGET_COMMUNITIES:
            posts = get_community_posts(instance, community, limit=limit_per_community)

            if not posts:
                continue

            print(f"    /c/{community}: {len(posts)} posts")

            # group posts by user
            user_posts = {}
            for post in posts:
                creator = post.get('creator', {})
                username = creator.get('name')
                if not username:
                    continue

                user_key = f"{username}@{instance}"
                if user_key in seen_users:
                    continue

                if user_key not in user_posts:
                    user_posts[user_key] = []
                user_posts[user_key].append(post)

            # analyze each user
            for user_key, posts in user_posts.items():
                username = user_key.split('@')[0]

                if user_key in seen_users:
                    continue
                seen_users.add(user_key)

                result = analyze_lemmy_user(instance, username, posts)
                if not result:
                    continue

                if result['score'] >= 20 or result.get('lost_potential_score', 0) >= 30:
                    db.save_human(result)
                    found += 1

                    if result.get('user_type') in ['lost', 'both']:
                        lost_found += 1
                        print(f"      {result['username']}: {result['score']:.0f} (lost: {result['lost_potential_score']:.0f})")
                    elif result['score'] >= 40:
                        print(f"      {result['username']}: {result['score']:.0f}")

                time.sleep(0.5)  # rate limit

            time.sleep(1)  # between communities

        time.sleep(2)  # between instances

    print(f"lemmy: found {found} humans ({lost_found} lost builders)")
    return found
