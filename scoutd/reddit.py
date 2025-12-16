"""
scoutd/reddit.py - reddit discovery (DISCOVERY ONLY, NOT OUTREACH)

reddit is a SIGNAL SOURCE, not a contact channel.
flow:
1. scrape reddit for users active in target subs
2. extract their reddit profile
3. look for links TO other platforms (github, mastodon, website, etc.)
4. add to scout database with reddit as signal source
5. reach out via their OTHER platforms, never reddit

if reddit user has no external links:
   - add to manual_queue with note "reddit-only, needs manual review"

also detects lost builders - stuck in learnprogramming for years, imposter syndrome, etc.
"""

import requests
import json
import time
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from .signals import analyze_text, ALIGNED_SUBREDDITS, NEGATIVE_SUBREDDITS
from .lost import (
    analyze_reddit_for_lost_signals,
    analyze_text_for_lost_signals,
    classify_user,
    get_signal_descriptions,
    STUCK_SUBREDDITS,
)

HEADERS = {'User-Agent': 'connectd:v1.0 (community discovery)'}
CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'reddit'

# patterns for extracting external platform links
PLATFORM_PATTERNS = {
    'github': [
        r'github\.com/([a-zA-Z0-9_-]+)',
        r'gh:\s*@?([a-zA-Z0-9_-]+)',
    ],
    'mastodon': [
        r'@([a-zA-Z0-9_]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'mastodon\.social/@([a-zA-Z0-9_]+)',
        r'fosstodon\.org/@([a-zA-Z0-9_]+)',
        r'hachyderm\.io/@([a-zA-Z0-9_]+)',
        r'tech\.lgbt/@([a-zA-Z0-9_]+)',
    ],
    'twitter': [
        r'twitter\.com/([a-zA-Z0-9_]+)',
        r'x\.com/([a-zA-Z0-9_]+)',
        r'(?:^|\s)@([a-zA-Z0-9_]{1,15})(?:\s|$)',  # bare @handle
    ],
    'bluesky': [
        r'bsky\.app/profile/([a-zA-Z0-9_.-]+)',
        r'([a-zA-Z0-9_-]+)\.bsky\.social',
    ],
    'website': [
        r'https?://([a-zA-Z0-9_-]+\.[a-zA-Z]{2,}[a-zA-Z0-9./_-]*)',
    ],
    'matrix': [
        r'@([a-zA-Z0-9_-]+):([a-zA-Z0-9.-]+)',
    ],
}


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

    time.sleep(2)  # reddit rate limit

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        cache_file.write_text(json.dumps({'_cached_at': time.time(), '_data': result}))
        return result
    except requests.exceptions.RequestException as e:
        print(f"  reddit api error: {e}")
        return None


def extract_external_links(text):
    """extract links to other platforms from text"""
    links = {}

    if not text:
        return links

    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                if platform == 'mastodon' and isinstance(matches[0], tuple):
                    # full fediverse handle
                    links[platform] = f"@{matches[0][0]}@{matches[0][1]}"
                elif platform == 'matrix' and isinstance(matches[0], tuple):
                    links[platform] = f"@{matches[0][0]}:{matches[0][1]}"
                elif platform == 'website':
                    # skip reddit/imgur/etc
                    for match in matches:
                        if not any(x in match.lower() for x in ['reddit', 'imgur', 'redd.it', 'i.redd']):
                            links[platform] = f"https://{match}"
                            break
                else:
                    links[platform] = matches[0]
                break

    return links


def get_user_profile(username):
    """get user profile including bio/description"""
    url = f'https://www.reddit.com/user/{username}/about.json'
    data = _api_get(url)

    if not data or 'data' not in data:
        return None

    profile = data['data']
    return {
        'username': username,
        'name': profile.get('name'),
        'bio': profile.get('subreddit', {}).get('public_description', ''),
        'title': profile.get('subreddit', {}).get('title', ''),
        'icon': profile.get('icon_img'),
        'created_utc': profile.get('created_utc'),
        'total_karma': profile.get('total_karma', 0),
        'link_karma': profile.get('link_karma', 0),
        'comment_karma': profile.get('comment_karma', 0),
    }


def get_subreddit_users(subreddit, limit=100):
    """get recent posters/commenters from a subreddit"""
    users = set()

    # posts
    url = f'https://www.reddit.com/r/{subreddit}/new.json'
    data = _api_get(url, {'limit': limit})
    if data and 'data' in data:
        for post in data['data'].get('children', []):
            author = post['data'].get('author')
            if author and author not in ['[deleted]', 'AutoModerator']:
                users.add(author)

    # comments
    url = f'https://www.reddit.com/r/{subreddit}/comments.json'
    data = _api_get(url, {'limit': limit})
    if data and 'data' in data:
        for comment in data['data'].get('children', []):
            author = comment['data'].get('author')
            if author and author not in ['[deleted]', 'AutoModerator']:
                users.add(author)

    return users


def get_user_activity(username):
    """get user's posts and comments"""
    activity = []

    # posts
    url = f'https://www.reddit.com/user/{username}/submitted.json'
    data = _api_get(url, {'limit': 100})
    if data and 'data' in data:
        for post in data['data'].get('children', []):
            activity.append({
                'type': 'post',
                'subreddit': post['data'].get('subreddit'),
                'title': post['data'].get('title', ''),
                'body': post['data'].get('selftext', ''),
                'score': post['data'].get('score', 0),
            })

    # comments
    url = f'https://www.reddit.com/user/{username}/comments.json'
    data = _api_get(url, {'limit': 100})
    if data and 'data' in data:
        for comment in data['data'].get('children', []):
            activity.append({
                'type': 'comment',
                'subreddit': comment['data'].get('subreddit'),
                'body': comment['data'].get('body', ''),
                'score': comment['data'].get('score', 0),
            })

    return activity


def analyze_reddit_user(username):
    """
    analyze a reddit user for alignment and extract external platform links.

    reddit is DISCOVERY ONLY - we find users here but contact them elsewhere.
    """
    activity = get_user_activity(username)
    if not activity:
        return None

    # get profile for bio
    profile = get_user_profile(username)

    # count subreddit activity
    sub_activity = defaultdict(int)
    text_parts = []
    total_karma = 0

    for item in activity:
        sub = item.get('subreddit', '').lower()
        if sub:
            sub_activity[sub] += 1
        if item.get('title'):
            text_parts.append(item['title'])
        if item.get('body'):
            text_parts.append(item['body'])
        total_karma += item.get('score', 0)

    full_text = ' '.join(text_parts)
    text_score, positive_signals, negative_signals = analyze_text(full_text)

    # EXTRACT EXTERNAL LINKS - this is the key part
    # check profile bio first
    external_links = {}
    if profile:
        bio_text = f"{profile.get('bio', '')} {profile.get('title', '')}"
        external_links.update(extract_external_links(bio_text))

    # also scan posts/comments for links (people often share their github etc)
    activity_links = extract_external_links(full_text)
    for platform, link in activity_links.items():
        if platform not in external_links:
            external_links[platform] = link

    # subreddit scoring
    sub_score = 0
    aligned_subs = []
    for sub, count in sub_activity.items():
        weight = ALIGNED_SUBREDDITS.get(sub, 0)
        if weight > 0:
            sub_score += weight * min(count, 5)
            aligned_subs.append(sub)

    # multi-sub bonus
    if len(aligned_subs) >= 5:
        sub_score += 30
    elif len(aligned_subs) >= 3:
        sub_score += 15

    # negative sub penalty
    for sub in sub_activity:
        if sub.lower() in [n.lower() for n in NEGATIVE_SUBREDDITS]:
            sub_score -= 50
            negative_signals.append(f"r/{sub}")

    total_score = text_score + sub_score

    # bonus if they have external links (we can actually contact them)
    if external_links.get('github'):
        total_score += 10
        positive_signals.append('has github')
    if external_links.get('mastodon'):
        total_score += 10
        positive_signals.append('has mastodon')
    if external_links.get('website'):
        total_score += 5
        positive_signals.append('has website')

    # === LOST BUILDER DETECTION ===
    # reddit is HIGH SIGNAL for lost builders - stuck in learnprogramming,
    # imposter syndrome posts, "i wish i could" language, etc.
    subreddits_list = list(sub_activity.keys())
    lost_signals, lost_weight = analyze_reddit_for_lost_signals(activity, subreddits_list)

    # also check full text for lost patterns (already done partially in analyze_reddit_for_lost_signals)
    text_lost_signals, text_lost_weight = analyze_text_for_lost_signals(full_text)
    for sig in text_lost_signals:
        if sig not in lost_signals:
            lost_signals.append(sig)
            lost_weight += text_lost_weight

    lost_potential_score = lost_weight

    # classify: builder, lost, both, or none
    # for reddit, builder_score is based on having external links + high karma
    builder_activity = 0
    if external_links.get('github'):
        builder_activity += 20
    if total_karma > 1000:
        builder_activity += 15
    elif total_karma > 500:
        builder_activity += 10

    user_type = classify_user(lost_potential_score, builder_activity, total_score)

    # confidence
    confidence = 0.3
    if len(activity) > 20:
        confidence += 0.2
    if len(aligned_subs) >= 2:
        confidence += 0.2
    if len(text_parts) > 10:
        confidence += 0.2
    # higher confidence if we have contact methods
    if external_links:
        confidence += 0.1
    confidence = min(confidence, 0.95)

    reasons = []
    if aligned_subs:
        reasons.append(f"active in: {', '.join(aligned_subs[:5])}")
    if positive_signals:
        reasons.append(f"signals: {', '.join(positive_signals[:5])}")
    if negative_signals:
        reasons.append(f"WARNING: {', '.join(negative_signals)}")
    if external_links:
        reasons.append(f"external: {', '.join(external_links.keys())}")

    # add lost reasons if applicable
    if user_type == 'lost' or user_type == 'both':
        lost_descriptions = get_signal_descriptions(lost_signals)
        if lost_descriptions:
            reasons.append(f"LOST SIGNALS: {', '.join(lost_descriptions[:3])}")

    # determine if this is reddit-only (needs manual review)
    reddit_only = len(external_links) == 0
    if reddit_only:
        reasons.append("REDDIT-ONLY: needs manual review for outreach")

    return {
        'platform': 'reddit',
        'username': username,
        'url': f"https://reddit.com/u/{username}",
        'score': total_score,
        'confidence': confidence,
        'signals': positive_signals,
        'negative_signals': negative_signals,
        'subreddits': aligned_subs,
        'activity_count': len(activity),
        'karma': total_karma,
        'reasons': reasons,
        'scraped_at': datetime.now().isoformat(),
        # external platform links for outreach
        'external_links': external_links,
        'reddit_only': reddit_only,
        'extra': {
            'github': external_links.get('github'),
            'mastodon': external_links.get('mastodon'),
            'twitter': external_links.get('twitter'),
            'bluesky': external_links.get('bluesky'),
            'website': external_links.get('website'),
            'matrix': external_links.get('matrix'),
            'reddit_karma': total_karma,
            'reddit_activity': len(activity),
        },
        # lost builder fields
        'lost_potential_score': lost_potential_score,
        'lost_signals': lost_signals,
        'user_type': user_type,
    }


def scrape_reddit(db, limit_per_sub=50):
    """
    full reddit scrape - DISCOVERY ONLY

    finds aligned users, extracts external links for outreach.
    reddit-only users go to manual queue.
    """
    print("scoutd/reddit: starting scrape (discovery only, not outreach)...")

    # find users in multiple aligned subs
    user_subs = defaultdict(set)

    # aligned subs - active builders
    priority_subs = ['intentionalcommunity', 'cohousing', 'selfhosted',
                     'homeassistant', 'solarpunk', 'cooperatives', 'privacy',
                     'localllama', 'homelab', 'degoogle', 'pihole', 'unraid']

    # lost builder subs - people who need encouragement
    # these folks might be stuck, but they have aligned interests
    lost_subs = ['learnprogramming', 'findapath', 'getdisciplined',
                 'careerguidance', 'cscareerquestions', 'decidingtobebetter']

    # scrape both - we want to find lost builders with aligned interests
    all_subs = priority_subs + lost_subs

    for sub in all_subs:
        print(f"  scraping r/{sub}...")
        users = get_subreddit_users(sub, limit=limit_per_sub)
        for user in users:
            user_subs[user].add(sub)
        print(f"    found {len(users)} users")

    # filter for multi-sub users
    multi_sub = {u: subs for u, subs in user_subs.items() if len(subs) >= 2}
    print(f"  {len(multi_sub)} users in 2+ aligned subs")

    # analyze
    results = []
    reddit_only_count = 0
    external_link_count = 0
    builders_found = 0
    lost_found = 0

    for username in multi_sub:
        try:
            result = analyze_reddit_user(username)
            if result and result['score'] > 0:
                results.append(result)
                db.save_human(result)

                user_type = result.get('user_type', 'none')

                # track lost builders - reddit is high signal for these
                if user_type == 'lost':
                    lost_found += 1
                    lost_score = result.get('lost_potential_score', 0)
                    if lost_score >= 40:
                        print(f"    💔 u/{username}: lost_score={lost_score}, values={result['score']} pts")
                        # lost builders also go to manual queue if reddit-only
                        if result.get('reddit_only'):
                            _add_to_manual_queue(result)

                elif user_type == 'builder':
                    builders_found += 1

                elif user_type == 'both':
                    builders_found += 1
                    lost_found += 1
                    print(f"    ⚡ u/{username}: recovering builder")

                # track external links
                if result.get('reddit_only'):
                    reddit_only_count += 1
                    # add high-value users to manual queue for review
                    if result['score'] >= 50 and user_type != 'lost':  # lost already added above
                        _add_to_manual_queue(result)
                        print(f"    📋 u/{username}: {result['score']} pts (reddit-only → manual queue)")
                else:
                    external_link_count += 1
                    if result['score'] >= 50 and user_type == 'builder':
                        links = list(result.get('external_links', {}).keys())
                        print(f"    ★ u/{username}: {result['score']} pts → {', '.join(links)}")

        except Exception as e:
            print(f"    error on {username}: {e}")

    print(f"scoutd/reddit: found {len(results)} aligned humans")
    print(f"  - {builders_found} active builders")
    print(f"  - {lost_found} lost builders (need encouragement)")
    print(f"  - {external_link_count} with external links (reachable)")
    print(f"  - {reddit_only_count} reddit-only (manual queue)")
    return results


def _add_to_manual_queue(result):
    """add reddit-only user to manual queue for review"""
    from pathlib import Path
    import json

    queue_file = Path(__file__).parent.parent / 'data' / 'manual_queue.json'
    queue_file.parent.mkdir(parents=True, exist_ok=True)

    queue = []
    if queue_file.exists():
        try:
            queue = json.loads(queue_file.read_text())
        except:
            pass

    # check if already in queue
    existing = [q for q in queue if q.get('username') == result['username'] and q.get('platform') == 'reddit']
    if existing:
        return

    queue.append({
        'platform': 'reddit',
        'username': result['username'],
        'url': result['url'],
        'score': result['score'],
        'subreddits': result.get('subreddits', []),
        'signals': result.get('signals', []),
        'reasons': result.get('reasons', []),
        'note': 'reddit-only user - no external links found. DM manually if promising.',
        'queued_at': datetime.now().isoformat(),
        'status': 'pending',
    })

    queue_file.write_text(json.dumps(queue, indent=2))
