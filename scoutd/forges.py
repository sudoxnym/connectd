"""
scoutd/forges.py - scrape self-hosted git forges

these people = highest signal. they actually selfhost.

supported platforms:
- gitea (and forks like forgejo)
- gogs
- gitlab ce
- sourcehut
- codeberg (gitea-based)

scrapes users AND extracts contact info for outreach.
"""

import os
import re
import json
import time
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from .signals import analyze_text

# rate limiting
REQUEST_DELAY = 1.0

# known public instances to scrape
# format: (name, url, platform_type)
KNOWN_INSTANCES = [
    # === PUBLIC INSTANCES ===
    # local/private instances can be added via LOCAL_FORGE_INSTANCES env var
    # codeberg (largest gitea instance)
    ('codeberg', 'https://codeberg.org', 'gitea'),

    # sourcehut
    ('sourcehut', 'https://sr.ht', 'sourcehut'),

    # notable gitea/forgejo instances
    ('gitea.com', 'https://gitea.com', 'gitea'),
    ('git.disroot.org', 'https://git.disroot.org', 'gitea'),
    ('git.gay', 'https://git.gay', 'forgejo'),
    ('git.envs.net', 'https://git.envs.net', 'forgejo'),
    ('tildegit', 'https://tildegit.org', 'gitea'),
    ('git.sr.ht', 'https://git.sr.ht', 'sourcehut'),

    # gitlab ce instances
    ('framagit', 'https://framagit.org', 'gitlab'),
    ('gitlab.gnome.org', 'https://gitlab.gnome.org', 'gitlab'),
    ('invent.kde.org', 'https://invent.kde.org', 'gitlab'),
    ('salsa.debian.org', 'https://salsa.debian.org', 'gitlab'),
]

# headers
HEADERS = {
    'User-Agent': 'connectd/1.0 (finding builders with aligned values)',
    'Accept': 'application/json',
}


def log(msg):
    print(f"  forges: {msg}")


# === GITEA/FORGEJO/GOGS API ===
# these share the same API structure

def scrape_gitea_users(instance_url: str, limit: int = 100) -> List[Dict]:
    """
    scrape users from a gitea/forgejo/gogs instance.
    uses the explore/users page or API if available.
    """
    users = []

    # try API first (gitea 1.x+)
    try:
        api_url = f"{instance_url}/api/v1/users/search"
        params = {'q': '', 'limit': min(limit, 50)}
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            user_list = data.get('data', []) or data.get('users', []) or data
            if isinstance(user_list, list):
                for u in user_list[:limit]:
                    users.append({
                        'username': u.get('login') or u.get('username'),
                        'full_name': u.get('full_name'),
                        'avatar': u.get('avatar_url'),
                        'website': u.get('website'),
                        'location': u.get('location'),
                        'bio': u.get('description') or u.get('bio'),
                    })
                log(f"  got {len(users)} users via API")
    except Exception as e:
        log(f"  API failed: {e}")

    # fallback: scrape explore page
    if not users:
        try:
            explore_url = f"{instance_url}/explore/users"
            resp = requests.get(explore_url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                # parse HTML for usernames
                usernames = re.findall(r'href="/([^/"]+)"[^>]*class="[^"]*user[^"]*"', resp.text)
                usernames += re.findall(r'<a[^>]+href="/([^/"]+)"[^>]*title="[^"]*"', resp.text)
                usernames = list(set(usernames))[:limit]
                for username in usernames:
                    if username and not username.startswith(('explore', 'api', 'user', 'repo')):
                        users.append({'username': username})
                log(f"  got {len(users)} users via scrape")
        except Exception as e:
            log(f"  scrape failed: {e}")

    return users


def get_gitea_user_details(instance_url: str, username: str) -> Optional[Dict]:
    """get detailed user info from gitea/forgejo/gogs"""
    try:
        # API endpoint
        api_url = f"{instance_url}/api/v1/users/{username}"
        resp = requests.get(api_url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            u = resp.json()
            return {
                'username': u.get('login') or u.get('username'),
                'full_name': u.get('full_name'),
                'email': u.get('email'),  # may be hidden
                'website': u.get('website'),
                'location': u.get('location'),
                'bio': u.get('description') or u.get('bio'),
                'created': u.get('created'),
                'followers': u.get('followers_count', 0),
                'following': u.get('following_count', 0),
            }
    except:
        pass
    return None


def get_gitea_user_repos(instance_url: str, username: str, limit: int = 10) -> List[Dict]:
    """get user's repos from gitea/forgejo/gogs"""
    repos = []
    try:
        api_url = f"{instance_url}/api/v1/users/{username}/repos"
        resp = requests.get(api_url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            for r in resp.json()[:limit]:
                repos.append({
                    'name': r.get('name'),
                    'full_name': r.get('full_name'),
                    'description': r.get('description'),
                    'stars': r.get('stars_count', 0),
                    'forks': r.get('forks_count', 0),
                    'language': r.get('language'),
                    'updated': r.get('updated_at'),
                })
    except:
        pass
    return repos


# === GITLAB CE API ===

def scrape_gitlab_users(instance_url: str, limit: int = 100) -> List[Dict]:
    """scrape users from a gitlab ce instance"""
    users = []

    try:
        # gitlab API - public users endpoint
        api_url = f"{instance_url}/api/v4/users"
        params = {'per_page': min(limit, 100), 'active': True}
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=15)

        if resp.status_code == 200:
            for u in resp.json()[:limit]:
                users.append({
                    'username': u.get('username'),
                    'full_name': u.get('name'),
                    'avatar': u.get('avatar_url'),
                    'website': u.get('website_url'),
                    'location': u.get('location'),
                    'bio': u.get('bio'),
                    'public_email': u.get('public_email'),
                })
            log(f"  got {len(users)} gitlab users")
    except Exception as e:
        log(f"  gitlab API failed: {e}")

    return users


def get_gitlab_user_details(instance_url: str, username: str) -> Optional[Dict]:
    """get detailed gitlab user info"""
    try:
        api_url = f"{instance_url}/api/v4/users"
        params = {'username': username}
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            users = resp.json()
            if users:
                u = users[0]
                return {
                    'username': u.get('username'),
                    'full_name': u.get('name'),
                    'email': u.get('public_email'),
                    'website': u.get('website_url'),
                    'location': u.get('location'),
                    'bio': u.get('bio'),
                    'created': u.get('created_at'),
                }
    except:
        pass
    return None


def get_gitlab_user_projects(instance_url: str, username: str, limit: int = 10) -> List[Dict]:
    """get user's projects from gitlab"""
    repos = []
    try:
        # first get user id
        api_url = f"{instance_url}/api/v4/users"
        params = {'username': username}
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=10)

        if resp.status_code == 200 and resp.json():
            user_id = resp.json()[0].get('id')

            # get projects
            proj_url = f"{instance_url}/api/v4/users/{user_id}/projects"
            resp = requests.get(proj_url, headers=HEADERS, timeout=10)

            if resp.status_code == 200:
                for p in resp.json()[:limit]:
                    repos.append({
                        'name': p.get('name'),
                        'full_name': p.get('path_with_namespace'),
                        'description': p.get('description'),
                        'stars': p.get('star_count', 0),
                        'forks': p.get('forks_count', 0),
                        'updated': p.get('last_activity_at'),
                    })
    except:
        pass
    return repos


# === SOURCEHUT API ===

def scrape_sourcehut_users(limit: int = 100) -> List[Dict]:
    """
    scrape users from sourcehut.
    sourcehut doesn't have a public user list, so we scrape from:
    - recent commits
    - mailing lists
    - project pages
    """
    users = []
    seen = set()

    try:
        # scrape from git.sr.ht explore
        resp = requests.get('https://git.sr.ht/projects', headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            # extract usernames from repo paths like ~username/repo
            usernames = re.findall(r'href="/~([^/"]+)', resp.text)
            for username in usernames:
                if username not in seen:
                    seen.add(username)
                    users.append({'username': username})
                    if len(users) >= limit:
                        break
        log(f"  got {len(users)} sourcehut users")
    except Exception as e:
        log(f"  sourcehut scrape failed: {e}")

    return users


def get_sourcehut_user_details(username: str) -> Optional[Dict]:
    """get sourcehut user details"""
    try:
        # scrape profile page
        profile_url = f"https://sr.ht/~{username}"
        resp = requests.get(profile_url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            bio = ''
            # extract bio from page
            bio_match = re.search(r'<div class="container">\s*<p>([^<]+)</p>', resp.text)
            if bio_match:
                bio = bio_match.group(1).strip()

            return {
                'username': username,
                'bio': bio,
                'profile_url': profile_url,
            }
    except:
        pass
    return None


def get_sourcehut_user_repos(username: str, limit: int = 10) -> List[Dict]:
    """get sourcehut user's repos"""
    repos = []
    try:
        git_url = f"https://git.sr.ht/~{username}"
        resp = requests.get(git_url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            # extract repo names
            repo_matches = re.findall(rf'href="/~{username}/([^"]+)"', resp.text)
            for repo in repo_matches[:limit]:
                if repo and not repo.startswith(('refs', 'log', 'tree')):
                    repos.append({
                        'name': repo,
                        'full_name': f"~{username}/{repo}",
                    })
    except:
        pass
    return repos


# === UNIFIED SCRAPER ===

def scrape_forge(instance_name: str, instance_url: str, platform_type: str, limit: int = 50) -> List[Dict]:
    """
    scrape users from any forge type.
    returns list of human dicts ready for database.
    """
    log(f"scraping {instance_name} ({platform_type})...")

    humans = []

    # get user list based on platform type
    if platform_type in ('gitea', 'forgejo', 'gogs'):
        users = scrape_gitea_users(instance_url, limit)
        get_details = lambda u: get_gitea_user_details(instance_url, u)
        get_repos = lambda u: get_gitea_user_repos(instance_url, u)
    elif platform_type == 'gitlab':
        users = scrape_gitlab_users(instance_url, limit)
        get_details = lambda u: get_gitlab_user_details(instance_url, u)
        get_repos = lambda u: get_gitlab_user_projects(instance_url, u)
    elif platform_type == 'sourcehut':
        users = scrape_sourcehut_users(limit)
        get_details = get_sourcehut_user_details
        get_repos = get_sourcehut_user_repos
    else:
        log(f"  unknown platform type: {platform_type}")
        return []

    for user in users:
        username = user.get('username')
        if not username:
            continue

        time.sleep(REQUEST_DELAY)

        # get detailed info
        details = get_details(username)
        if details:
            user.update(details)

        # get repos
        repos = get_repos(username)

        # build human record
        bio = user.get('bio', '') or ''
        website = user.get('website', '') or ''

        # analyze signals from bio
        score, signals, reasons = analyze_text(bio + ' ' + website)

        # BOOST: self-hosted git = highest signal
        score += 25
        signals.append('selfhosted_git')
        reasons.append(f'uses self-hosted git ({instance_name})')

        # extract contact info
        contact = {}
        email = user.get('email') or user.get('public_email')
        if email and '@' in email:
            contact['email'] = email
        if website:
            contact['website'] = website

        # build human dict
        human = {
            'platform': f'{platform_type}:{instance_name}',
            'username': username,
            'name': user.get('full_name'),
            'bio': bio,
            'url': f"{instance_url}/{username}" if platform_type != 'sourcehut' else f"https://sr.ht/~{username}",
            'score': score,
            'signals': json.dumps(signals),
            'reasons': json.dumps(reasons),
            'contact': json.dumps(contact),
            'extra': json.dumps({
                'instance': instance_name,
                'instance_url': instance_url,
                'platform_type': platform_type,
                'repos': repos[:5],
                'followers': user.get('followers', 0),
                'email': email,
                'website': website,
            }),
            'user_type': 'builder' if repos else 'none',
        }

        humans.append(human)
        log(f"    {username}: score={score}, repos={len(repos)}")

    return humans


def scrape_all_forges(limit_per_instance: int = 30) -> List[Dict]:
    """scrape all known forge instances"""
    all_humans = []

    for instance_name, instance_url, platform_type in KNOWN_INSTANCES:
        try:
            humans = scrape_forge(instance_name, instance_url, platform_type, limit_per_instance)
            all_humans.extend(humans)
            log(f"  {instance_name}: {len(humans)} humans")
        except Exception as e:
            log(f"  {instance_name} failed: {e}")

        time.sleep(2)  # be nice between instances

    log(f"total: {len(all_humans)} humans from {len(KNOWN_INSTANCES)} forges")
    return all_humans


# === OUTREACH METHODS ===

def can_message_on_forge(instance_url: str, platform_type: str) -> bool:
    """check if we can send messages on this forge"""
    # gitea/forgejo don't have DMs
    # gitlab has merge request comments
    # sourcehut has mailing lists
    return platform_type in ('gitlab', 'sourcehut')


def open_forge_issue(instance_url: str, platform_type: str,
                     owner: str, repo: str, title: str, body: str) -> Tuple[bool, str]:
    """
    open an issue on a forge as outreach method.
    requires API token for authenticated requests.
    """
    # would need tokens per instance - for now return False
    # this is a fallback method, email is preferred
    return False, "forge issue creation not implemented yet"


# === DISCOVERY ===

def discover_forge_instances() -> List[Tuple[str, str, str]]:
    """
    discover new forge instances from:
    - fediverse (they often announce)
    - known lists
    - DNS patterns

    returns list of (name, url, platform_type)
    """
    # start with known instances
    instances = list(KNOWN_INSTANCES)

    # could add discovery logic here:
    # - scrape https://codeberg.org/forgejo/forgejo/issues for instance mentions
    # - check fediverse for git.* domains
    # - crawl gitea/forgejo awesome lists

    return instances


if __name__ == '__main__':
    # test
    print("testing forge scrapers...")

    # test codeberg
    humans = scrape_forge('codeberg', 'https://codeberg.org', 'gitea', limit=5)
    print(f"codeberg: {len(humans)} humans")
    for h in humans[:2]:
        print(f"  {h['username']}: {h['score']} - {h.get('signals')}")
