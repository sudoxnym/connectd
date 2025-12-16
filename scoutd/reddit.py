"""
scoutd/reddit.py - reddit discovery with TAVILY web search

CRITICAL: always quote usernames in tavily searches to avoid fuzzy matching
"""

import requests
import json
import time
import re
import os
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

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY', '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')


def _api_get(url, params=None, headers=None):
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
    req_headers = {**HEADERS, **(headers or {})}
    try:
        resp = requests.get(url, headers=req_headers, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        cache_file.write_text(json.dumps({'_cached_at': time.time(), '_data': result}))
        return result
    except:
        return None


def tavily_search(query, max_results=10):
    if not TAVILY_API_KEY:
        return []
    try:
        resp = requests.post(
            'https://api.tavily.com/search',
            json={'api_key': TAVILY_API_KEY, 'query': query, 'max_results': max_results},
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json().get('results', [])
    except Exception as e:
        print(f"      tavily error: {e}")
    return []


def extract_links_from_text(text, username=None):
    found = {}
    if not text:
        return found
    text_lower = text.lower()
    username_lower = username.lower() if username else None
    
    # email
    for email in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text):
        if any(x in email.lower() for x in ['noreply', 'example', '@reddit', 'info@', 'support@', 'contact@', 'admin@']):
            continue
        if username_lower and username_lower in email.lower():
            found['email'] = email
            break
        if 'email' not in found:
            found['email'] = email
    
    # github
    for gh in re.findall(r'github\.com/([a-zA-Z0-9_-]+)', text):
        if gh.lower() in ['topics', 'explore', 'trending', 'sponsors', 'orgs']:
            continue
        if username_lower and gh.lower() == username_lower:
            found['github'] = gh
            break
    
    # mastodon
    masto = re.search(r'@([a-zA-Z0-9_]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
    if masto:
        found['mastodon'] = f"@{masto.group(1)}@{masto.group(2)}"
    for inst in ['mastodon.social', 'fosstodon.org', 'hachyderm.io', 'tech.lgbt']:
        m = re.search(f'{inst}/@([a-zA-Z0-9_]+)', text)
        if m:
            found['mastodon'] = f"@{m.group(1)}@{inst}"
            break
    
    # bluesky
    bsky = re.search(r'bsky\.app/profile/([a-zA-Z0-9_.-]+)', text)
    if bsky:
        found['bluesky'] = bsky.group(1)
    
    # twitter
    tw = re.search(r'(?:twitter|x)\.com/([a-zA-Z0-9_]+)', text)
    if tw and tw.group(1).lower() not in ['home', 'explore', 'search']:
        found['twitter'] = tw.group(1)
    
    # linkedin
    li = re.search(r'linkedin\.com/in/([a-zA-Z0-9_-]+)', text)
    if li:
        found['linkedin'] = f"https://linkedin.com/in/{li.group(1)}"
    
    # twitch
    twitch = re.search(r'twitch\.tv/([a-zA-Z0-9_]+)', text)
    if twitch:
        found['twitch'] = f"https://twitch.tv/{twitch.group(1)}"
    
    # itch.io
    itch = re.search(r'itch\.io/profile/([a-zA-Z0-9_-]+)', text)
    if itch:
        found['itch'] = f"https://itch.io/profile/{itch.group(1)}"
    
    # website
    for url in re.findall(r'https?://([a-zA-Z0-9_-]+\.[a-zA-Z]{2,}[a-zA-Z0-9./_-]*)', text):
        skip = ['reddit', 'imgur', 'google', 'facebook', 'twitter', 'youtube', 'wikipedia', 'amazon']
        if not any(x in url.lower() for x in skip):
            if username_lower and username_lower in url.lower():
                found['website'] = f"https://{url}"
                break
            if 'website' not in found:
                found['website'] = f"https://{url}"
    
    return found


def cross_platform_discovery(username, full_text=''):
    """
    search the ENTIRE internet using TAVILY.
    CRITICAL: always quote username to avoid fuzzy matching!
    """
    found = {}
    all_content = full_text
    username_lower = username.lower()
    
    print(f"    🔍 cross-platform search for {username}...")
    
    # ALWAYS QUOTE THE USERNAME - critical for exact matching
    searches = [
        f'"{username}"',                          # just username, quoted
        f'"{username}" github',                   # github
        f'"{username}" developer programmer',     # dev context
        f'"{username}" email contact',            # contact
        f'"{username}" mastodon',                 # fediverse
    ]
    
    for query in searches:
        print(f"      🌐 tavily: {query}")
        results = tavily_search(query, max_results=5)
        
        for result in results:
            url = result.get('url', '').lower()
            title = result.get('title', '')
            content = result.get('content', '')
            combined = f"{url} {title} {content}"
            
            # validate username appears
            if username_lower not in combined.lower():
                continue
            
            all_content += f" {combined}"
            
            # extract from URL directly
            if f'github.com/{username_lower}' in url and not found.get('github'):
                found['github'] = username
                print(f"        ✓ github: {username}")
            
            if f'twitch.tv/{username_lower}' in url and not found.get('twitch'):
                found['twitch'] = f"https://twitch.tv/{username}"
                print(f"        ✓ twitch")
            
            if 'itch.io/profile/' in url and username_lower in url and not found.get('itch'):
                found['itch'] = url if url.startswith('http') else f"https://{url}"
                print(f"        ✓ itch.io")
            
            if 'linkedin.com/in/' in url and not found.get('linkedin'):
                li = re.search(r'linkedin\.com/in/([a-zA-Z0-9_-]+)', url)
                if li:
                    found['linkedin'] = f"https://linkedin.com/in/{li.group(1)}"
                    print(f"        ✓ linkedin")
        
        # extract from content
        extracted = extract_links_from_text(all_content, username)
        for k, v in extracted.items():
            if k not in found:
                found[k] = v
                print(f"        ✓ {k}")
        
        # good contact found? stop searching
        if found.get('email') or found.get('github') or found.get('mastodon') or found.get('twitch'):
            break
    
    # === API CHECKS ===
    if not found.get('github'):
        headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}
        try:
            resp = requests.get(f'https://api.github.com/users/{username}', headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                found['github'] = username
                print(f"        ✓ github API")
                if data.get('email') and 'email' not in found:
                    found['email'] = data['email']
                if data.get('blog') and 'website' not in found:
                    found['website'] = data['blog'] if data['blog'].startswith('http') else f"https://{data['blog']}"
        except:
            pass
    
    if not found.get('mastodon'):
        for inst in ['mastodon.social', 'fosstodon.org', 'hachyderm.io', 'tech.lgbt']:
            try:
                resp = requests.get(f'https://{inst}/api/v1/accounts/lookup', params={'acct': username}, timeout=5)
                if resp.status_code == 200:
                    found['mastodon'] = f"@{username}@{inst}"
                    print(f"        ✓ mastodon: {found['mastodon']}")
                    break
            except:
                continue
    
    if not found.get('bluesky'):
        try:
            resp = requests.get('https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile', 
                              params={'actor': f'{username}.bsky.social'}, timeout=10)
            if resp.status_code == 200:
                found['bluesky'] = resp.json().get('handle')
                print(f"        ✓ bluesky")
        except:
            pass
    
    return found


def get_user_profile(username):
    url = f'https://www.reddit.com/user/{username}/about.json'
    data = _api_get(url)
    if not data or 'data' not in data:
        return None
    profile = data['data']
    return {
        'username': username,
        'bio': profile.get('subreddit', {}).get('public_description', ''),
        'title': profile.get('subreddit', {}).get('title', ''),
        'total_karma': profile.get('total_karma', 0),
    }


def get_subreddit_users(subreddit, limit=100):
    users = set()
    for endpoint in ['new', 'comments']:
        url = f'https://www.reddit.com/r/{subreddit}/{endpoint}.json'
        data = _api_get(url, {'limit': limit})
        if data and 'data' in data:
            for item in data['data'].get('children', []):
                author = item['data'].get('author')
                if author and author not in ['[deleted]', 'AutoModerator']:
                    users.add(author)
    return users


def get_user_activity(username):
    activity = []
    for endpoint in ['submitted', 'comments']:
        url = f'https://www.reddit.com/user/{username}/{endpoint}.json'
        data = _api_get(url, {'limit': 100})
        if data and 'data' in data:
            for item in data['data'].get('children', []):
                activity.append({
                    'type': 'post' if endpoint == 'submitted' else 'comment',
                    'subreddit': item['data'].get('subreddit'),
                    'title': item['data'].get('title', ''),
                    'body': item['data'].get('selftext', '') or item['data'].get('body', ''),
                    'score': item['data'].get('score', 0),
                })
    return activity


def analyze_reddit_user(username):
    activity = get_user_activity(username)
    if not activity:
        return None

    profile = get_user_profile(username)
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

    external_links = {}
    if profile:
        external_links.update(extract_links_from_text(f"{profile.get('bio', '')} {profile.get('title', '')}", username))
    external_links.update(extract_links_from_text(full_text, username))

    # TAVILY search
    discovered = cross_platform_discovery(username, full_text)
    external_links.update(discovered)

    # scoring
    sub_score = 0
    aligned_subs = []
    for sub, count in sub_activity.items():
        weight = ALIGNED_SUBREDDITS.get(sub, 0)
        if weight > 0:
            sub_score += weight * min(count, 5)
            aligned_subs.append(sub)

    if len(aligned_subs) >= 5:
        sub_score += 30
    elif len(aligned_subs) >= 3:
        sub_score += 15

    for sub in sub_activity:
        if sub.lower() in [n.lower() for n in NEGATIVE_SUBREDDITS]:
            sub_score -= 50
            negative_signals.append(f"r/{sub}")

    total_score = text_score + sub_score

    if external_links.get('github'):
        total_score += 10
        positive_signals.append('github')
    if external_links.get('mastodon'):
        total_score += 10
        positive_signals.append('mastodon')
    if external_links.get('email'):
        total_score += 15
        positive_signals.append('email')
    if external_links.get('twitch'):
        total_score += 5
        positive_signals.append('twitch')

    # lost builder
    subreddits_list = list(sub_activity.keys())
    lost_signals, lost_weight = analyze_reddit_for_lost_signals(activity, subreddits_list)
    text_lost_signals, _ = analyze_text_for_lost_signals(full_text)
    for sig in text_lost_signals:
        if sig not in lost_signals:
            lost_signals.append(sig)

    builder_activity = 20 if external_links.get('github') else 0
    user_type = classify_user(lost_weight, builder_activity, total_score)

    confidence = min(0.95, 0.3 + (0.2 if len(activity) > 20 else 0) + (0.2 if len(aligned_subs) >= 2 else 0) + (0.1 if external_links else 0))

    reddit_only = not any([external_links.get(k) for k in ['github', 'mastodon', 'bluesky', 'email', 'matrix', 'linkedin', 'twitch', 'itch']])

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
        'reasons': [f"contact: {', '.join(external_links.keys())}"] if external_links else [],
        'scraped_at': datetime.now().isoformat(),
        'external_links': external_links,
        'reddit_only': reddit_only,
        'extra': external_links,
        'lost_potential_score': lost_weight,
        'lost_signals': lost_signals,
        'user_type': user_type,
    }


def scrape_reddit(db, limit_per_sub=50):
    print("scoutd/reddit: scraping (TAVILY enabled)...")
    user_subs = defaultdict(set)
    for sub in ['intentionalcommunity', 'cohousing', 'selfhosted', 'homeassistant', 'solarpunk', 'cooperatives', 'privacy', 'localllama', 'homelab', 'learnprogramming']:
        users = get_subreddit_users(sub, limit=limit_per_sub)
        for user in users:
            user_subs[user].add(sub)

    multi_sub = {u: subs for u, subs in user_subs.items() if len(subs) >= 2}
    print(f"  {len(multi_sub)} users in 2+ subs")

    results = []
    for username in multi_sub:
        try:
            result = analyze_reddit_user(username)
            if result and result['score'] > 0:
                results.append(result)
                db.save_human(result)
        except Exception as e:
            print(f"  error: {username}: {e}")

    print(f"scoutd/reddit: {len(results)} humans")
    return results


def _add_to_manual_queue(result):
    queue_file = Path(__file__).parent.parent / 'data' / 'manual_queue.json'
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    queue = json.loads(queue_file.read_text()) if queue_file.exists() else []
    if not any(q.get('username') == result['username'] for q in queue):
        queue.append({'platform': 'reddit', 'username': result['username'], 'url': result['url'], 'score': result['score'], 'queued_at': datetime.now().isoformat()})
        queue_file.write_text(json.dumps(queue, indent=2))
