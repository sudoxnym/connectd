"""
scoutd/bluesky.py - bluesky/atproto discovery

bluesky has an open API via AT Protocol - no auth needed for public data
many twitter refugees landed here, good source for aligned builders
"""

import requests
import json
import time
from datetime import datetime
from pathlib import Path

from .signals import analyze_text

HEADERS = {'User-Agent': 'connectd/1.0', 'Accept': 'application/json'}
CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'bluesky'

# public bluesky API
BSKY_API = 'https://public.api.bsky.app'

# hashtags to search
ALIGNED_HASHTAGS = [
    'selfhosted', 'homelab', 'homeassistant', 'foss', 'opensource',
    'privacy', 'solarpunk', 'cooperative', 'mutualaid', 'localfirst',
    'indieweb', 'smallweb', 'permacomputing', 'techworkers', 'coops',
]


def _api_get(endpoint, params=None):
    """rate-limited API request with caching"""
    url = f"{BSKY_API}{endpoint}"
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

    time.sleep(0.5)  # rate limit

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        cache_file.write_text(json.dumps({'_cached_at': time.time(), '_data': result}))
        return result
    except requests.exceptions.RequestException as e:
        print(f"  bluesky api error: {e}")
        return None


def search_posts(query, limit=50):
    """search for posts containing query"""
    result = _api_get('/xrpc/app.bsky.feed.searchPosts', {
        'q': query,
        'limit': min(limit, 100),
    })

    if not result:
        return []

    posts = result.get('posts', [])
    return posts


def get_profile(handle):
    """get user profile by handle (e.g., user.bsky.social)"""
    result = _api_get('/xrpc/app.bsky.actor.getProfile', {'actor': handle})
    return result


def get_author_feed(handle, limit=30):
    """get user's recent posts"""
    result = _api_get('/xrpc/app.bsky.feed.getAuthorFeed', {
        'actor': handle,
        'limit': limit,
    })

    if not result:
        return []

    return result.get('feed', [])


def analyze_bluesky_user(handle):
    """analyze a bluesky user for alignment"""
    profile = get_profile(handle)
    if not profile:
        return None

    # collect text
    text_parts = []

    # bio/description
    description = profile.get('description', '')
    if description:
        text_parts.append(description)

    display_name = profile.get('displayName', '')
    if display_name:
        text_parts.append(display_name)

    # recent posts
    feed = get_author_feed(handle, limit=20)
    for item in feed:
        post = item.get('post', {})
        record = post.get('record', {})
        text = record.get('text', '')
        if text:
            text_parts.append(text)

    full_text = ' '.join(text_parts)
    text_score, positive_signals, negative_signals = analyze_text(full_text)

    # bluesky bonus (decentralized, values-aligned platform choice)
    platform_bonus = 10
    total_score = text_score + platform_bonus

    # activity bonus
    followers = profile.get('followersCount', 0)
    posts_count = profile.get('postsCount', 0)

    if posts_count >= 100:
        total_score += 5
    if followers >= 100:
        total_score += 5

    # confidence
    confidence = 0.35  # base for bluesky (better signal than twitter)
    if len(text_parts) > 5:
        confidence += 0.2
    if len(positive_signals) >= 3:
        confidence += 0.2
    if posts_count >= 50:
        confidence += 0.1
    confidence = min(confidence, 0.85)

    reasons = ['on bluesky (atproto)']
    if positive_signals:
        reasons.append(f"signals: {', '.join(positive_signals[:5])}")
    if negative_signals:
        reasons.append(f"WARNING: {', '.join(negative_signals)}")

    return {
        'platform': 'bluesky',
        'username': handle,
        'url': f"https://bsky.app/profile/{handle}",
        'name': display_name or handle,
        'bio': description,
        'score': total_score,
        'confidence': confidence,
        'signals': positive_signals,
        'negative_signals': negative_signals,
        'followers': followers,
        'posts_count': posts_count,
        'reasons': reasons,
        'contact': {
            'bluesky': handle,
        },
        'scraped_at': datetime.now().isoformat(),
    }


def scrape_bluesky(db, limit_per_hashtag=30):
    """full bluesky scrape"""
    print("scoutd/bluesky: starting scrape...")

    all_users = {}

    for hashtag in ALIGNED_HASHTAGS:
        print(f"  #{hashtag}...")

        # search for hashtag
        posts = search_posts(f"#{hashtag}", limit=limit_per_hashtag)

        for post in posts:
            author = post.get('author', {})
            handle = author.get('handle')

            if handle and handle not in all_users:
                all_users[handle] = {
                    'handle': handle,
                    'display_name': author.get('displayName'),
                    'hashtags': [hashtag],
                }
            elif handle:
                all_users[handle]['hashtags'].append(hashtag)

        print(f"    found {len(posts)} posts")

    # prioritize users in multiple hashtags
    multi_hashtag = {h: d for h, d in all_users.items() if len(d.get('hashtags', [])) >= 2}
    print(f"  {len(multi_hashtag)} users in 2+ aligned hashtags")

    # analyze
    results = []
    for handle in list(multi_hashtag.keys())[:100]:
        try:
            result = analyze_bluesky_user(handle)
            if result and result['score'] > 0:
                results.append(result)
                db.save_human(result)

                if result['score'] >= 30:
                    print(f"    ★ @{handle}: {result['score']} pts")
        except Exception as e:
            print(f"    error on {handle}: {e}")

    print(f"scoutd/bluesky: found {len(results)} aligned humans")
    return results
