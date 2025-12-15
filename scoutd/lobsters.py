"""
scoutd/lobsters.py - lobste.rs discovery
high-signal invite-only tech community
"""

import requests
import json
import time
from datetime import datetime
from pathlib import Path

from .signals import analyze_text

HEADERS = {'User-Agent': 'connectd/1.0', 'Accept': 'application/json'}
CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'lobsters'

ALIGNED_TAGS = ['privacy', 'security', 'distributed', 'rust', 'linux', 'culture', 'practices']


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

    time.sleep(2)

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        cache_file.write_text(json.dumps({'_cached_at': time.time(), '_data': result}))
        return result
    except requests.exceptions.RequestException as e:
        print(f"  lobsters api error: {e}")
        return None


def get_stories_by_tag(tag):
    """get recent stories by tag"""
    url = f'https://lobste.rs/t/{tag}.json'
    return _api_get(url) or []


def get_newest_stories():
    """get newest stories"""
    return _api_get('https://lobste.rs/newest.json') or []


def get_user(username):
    """get user profile"""
    return _api_get(f'https://lobste.rs/u/{username}.json')


def analyze_lobsters_user(username):
    """analyze a lobste.rs user"""
    user = get_user(username)
    if not user:
        return None

    text_parts = []
    if user.get('about'):
        text_parts.append(user['about'])

    full_text = ' '.join(text_parts)
    text_score, positive_signals, negative_signals = analyze_text(full_text)

    # lobsters base bonus (invite-only, high signal)
    base_score = 15

    # karma bonus
    karma = user.get('karma', 0)
    karma_score = 0
    if karma > 100:
        karma_score = 10
    elif karma > 50:
        karma_score = 5

    # github presence
    github_score = 5 if user.get('github_username') else 0

    # homepage
    homepage_score = 5 if user.get('homepage') else 0

    total_score = text_score + base_score + karma_score + github_score + homepage_score

    # confidence
    confidence = 0.4  # higher base for invite-only
    if text_parts:
        confidence += 0.2
    if karma > 50:
        confidence += 0.2
    confidence = min(confidence, 0.9)

    reasons = ['on lobste.rs (invite-only)']
    if karma > 50:
        reasons.append(f"active ({karma} karma)")
    if positive_signals:
        reasons.append(f"signals: {', '.join(positive_signals[:5])}")
    if negative_signals:
        reasons.append(f"WARNING: {', '.join(negative_signals)}")

    return {
        'platform': 'lobsters',
        'username': username,
        'url': f"https://lobste.rs/u/{username}",
        'score': total_score,
        'confidence': confidence,
        'signals': positive_signals,
        'negative_signals': negative_signals,
        'karma': karma,
        'reasons': reasons,
        'contact': {
            'github': user.get('github_username'),
            'twitter': user.get('twitter_username'),
            'homepage': user.get('homepage'),
        },
        'scraped_at': datetime.now().isoformat(),
    }


def scrape_lobsters(db):
    """full lobste.rs scrape"""
    print("scoutd/lobsters: starting scrape...")

    all_users = set()

    # stories by aligned tags
    for tag in ALIGNED_TAGS:
        print(f"  tag: {tag}...")
        stories = get_stories_by_tag(tag)
        for story in stories:
            submitter = story.get('submitter_user', {}).get('username')
            if submitter:
                all_users.add(submitter)

    # newest stories
    print("  newest stories...")
    for story in get_newest_stories():
        submitter = story.get('submitter_user', {}).get('username')
        if submitter:
            all_users.add(submitter)

    print(f"  {len(all_users)} unique users to analyze")

    # analyze
    results = []
    for username in all_users:
        try:
            result = analyze_lobsters_user(username)
            if result and result['score'] > 0:
                results.append(result)
                db.save_human(result)

                if result['score'] >= 30:
                    print(f"    ★ {username}: {result['score']} pts")
        except Exception as e:
            print(f"    error on {username}: {e}")

    print(f"scoutd/lobsters: found {len(results)} aligned humans")
    return results
