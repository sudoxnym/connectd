"""
scoutd/twitter.py - twitter/x discovery via nitter instances

scrapes nitter (twitter frontend) to find users posting about aligned topics
without needing twitter API access

nitter instances rotate to avoid rate limits
"""

import requests
import json
import time
import re
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

from .signals import analyze_text

HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0'}
CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'twitter'

# nitter instances (rotate through these)
NITTER_INSTANCES = [
    'nitter.privacydev.net',
    'nitter.poast.org',
    'nitter.woodland.cafe',
    'nitter.esmailelbob.xyz',
]

# hashtags to search
ALIGNED_HASHTAGS = [
    'selfhosted', 'homelab', 'homeassistant', 'foss', 'opensource',
    'privacy', 'solarpunk', 'cooperative', 'mutualaid', 'localfirst',
    'indieweb', 'smallweb', 'permacomputing', 'degrowth', 'techworkers',
]

_current_instance_idx = 0


def get_nitter_instance():
    """get current nitter instance, rotate on failure"""
    global _current_instance_idx
    return NITTER_INSTANCES[_current_instance_idx % len(NITTER_INSTANCES)]


def rotate_instance():
    """switch to next nitter instance"""
    global _current_instance_idx
    _current_instance_idx += 1


def _scrape_page(url, retries=3):
    """scrape a nitter page with instance rotation"""
    for attempt in range(retries):
        instance = get_nitter_instance()
        full_url = url.replace('{instance}', instance)

        # check cache
        cache_key = f"{full_url}"
        cache_file = CACHE_DIR / f"{hash(cache_key) & 0xffffffff}.json"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                if time.time() - data.get('_cached_at', 0) < 3600:
                    return data.get('_html')
            except:
                pass

        time.sleep(2)  # rate limit

        try:
            resp = requests.get(full_url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                cache_file.write_text(json.dumps({
                    '_cached_at': time.time(),
                    '_html': resp.text
                }))
                return resp.text
            elif resp.status_code in [429, 503]:
                print(f"  nitter {instance} rate limited, rotating...")
                rotate_instance()
            else:
                print(f"  nitter error: {resp.status_code}")
                return None
        except Exception as e:
            print(f"  nitter {instance} error: {e}")
            rotate_instance()

    return None


def search_hashtag(hashtag):
    """search for tweets with hashtag"""
    url = f"https://{{instance}}/search?q=%23{hashtag}&f=tweets"
    html = _scrape_page(url)
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    tweets = []

    for tweet_div in soup.select('.timeline-item'):
        try:
            username_elem = tweet_div.select_one('.username')
            content_elem = tweet_div.select_one('.tweet-content')
            fullname_elem = tweet_div.select_one('.fullname')

            if username_elem and content_elem:
                username = username_elem.text.strip().lstrip('@')
                tweets.append({
                    'username': username,
                    'name': fullname_elem.text.strip() if fullname_elem else username,
                    'content': content_elem.text.strip(),
                })
        except Exception as e:
            continue

    return tweets


def get_user_profile(username):
    """get user profile from nitter"""
    url = f"https://{{instance}}/{username}"
    html = _scrape_page(url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')

    try:
        bio_elem = soup.select_one('.profile-bio')
        bio = bio_elem.text.strip() if bio_elem else ''

        location_elem = soup.select_one('.profile-location')
        location = location_elem.text.strip() if location_elem else ''

        website_elem = soup.select_one('.profile-website a')
        website = website_elem.get('href') if website_elem else ''

        # get recent tweets for more signal
        tweets = []
        for tweet_div in soup.select('.timeline-item')[:10]:
            content_elem = tweet_div.select_one('.tweet-content')
            if content_elem:
                tweets.append(content_elem.text.strip())

        return {
            'username': username,
            'bio': bio,
            'location': location,
            'website': website,
            'recent_tweets': tweets,
        }
    except Exception as e:
        print(f"  error parsing {username}: {e}")
        return None


def analyze_twitter_user(username, profile=None):
    """analyze a twitter user for alignment"""
    if not profile:
        profile = get_user_profile(username)

    if not profile:
        return None

    # collect text
    text_parts = [profile.get('bio', '')]
    text_parts.extend(profile.get('recent_tweets', []))

    full_text = ' '.join(text_parts)
    text_score, positive_signals, negative_signals = analyze_text(full_text)

    # twitter is noisy, lower base confidence
    confidence = 0.25
    if len(positive_signals) >= 3:
        confidence += 0.2
    if profile.get('website'):
        confidence += 0.1
    if len(profile.get('recent_tweets', [])) >= 5:
        confidence += 0.1
    confidence = min(confidence, 0.7)  # cap lower for twitter

    reasons = []
    if positive_signals:
        reasons.append(f"signals: {', '.join(positive_signals[:5])}")
    if negative_signals:
        reasons.append(f"WARNING: {', '.join(negative_signals)}")

    return {
        'platform': 'twitter',
        'username': username,
        'url': f"https://twitter.com/{username}",
        'name': profile.get('name', username),
        'bio': profile.get('bio'),
        'location': profile.get('location'),
        'score': text_score,
        'confidence': confidence,
        'signals': positive_signals,
        'negative_signals': negative_signals,
        'reasons': reasons,
        'contact': {
            'twitter': username,
            'website': profile.get('website'),
        },
        'scraped_at': datetime.now().isoformat(),
    }


def scrape_twitter(db, limit_per_hashtag=50):
    """full twitter scrape via nitter"""
    print("scoutd/twitter: starting scrape via nitter...")

    all_users = {}

    for hashtag in ALIGNED_HASHTAGS:
        print(f"  #{hashtag}...")
        tweets = search_hashtag(hashtag)

        for tweet in tweets[:limit_per_hashtag]:
            username = tweet.get('username')
            if username and username not in all_users:
                all_users[username] = {
                    'username': username,
                    'name': tweet.get('name'),
                    'hashtags': [hashtag],
                }
            elif username:
                all_users[username]['hashtags'].append(hashtag)

        print(f"    found {len(tweets)} tweets")

    # prioritize users in multiple hashtags
    multi_hashtag = {u: d for u, d in all_users.items() if len(d.get('hashtags', [])) >= 2}
    print(f"  {len(multi_hashtag)} users in 2+ aligned hashtags")

    # analyze
    results = []
    for username, data in list(multi_hashtag.items())[:100]:  # limit to prevent rate limits
        try:
            result = analyze_twitter_user(username)
            if result and result['score'] > 0:
                results.append(result)
                db.save_human(result)

                if result['score'] >= 30:
                    print(f"    ★ @{username}: {result['score']} pts")
        except Exception as e:
            print(f"    error on {username}: {e}")

    print(f"scoutd/twitter: found {len(results)} aligned humans")
    return results
