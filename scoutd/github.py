"""
scoutd/github.py - github discovery
scrapes repos, bios, commit patterns to find aligned builders
also detects lost builders - people with potential who haven't started yet
"""

import requests
import json
import time
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from .signals import analyze_text, TARGET_TOPICS, ECOSYSTEM_REPOS
from .lost import (
    analyze_github_for_lost_signals,
    analyze_text_for_lost_signals,
    classify_user,
    get_signal_descriptions,
)
from .handles import discover_all_handles

# rate limit: 60/hr unauthenticated, 5000/hr with token
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
HEADERS = {'Accept': 'application/vnd.github.v3+json'}
if GITHUB_TOKEN:
    HEADERS['Authorization'] = f'token {GITHUB_TOKEN}'

CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'github'


def _api_get(url, params=None):
    """rate-limited api request with caching"""
    cache_key = f"{url}_{json.dumps(params or {}, sort_keys=True)}"
    cache_file = CACHE_DIR / f"{hash(cache_key) & 0xffffffff}.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # check cache (1 hour expiry)
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get('_cached_at', 0) < 3600:
                return data.get('_data')
        except:
            pass

    # rate limit
    time.sleep(0.5 if GITHUB_TOKEN else 2)

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        # cache
        cache_file.write_text(json.dumps({'_cached_at': time.time(), '_data': result}))
        return result
    except requests.exceptions.RequestException as e:
        print(f"  github api error: {e}")
        return None


def search_repos_by_topic(topic, per_page=100):
    """search repos by topic tag"""
    url = 'https://api.github.com/search/repositories'
    params = {'q': f'topic:{topic}', 'sort': 'stars', 'order': 'desc', 'per_page': per_page}
    data = _api_get(url, params)
    return data.get('items', []) if data else []


def get_repo_contributors(repo_full_name, per_page=100):
    """get top contributors to a repo"""
    url = f'https://api.github.com/repos/{repo_full_name}/contributors'
    return _api_get(url, {'per_page': per_page}) or []


def get_github_user(login):
    """get full user profile"""
    url = f'https://api.github.com/users/{login}'
    return _api_get(url)


def get_user_repos(login, per_page=100):
    """get user's repos"""
    url = f'https://api.github.com/users/{login}/repos'
    return _api_get(url, {'per_page': per_page, 'sort': 'pushed'}) or []


def analyze_github_user(login):
    """
    analyze a github user for values alignment
    returns dict with score, confidence, signals, contact info
    """
    user = get_github_user(login)
    if not user:
        return None

    repos = get_user_repos(login)

    # collect text corpus
    text_parts = []
    if user.get('bio'):
        text_parts.append(user['bio'])
    if user.get('company'):
        text_parts.append(user['company'])
    if user.get('location'):
        text_parts.append(user['location'])

    # analyze repos
    all_topics = []
    languages = defaultdict(int)
    total_stars = 0

    for repo in repos:
        if repo.get('description'):
            text_parts.append(repo['description'])
        if repo.get('topics'):
            all_topics.extend(repo['topics'])
        if repo.get('language'):
            languages[repo['language']] += 1
        total_stars += repo.get('stargazers_count', 0)

    full_text = ' '.join(text_parts)

    # analyze signals
    text_score, positive_signals, negative_signals = analyze_text(full_text)

    # topic alignment
    aligned_topics = set(all_topics) & set(TARGET_TOPICS)
    topic_score = len(aligned_topics) * 10

    # builder score (repos indicate building, not just talking)
    builder_score = 0
    if len(repos) > 20:
        builder_score = 15
    elif len(repos) > 10:
        builder_score = 10
    elif len(repos) > 5:
        builder_score = 5

    # hireable bonus
    hireable_score = 5 if user.get('hireable') else 0

    # total score
    total_score = text_score + topic_score + builder_score + hireable_score

    # === LOST BUILDER DETECTION ===
    # build profile dict for lost analysis
    profile_for_lost = {
        'bio': user.get('bio'),
        'repos': repos,
        'public_repos': user.get('public_repos', len(repos)),
        'followers': user.get('followers', 0),
        'following': user.get('following', 0),
        'extra': {
            'top_repos': repos[:10],
        },
    }

    # analyze for lost signals
    lost_signals, lost_weight = analyze_github_for_lost_signals(profile_for_lost)

    # also check text for lost language patterns
    text_lost_signals, text_lost_weight = analyze_text_for_lost_signals(full_text)
    for sig in text_lost_signals:
        if sig not in lost_signals:
            lost_signals.append(sig)
            lost_weight += text_lost_weight

    lost_potential_score = lost_weight

    # classify: builder, lost, both, or none
    user_type = classify_user(lost_potential_score, builder_score, total_score)

    # confidence based on data richness
    confidence = 0.3
    if user.get('bio'):
        confidence += 0.15
    if len(repos) > 5:
        confidence += 0.15
    if len(text_parts) > 5:
        confidence += 0.15
    if user.get('email') or user.get('blog') or user.get('twitter_username'):
        confidence += 0.15
    if total_stars > 100:
        confidence += 0.1
    confidence = min(confidence, 1.0)

    # build reasons
    reasons = []
    if positive_signals:
        reasons.append(f"signals: {', '.join(positive_signals[:5])}")
    if aligned_topics:
        reasons.append(f"topics: {', '.join(list(aligned_topics)[:5])}")
    if builder_score > 0:
        reasons.append(f"builder ({len(repos)} repos)")
    if negative_signals:
        reasons.append(f"WARNING: {', '.join(negative_signals)}")

    # add lost reasons if applicable
    if user_type == 'lost' or user_type == 'both':
        lost_descriptions = get_signal_descriptions(lost_signals)
        if lost_descriptions:
            reasons.append(f"LOST SIGNALS: {', '.join(lost_descriptions[:3])}")

    # === DEEP HANDLE DISCOVERY ===
    # follow blog links, scrape websites, find ALL social handles
    handles, discovered_emails = discover_all_handles(user)

    # merge discovered emails with github email
    all_emails = discovered_emails or []
    if user.get('email'):
        all_emails.append(user['email'])
    all_emails = list(set(e for e in all_emails if e and 'noreply' not in e.lower()))

    return {
        'platform': 'github',
        'username': login,
        'url': f"https://github.com/{login}",
        'name': user.get('name'),
        'bio': user.get('bio'),
        'location': user.get('location'),
        'score': total_score,
        'confidence': confidence,
        'signals': positive_signals,
        'negative_signals': negative_signals,
        'topics': list(aligned_topics),
        'languages': dict(languages),
        'repo_count': len(repos),
        'total_stars': total_stars,
        'reasons': reasons,
        'contact': {
            'email': all_emails[0] if all_emails else None,
            'emails': all_emails,
            'blog': user.get('blog'),
            'twitter': user.get('twitter_username') or handles.get('twitter'),
            'mastodon': handles.get('mastodon'),
            'bluesky': handles.get('bluesky'),
            'matrix': handles.get('matrix'),
            'lemmy': handles.get('lemmy'),
        },
        'extra': {
            'topics': list(aligned_topics),
            'languages': dict(languages),
            'repo_count': len(repos),
            'total_stars': total_stars,
            'hireable': user.get('hireable', False),
            'top_repos': [{'name': r.get('name'), 'description': r.get('description'), 'stars': r.get('stargazers_count', 0), 'language': r.get('language')} for r in repos[:5] if not r.get('fork')],
            'handles': handles,  # all discovered handles
        },
        'hireable': user.get('hireable', False),
            'top_repos': [{'name': r.get('name'), 'description': r.get('description'), 'stars': r.get('stargazers_count', 0), 'language': r.get('language')} for r in repos[:5] if not r.get('fork')],
        'scraped_at': datetime.now().isoformat(),
        # lost builder fields
        'lost_potential_score': lost_potential_score,
        'lost_signals': lost_signals,
        'user_type': user_type,  # 'builder', 'lost', 'both', 'none'
    }


def scrape_github(db, limit_per_source=50):
    """
    full github scrape
    returns list of analyzed users
    """
    print("scoutd/github: starting scrape...")

    all_logins = set()

    # 1. ecosystem repo contributors
    print("  scraping ecosystem repo contributors...")
    for repo in ECOSYSTEM_REPOS:
        contributors = get_repo_contributors(repo, per_page=limit_per_source)
        for c in contributors:
            login = c.get('login')
            if login and not login.endswith('[bot]'):
                all_logins.add(login)
        print(f"    {repo}: {len(contributors)} contributors")

    # 2. topic repos
    print("  scraping topic repos...")
    for topic in TARGET_TOPICS[:10]:
        repos = search_repos_by_topic(topic, per_page=30)
        for repo in repos:
            owner = repo.get('owner', {}).get('login')
            if owner and not owner.endswith('[bot]'):
                all_logins.add(owner)
        print(f"    #{topic}: {len(repos)} repos")

    print(f"  found {len(all_logins)} unique users to analyze")

    # analyze each
    results = []
    builders_found = 0
    lost_found = 0

    for i, login in enumerate(all_logins):
        if i % 20 == 0:
            print(f"  analyzing... {i}/{len(all_logins)}")

        try:
            result = analyze_github_user(login)
            if result and result['score'] > 0:
                results.append(result)
                db.save_human(result)

                user_type = result.get('user_type', 'none')

                if user_type == 'builder':
                    builders_found += 1
                    if result['score'] >= 50:
                        print(f"    ★ {login}: {result['score']} pts, {result['confidence']:.0%} conf")

                elif user_type == 'lost':
                    lost_found += 1
                    lost_score = result.get('lost_potential_score', 0)
                    if lost_score >= 40:
                        print(f"    💔 {login}: lost_score={lost_score}, values={result['score']} pts")

                elif user_type == 'both':
                    builders_found += 1
                    lost_found += 1
                    print(f"    ⚡ {login}: recovering builder (lost={result.get('lost_potential_score', 0)}, active={result['score']})")

        except Exception as e:
            print(f"    error on {login}: {e}")

    print(f"scoutd/github: found {len(results)} aligned humans")
    print(f"  - {builders_found} active builders")
    print(f"  - {lost_found} lost builders (need encouragement)")
    return results
