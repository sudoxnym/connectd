"""
scoutd/mastodon.py - fediverse discovery
scrapes high-signal instances: tech.lgbt, social.coop, fosstodon, hackers.town
also detects lost builders - social isolation, imposter syndrome, struggling folks
"""

import requests
import json
import time
import re
from datetime import datetime
from pathlib import Path

from .signals import analyze_text, ALIGNED_INSTANCES
from .lost import (
    analyze_social_for_lost_signals,
    analyze_text_for_lost_signals,
    classify_user,
    get_signal_descriptions,
)

HEADERS = {'User-Agent': 'connectd/1.0', 'Accept': 'application/json'}
CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'mastodon'

TARGET_HASHTAGS = [
    'selfhosted', 'homelab', 'homeassistant', 'foss', 'opensource',
    'privacy', 'solarpunk', 'cooperative', 'cohousing', 'mutualaid',
    'intentionalcommunity', 'degoogle', 'fediverse', 'indieweb',
]


def _api_get(url, params=None):
    """rate-limited request"""
    cache_key = f"{url}_{json.dumps(params or {}, sort_keys=True)}"
    cache_file = CACHE_DIR / f"{hash(cache_key) & 0xffffffff}.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get('_cached_at', 0) < 3600:
                return data.get('_data')
        except:
            pass

    time.sleep(1)

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        cache_file.write_text(json.dumps({'_cached_at': time.time(), '_data': result}))
        return result
    except requests.exceptions.RequestException as e:
        print(f"  mastodon api error: {e}")
        return None


def strip_html(text):
    """strip html tags"""
    return re.sub(r'<[^>]+>', ' ', text) if text else ''


def get_instance_directory(instance, limit=40):
    """get users from instance directory"""
    url = f'https://{instance}/api/v1/directory'
    return _api_get(url, {'limit': limit, 'local': 'true'}) or []


def get_hashtag_timeline(instance, hashtag, limit=40):
    """get posts from hashtag"""
    url = f'https://{instance}/api/v1/timelines/tag/{hashtag}'
    return _api_get(url, {'limit': limit}) or []


def get_user_statuses(instance, user_id, limit=30):
    """get user's recent posts"""
    url = f'https://{instance}/api/v1/accounts/{user_id}/statuses'
    return _api_get(url, {'limit': limit, 'exclude_reblogs': 'true'}) or []


def analyze_mastodon_user(account, instance):
    """analyze a mastodon account"""
    acct = account.get('acct', '')
    if '@' not in acct:
        acct = f"{acct}@{instance}"

    # collect text
    text_parts = []
    bio = strip_html(account.get('note', ''))
    if bio:
        text_parts.append(bio)

    display_name = account.get('display_name', '')
    if display_name:
        text_parts.append(display_name)

    # profile fields
    for field in account.get('fields', []):
        if field.get('name'):
            text_parts.append(field['name'])
        if field.get('value'):
            text_parts.append(strip_html(field['value']))

    # get recent posts
    user_id = account.get('id')
    if user_id:
        statuses = get_user_statuses(instance, user_id)
        for status in statuses:
            content = strip_html(status.get('content', ''))
            if content:
                text_parts.append(content)

    full_text = ' '.join(text_parts)
    text_score, positive_signals, negative_signals = analyze_text(full_text)

    # instance bonus
    instance_bonus = ALIGNED_INSTANCES.get(instance, 0)
    total_score = text_score + instance_bonus

    # pronouns bonus
    if re.search(r'\b(they/them|she/her|he/him|xe/xem)\b', full_text, re.I):
        total_score += 10
        positive_signals.append('pronouns')

    # activity level
    statuses_count = account.get('statuses_count', 0)
    followers = account.get('followers_count', 0)
    if statuses_count > 100:
        total_score += 5

    # === LOST BUILDER DETECTION ===
    # build profile and posts for lost analysis
    profile_for_lost = {
        'bio': bio,
        'note': account.get('note'),
    }

    # convert statuses to posts format for analyze_social_for_lost_signals
    posts_for_lost = []
    if user_id:
        statuses = get_user_statuses(instance, user_id)
        for status in statuses:
            posts_for_lost.append({
                'content': strip_html(status.get('content', '')),
                'reblog': status.get('reblog'),
            })

    # analyze for lost signals
    lost_signals, lost_weight = analyze_social_for_lost_signals(profile_for_lost, posts_for_lost)

    # also check combined text for lost patterns
    text_lost_signals, text_lost_weight = analyze_text_for_lost_signals(full_text)
    for sig in text_lost_signals:
        if sig not in lost_signals:
            lost_signals.append(sig)
            lost_weight += text_lost_weight

    lost_potential_score = lost_weight

    # classify: builder, lost, both, or none
    # for mastodon, we use statuses_count as a proxy for builder activity
    builder_activity = 10 if statuses_count > 100 else 5 if statuses_count > 50 else 0
    user_type = classify_user(lost_potential_score, builder_activity, total_score)

    # confidence
    confidence = 0.3
    if len(text_parts) > 5:
        confidence += 0.2
    if statuses_count > 50:
        confidence += 0.2
    if len(positive_signals) > 3:
        confidence += 0.2
    confidence = min(confidence, 0.9)

    reasons = []
    if instance in ALIGNED_INSTANCES:
        reasons.append(f"on {instance}")
    if positive_signals:
        reasons.append(f"signals: {', '.join(positive_signals[:5])}")
    if negative_signals:
        reasons.append(f"WARNING: {', '.join(negative_signals)}")

    # add lost reasons if applicable
    if user_type == 'lost' or user_type == 'both':
        lost_descriptions = get_signal_descriptions(lost_signals)
        if lost_descriptions:
            reasons.append(f"LOST SIGNALS: {', '.join(lost_descriptions[:3])}")

    return {
        'platform': 'mastodon',
        'username': acct,
        'url': account.get('url'),
        'name': display_name,
        'bio': bio,
        'instance': instance,
        'score': total_score,
        'confidence': confidence,
        'signals': positive_signals,
        'negative_signals': negative_signals,
        'statuses_count': statuses_count,
        'followers': followers,
        'reasons': reasons,
        'scraped_at': datetime.now().isoformat(),
        # lost builder fields
        'lost_potential_score': lost_potential_score,
        'lost_signals': lost_signals,
        'user_type': user_type,
    }


def scrape_mastodon(db, limit_per_instance=40):
    """full mastodon scrape"""
    print("scoutd/mastodon: starting scrape...")

    all_accounts = []

    # 1. instance directories
    print("  scraping instance directories...")
    for instance in ALIGNED_INSTANCES:
        accounts = get_instance_directory(instance, limit=limit_per_instance)
        for acct in accounts:
            acct['_instance'] = instance
            all_accounts.append(acct)
        print(f"    {instance}: {len(accounts)} users")

    # 2. hashtag timelines
    print("  scraping hashtags...")
    seen = set()
    for tag in TARGET_HASHTAGS[:8]:
        for instance in ['fosstodon.org', 'tech.lgbt', 'social.coop']:
            posts = get_hashtag_timeline(instance, tag, limit=20)
            for post in posts:
                account = post.get('account', {})
                acct = account.get('acct', '')
                if '@' not in acct:
                    acct = f"{acct}@{instance}"

                if acct not in seen:
                    seen.add(acct)
                    account['_instance'] = instance
                    all_accounts.append(account)

    # dedupe
    unique = {}
    for acct in all_accounts:
        key = acct.get('acct', acct.get('id', ''))
        if key not in unique:
            unique[key] = acct

    print(f"  {len(unique)} unique accounts to analyze")

    # analyze
    results = []
    builders_found = 0
    lost_found = 0

    for acct_data in unique.values():
        instance = acct_data.get('_instance', 'mastodon.social')
        try:
            result = analyze_mastodon_user(acct_data, instance)
            if result and result['score'] > 0:
                results.append(result)
                db.save_human(result)

                user_type = result.get('user_type', 'none')

                if user_type == 'builder':
                    builders_found += 1
                    if result['score'] >= 40:
                        print(f"    ★ @{result['username']}: {result['score']} pts")

                elif user_type == 'lost':
                    lost_found += 1
                    lost_score = result.get('lost_potential_score', 0)
                    if lost_score >= 40:
                        print(f"    💔 @{result['username']}: lost_score={lost_score}, values={result['score']} pts")

                elif user_type == 'both':
                    builders_found += 1
                    lost_found += 1
                    print(f"    ⚡ @{result['username']}: recovering builder")

        except Exception as e:
            print(f"    error: {e}")

    print(f"scoutd/mastodon: found {len(results)} aligned humans")
    print(f"  - {builders_found} active builders")
    print(f"  - {lost_found} lost builders (need encouragement)")
    return results
