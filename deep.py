"""
scoutd/deep.py - deep profile discovery
when we find someone, follow ALL their links to build complete picture

github profile -> mastodon link -> scrape mastodon
                -> website -> scrape for more links
                -> twitter handle -> note it
                -> email -> store it

email discovery sources:
- github profile (if public)
- git commit history
- personal website/blog contact page
- README "contact me" sections
- mastodon/twitter bio

fallback contact methods if no email:
- github_issue: open issue on their repo
- mastodon: DM if allowed
- manual: pending contact queue for review

also filters out people who clearly already know each other
(same org, co-contributors to same repos)
"""

import re
import json
import requests
import time
import subprocess
import tempfile
import shutil
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

from .signals import analyze_text
from .github import get_github_user, get_user_repos, _api_get as github_api
from .mastodon import analyze_mastodon_user, _api_get as mastodon_api
from .handles import discover_all_handles, extract_handles_from_text, scrape_website_for_handles

# MASTODON HANDLE FILTER - don't treat these as emails
MASTODON_INSTANCES = [
    'mastodon.social', 'fosstodon.org', 'hachyderm.io', 'tech.lgbt',
    'social.coop', 'masto.ai', 'infosec.exchange', 'hackers.town',
    'chaos.social', 'mathstodon.xyz', 'scholar.social', 'mas.to',
    'mstdn.social', 'mastodon.online', 'universeodon.com', 'mastodon.world',
]

def is_mastodon_handle(email):
    """check if string looks like mastodon handle not email"""
    if not email or '@' not in email:
        return False
    email_lower = email.lower()
    # check for @username@instance pattern
    parts = email_lower.split('@')
    if len(parts) == 3 and parts[0] == '':  # @user@instance
        return True
    if len(parts) == 2:
        # check if domain is known mastodon instance
        domain = parts[1]
        for instance in MASTODON_INSTANCES:
            if domain == instance or domain.endswith('.' + instance):
                return True
        # also check common patterns
        if 'mastodon' in domain or 'masto' in domain:
            return True
    return False



# local cache for org memberships
ORG_CACHE_FILE = Path(__file__).parent.parent / 'data' / 'org_cache.json'
_org_cache = None

# patterns to find social links in text
MASTODON_PATTERN = r'@([a-zA-Z0-9_]+)@([a-zA-Z0-9.-]+\.[a-z]{2,})'
TWITTER_PATTERN = r'(?:twitter\.com/|x\.com/)([a-zA-Z0-9_]+)'
GITHUB_PATTERN = r'github\.com/([a-zA-Z0-9_-]+)'
MATRIX_PATTERN = r'@([a-zA-Z0-9_]+):([a-zA-Z0-9.-]+)'
EMAIL_PATTERN = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'

# known mastodon instances for validation
KNOWN_INSTANCES = [
    'mastodon.social', 'fosstodon.org', 'tech.lgbt', 'social.coop',
    'hackers.town', 'hachyderm.io', 'infosec.exchange', 'chaos.social',
    'mas.to', 'mstdn.social', 'mastodon.online', 'universeodon.com',
    'mathstodon.xyz', 'ruby.social', 'functional.cafe', 'types.pl',
]

# contact page patterns for website scraping
CONTACT_PAGE_PATHS = [
    '/contact', '/contact/', '/contact.html',
    '/about', '/about/', '/about.html',
    '/connect', '/reach-out', '/hire', '/hire-me',
]

# patterns to find emails in contact sections
CONTACT_SECTION_PATTERNS = [
    r'(?:contact|email|reach|mail)[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'([a-zA-Z0-9._%+-]+)\s*(?:\[at\]|\(at\)|@)\s*([a-zA-Z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\.)\s*([a-zA-Z]{2,})',
]


def load_org_cache():
    """load org membership cache from disk"""
    global _org_cache
    if _org_cache is not None:
        return _org_cache

    try:
        ORG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if ORG_CACHE_FILE.exists():
            with open(ORG_CACHE_FILE) as f:
                _org_cache = json.load(f)
        else:
            _org_cache = {'users': {}, 'updated': {}}
    except:
        _org_cache = {'users': {}, 'updated': {}}

    return _org_cache


def save_org_cache():
    """save org membership cache to disk"""
    global _org_cache
    if _org_cache is None:
        return

    try:
        ORG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ORG_CACHE_FILE, 'w') as f:
            json.dump(_org_cache, f, indent=2)
    except:
        pass


def get_cached_orgs(username):
    """get orgs from cache if available and fresh (< 7 days old)"""
    cache = load_org_cache()

    if username not in cache['users']:
        return None

    updated = cache['updated'].get(username)
    if updated:
        updated_dt = datetime.fromisoformat(updated)
        if (datetime.now() - updated_dt).days < 7:
            return cache['users'][username]

    return None


def cache_orgs(username, orgs):
    """cache org membership for a user"""
    cache = load_org_cache()
    cache['users'][username] = orgs
    cache['updated'][username] = datetime.now().isoformat()
    save_org_cache()


def get_emails_from_commit_history(repo_url, limit=50):
    """
    clone a repo (shallow) and extract unique committer emails from git log
    """
    emails = set()

    try:
        # create temp dir
        with tempfile.TemporaryDirectory() as tmpdir:
            # shallow clone with limited depth
            result = subprocess.run(
                ['git', 'clone', '--depth', '50', '--single-branch', repo_url, tmpdir],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return []

            # get unique emails from commit log
            result = subprocess.run(
                ['git', 'log', f'--max-count={limit}', '--format=%ae'],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                for email in result.stdout.strip().split('\n'):
                    email = email.strip().lower()
                    # filter out bot/noreply emails
                    if email and not any(x in email for x in [
                        'noreply', 'no-reply', 'dependabot', 'github-actions',
                        'renovate', 'greenkeeper', 'snyk-bot', 'users.noreply.github'
                    ]):
                        emails.add(email)
    except (subprocess.TimeoutExpired, Exception):
        pass

    return list(emails)


def scrape_website_for_emails(url, timeout=10):
    """
    scrape a personal website for email addresses
    checks main page and common contact pages
    """
    emails = set()

    if not is_personal_website(url):
        return []

    headers = {'User-Agent': 'connectd/1.0 (looking for contact info)'}

    # normalize url
    if not url.startswith('http'):
        url = 'https://' + url

    base_url = url.rstrip('/')

    # pages to check
    pages_to_check = [base_url] + [base_url + path for path in CONTACT_PAGE_PATHS]

    for page_url in pages_to_check:
        try:
            resp = requests.get(page_url, timeout=timeout, headers=headers)
            if resp.status_code == 200:
                text = resp.text

                # standard email pattern
                for match in re.finditer(EMAIL_PATTERN, text):
                    email = match.group(0).lower()
                    if not any(x in email for x in ['noreply', 'no-reply', 'example.com', 'users.noreply']):
                        emails.add(email)

                # obfuscated email patterns like "user [at] domain [dot] com"
                for pattern in CONTACT_SECTION_PATTERNS:
                    for match in re.finditer(pattern, text, re.IGNORECASE):
                        if len(match.groups()) == 3:
                            email = f"{match.group(1)}@{match.group(2)}.{match.group(3)}".lower()
                            emails.add(email)
                        elif len(match.groups()) == 1:
                            emails.add(match.group(1).lower())

                # mailto: links
                for match in re.finditer(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text):
                    emails.add(match.group(1).lower())

        except:
            continue

    return list(emails)


def extract_emails_from_readme(text):
    """
    extract emails from README text, looking for contact sections
    """
    emails = set()

    if not text:
        return []

    # look for contact-related sections
    contact_patterns = [
        r'(?:##?\s*)?(?:contact|reach|email|get in touch|connect)[^\n]*\n([^\n#]+)',
        r'(?:email|contact|reach me)[:\s]+([^\n]+)',
    ]

    for pattern in contact_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            section = match.group(1)
            # extract emails from this section
            for email_match in re.finditer(EMAIL_PATTERN, section):
                email = email_match.group(0).lower()
                if not any(x in email for x in ['noreply', 'no-reply', 'example.com']):
                    emails.add(email)

    # also check for obfuscated emails
    for match in re.finditer(r'([a-zA-Z0-9._%+-]+)\s*(?:\[at\]|\(at\))\s*([a-zA-Z0-9.-]+)\s*(?:\[dot\]|\(dot\))\s*([a-zA-Z]{2,})', text, re.IGNORECASE):
        email = f"{match.group(1)}@{match.group(2)}.{match.group(3)}".lower()
        emails.add(email)

    return list(emails)


def get_mastodon_dm_allowed(handle):
    """check if a mastodon user allows DMs"""
    profile = get_mastodon_profile(handle)
    if not profile:
        return False

    # check if they're locked (requires follow approval)
    if profile.get('locked'):
        return False

    # check bio for "DMs open" type messages
    bio = (profile.get('note') or profile.get('summary') or '').lower()
    if any(x in bio for x in ['dms open', 'dm me', 'message me', 'dms welcome']):
        return True

    # default: assume open if not locked
    return True


def determine_contact_method(profile):
    """
    determine the best way to contact someone
    returns (method, details) where method is one of:
    - 'email': direct email contact
    - 'github_issue': open issue on their repo
    - 'mastodon': DM on mastodon
    - 'manual': needs manual review
    """
    # prefer email
    if profile.get('email'):
        return 'email', {'email': profile['email']}

    # check for multiple emails to pick from
    if profile.get('emails') and len(profile['emails']) > 0:
        # prefer non-github, non-work emails
        for email in profile['emails']:
            if not any(x in email.lower() for x in ['github', 'noreply', '@company', '@corp']):
                return 'email', {'email': email}
        # fall back to first one
        return 'email', {'email': profile['emails'][0]}

    # try mastodon DM
    if profile.get('mastodon'):
        handles = profile['mastodon'] if isinstance(profile['mastodon'], list) else [profile['mastodon']]
        for handle in handles:
            if get_mastodon_dm_allowed(handle):
                return 'mastodon', {'handle': handle}

    # try github issue on their most-starred repo
    if profile.get('top_repos'):
        # find repo with issues enabled and good stars
        for repo in sorted(profile['top_repos'], key=lambda r: r.get('stars', 0), reverse=True):
            if repo.get('stars', 0) >= 10:
                repo_name = repo.get('name')
                if repo_name:
                    return 'github_issue', {
                        'repo': f"{profile['username']}/{repo_name}",
                        'stars': repo.get('stars'),
                    }

    # manual review needed
    return 'manual', {
        'reason': 'no email, mastodon, or suitable repo found',
        'available': {
            'twitter': profile.get('twitter'),
            'websites': profile.get('websites'),
            'matrix': profile.get('matrix'),
        }
    }


def extract_links_from_text(text):
    """extract social links from bio/readme text"""
    if not text:
        return {}

    links = {
        'mastodon': [],
        'twitter': [],
        'github': [],
        'matrix': [],
        'email': [],
        'websites': [],
    }

    # mastodon handles - only accept known instances or ones with 'mastodon'/'social' in name
    for match in re.finditer(MASTODON_PATTERN, text):
        user, instance = match.groups()
        instance_lower = instance.lower()
        # validate it's a known instance or looks like one
        is_known = instance_lower in KNOWN_INSTANCES
        looks_like_masto = any(x in instance_lower for x in ['mastodon', 'social', 'fedi', '.town', '.cafe'])
        if is_known or looks_like_masto:
            links['mastodon'].append(f"{user}@{instance}")

    # twitter
    for match in re.finditer(TWITTER_PATTERN, text, re.IGNORECASE):
        links['twitter'].append(match.group(1))

    # github (for cross-referencing)
    for match in re.finditer(GITHUB_PATTERN, text, re.IGNORECASE):
        links['github'].append(match.group(1))

    # matrix
    for match in re.finditer(MATRIX_PATTERN, text):
        user, server = match.groups()
        links['matrix'].append(f"@{user}:{server}")

    # email
    for match in re.finditer(EMAIL_PATTERN, text):
        email = match.group(0)
        # filter out obvious non-personal emails
        if not any(x in email.lower() for x in ['noreply', 'no-reply', 'example.com', 'users.noreply']):
            links['email'].append(email)

    # websites (http/https links that aren't social platforms)
    url_pattern = r'https?://([a-zA-Z0-9.-]+\.[a-z]{2,})[/\w.-]*'
    for match in re.finditer(url_pattern, text):
        domain = match.group(1).lower()
        if not any(x in domain for x in ['github.com', 'twitter.com', 'mastodon', 'linkedin.com', 't.co']):
            links['websites'].append(match.group(0))

    # dedupe
    for key in links:
        links[key] = list(set(links[key]))

    return links


def is_personal_website(url):
    """check if URL looks like a personal website vs corporate site"""
    domain = urlparse(url).netloc.lower()

    # skip obvious corporate/platform sites
    skip_domains = [
        'github.com', 'gitlab.com', 'bitbucket.org',
        'twitter.com', 'x.com', 'linkedin.com', 'facebook.com',
        'youtube.com', 'medium.com', 'dev.to', 'hashnode.com',
        'wedo.com', 'google.com', 'microsoft.com', 'apple.com',
        'amazon.com', 'stackoverflow.com', 'reddit.com',
    ]

    if any(skip in domain for skip in skip_domains):
        return False

    # looks personal if: short domain, has common personal TLDs, contains username-like string
    personal_tlds = ['.io', '.dev', '.me', '.co', '.xyz', '.page', '.codes', '.software']
    if any(domain.endswith(tld) for tld in personal_tlds):
        return True

    # if domain is just name.com or similar
    parts = domain.replace('www.', '').split('.')
    if len(parts) == 2 and len(parts[0]) < 20:
        return True

    return False


def scrape_website_for_links(url, timeout=10):
    """scrape a personal website for more social links"""
    if not is_personal_website(url):
        return {}

    try:
        resp = requests.get(url, timeout=timeout, headers={'User-Agent': 'connectd/1.0'})
        resp.raise_for_status()
        return extract_links_from_text(resp.text)
    except:
        return {}


def get_mastodon_profile(handle):
    """
    fetch mastodon profile from handle like user@instance
    returns profile data or None
    """
    if '@' not in handle:
        return None

    parts = handle.split('@')
    if len(parts) == 2:
        user, instance = parts
    elif len(parts) == 3 and parts[0] == '':
        # @user@instance format
        user, instance = parts[1], parts[2]
    else:
        return None

    # try to look up via webfinger
    try:
        webfinger_url = f"https://{instance}/.well-known/webfinger"
        resp = requests.get(
            webfinger_url,
            params={'resource': f'acct:{user}@{instance}'},
            timeout=10,
            headers={'Accept': 'application/json'}
        )
        if resp.status_code == 200:
            data = resp.json()
            # find the profile link
            for link in data.get('links', []):
                if link.get('type') == 'application/activity+json':
                    profile_url = link.get('href')
                    # fetch the profile
                    profile_resp = requests.get(
                        profile_url,
                        timeout=10,
                        headers={'Accept': 'application/activity+json'}
                    )
                    if profile_resp.status_code == 200:
                        return profile_resp.json()
    except:
        pass

    # fallback: try direct API
    try:
        search_url = f"https://{instance}/api/v1/accounts/lookup"
        resp = requests.get(search_url, params={'acct': user}, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass

    return None


def deep_scrape_github_user(login, scrape_commits=True):
    """
    deep scrape a github user - follow all links, build complete profile

    email discovery sources:
    1. github profile (if public)
    2. git commit history (if scrape_commits=True)
    3. personal website/blog contact pages
    4. README "contact me" sections
    5. mastodon bio
    """
    print(f"  deep scraping {login}...")

    user = get_github_user(login)
    if not user:
        return None

    repos = get_user_repos(login, per_page=50)

    # collect all text to search for links
    all_text = []
    readme_text = None

    if user.get('bio'):
        all_text.append(user['bio'])
    if user.get('blog'):
        all_text.append(user['blog'])
    if user.get('company'):
        all_text.append(user['company'])

    # check readme of profile repo (username/username)
    for branch in ['main', 'master']:
        readme_url = f"https://raw.githubusercontent.com/{login}/{login}/{branch}/README.md"
        try:
            resp = requests.get(readme_url, timeout=10)
            if resp.status_code == 200:
                readme_text = resp.text
                all_text.append(readme_text)
                break
        except:
            pass

    # extract links from all collected text
    combined_text = '\n'.join(all_text)
    found_links = extract_links_from_text(combined_text)

    # ensure all keys exist
    for key in ['email', 'twitter', 'github', 'matrix', 'mastodon', 'websites']:
        if key not in found_links:
            found_links[key] = []

    # add explicit github fields
    if user.get('email'):
        found_links['email'].append(user['email'])
    if user.get('twitter_username'):
        found_links['twitter'].append(user['twitter_username'])
    if user.get('blog'):
        found_links['websites'].append(user['blog'])

    # EMAIL DISCOVERY: extract emails from README contact sections
    if readme_text:
        readme_emails = extract_emails_from_readme(readme_text)
        found_links['email'].extend(readme_emails)
        if readme_emails:
            print(f"    found {len(readme_emails)} email(s) in README")

    # dedupe
    for key in found_links:
        found_links[key] = list(set(found_links[key]))

    # now follow the links to gather more data
    profile = {
        'source': 'github',
        'username': login,
        'url': f"https://github.com/{login}",
        'real_name': user.get('name'),
        'bio': user.get('bio'),
        'location': user.get('location'),
        'company': user.get('company'),
        'hireable': user.get('hireable'),
        'created_at': user.get('created_at'),
        'public_repos': user.get('public_repos'),
        'followers': user.get('followers'),

        # contact points
        'email': found_links['email'][0] if found_links['email'] else user.get('email'),
        'emails': list(found_links['email']),
        'twitter': found_links['twitter'][0] if found_links['twitter'] else user.get('twitter_username'),
        'mastodon': found_links['mastodon'],
        'matrix': found_links['matrix'],
        'websites': found_links['websites'],

        # cross-platform profiles we find
        'linked_profiles': {},

        # repos and languages
        'top_repos': [],
        'languages': {},
        'topics': [],
        'orgs': [],

        # contact method (will be determined at end)
        'contact_method': None,
        'contact_details': None,
    }

    # analyze repos
    top_starred_repo = None
    for repo in repos[:30]:
        if not repo.get('fork'):
            repo_info = {
                'name': repo.get('name'),
                'description': repo.get('description'),
                'stars': repo.get('stargazers_count'),
                'language': repo.get('language'),
                'topics': repo.get('topics', []),
                'html_url': repo.get('html_url'),
                'pushed_at': repo.get('pushed_at'),  # for activity-based contact selection
            }
            profile['top_repos'].append(repo_info)

            # track top starred for commit email scraping
            if not top_starred_repo or repo.get('stargazers_count', 0) > top_starred_repo.get('stars', 0):
                top_starred_repo = repo_info

            if repo.get('language'):
                lang = repo['language']
                profile['languages'][lang] = profile['languages'].get(lang, 0) + 1

            profile['topics'].extend(repo.get('topics', []))

    profile['topics'] = list(set(profile['topics']))

    # get orgs - check cache first
    cached_orgs = get_cached_orgs(login)
    if cached_orgs is not None:
        print(f"    using cached orgs: {cached_orgs}")
        profile['orgs'] = cached_orgs
    else:
        orgs_url = f"https://api.github.com/users/{login}/orgs"
        orgs_data = github_api(orgs_url) or []
        profile['orgs'] = [o.get('login') for o in orgs_data]
        # cache for future use
        cache_orgs(login, profile['orgs'])
        if profile['orgs']:
            print(f"    fetched & cached orgs: {profile['orgs']}")

    # EMAIL DISCOVERY: scrape commit history from top repo
    if scrape_commits and top_starred_repo and not profile['emails']:
        repo_url = f"https://github.com/{login}/{top_starred_repo['name']}.git"
        print(f"    checking commit history in {top_starred_repo['name']}...")
        commit_emails = get_emails_from_commit_history(repo_url)
        if commit_emails:
            print(f"    found {len(commit_emails)} email(s) in commits")
            profile['emails'].extend(commit_emails)

    # follow mastodon links
    for masto_handle in found_links['mastodon'][:2]:  # limit to 2
        print(f"    following mastodon: {masto_handle}")
        masto_profile = get_mastodon_profile(masto_handle)
        if masto_profile:
            profile['linked_profiles']['mastodon'] = {
                'handle': masto_handle,
                'display_name': masto_profile.get('display_name') or masto_profile.get('name'),
                'bio': masto_profile.get('note') or masto_profile.get('summary'),
                'followers': masto_profile.get('followers_count'),
                'url': masto_profile.get('url'),
                'locked': masto_profile.get('locked', False),
            }
            # extract more links from mastodon bio
            masto_bio = masto_profile.get('note') or masto_profile.get('summary') or ''
            masto_links = extract_links_from_text(masto_bio)
            profile['emails'].extend(masto_links.get('email', []))
            profile['websites'].extend(masto_links.get('websites', []))

    # EMAIL DISCOVERY: scrape personal website for contact info
    for website in found_links['websites'][:2]:  # check up to 2 sites
        print(f"    following website: {website}")

        # basic link extraction
        site_links = scrape_website_for_links(website)
        if site_links.get('mastodon') and not profile['mastodon']:
            profile['mastodon'] = site_links['mastodon']

        # enhanced email discovery - check contact pages
        website_emails = scrape_website_for_emails(website)
        if website_emails:
            print(f"    found {len(website_emails)} email(s) on website")
            profile['emails'].extend(website_emails)

    # dedupe emails and pick best one
    # FILTER OUT MASTODON HANDLES (they're not emails!)
    profile['emails'] = [e for e in set(profile['emails']) if e and not is_mastodon_handle(e)]

    # rank emails by preference
    def email_score(email):
        email_lower = email.lower()
        score = 0
        # prefer personal domains
        if any(x in email_lower for x in ['@gmail', '@proton', '@hey.com', '@fastmail']):
            score += 10
        # deprioritize github emails
        if 'github' in email_lower:
            score -= 20
        # deprioritize noreply
        if 'noreply' in email_lower:
            score -= 50
        # prefer emails matching username
        if login.lower() in email_lower:
            score += 5
        return score

    if profile['emails']:
        profile['emails'].sort(key=email_score, reverse=True)
        profile['email'] = profile['emails'][0]

    # COMPREHENSIVE HANDLE DISCOVERY
    # find ALL social handles from website, README, rel="me" links, etc.
    discovered_handles, discovered_emails = discover_all_handles(user)

    # merge discovered handles into profile
    profile['handles'] = discovered_handles

    # update individual fields from discovered handles
    if discovered_handles.get('mastodon') and not profile.get('mastodon'):
        profile['mastodon'] = discovered_handles['mastodon']
    if discovered_handles.get('twitter') and not profile.get('twitter'):
        profile['twitter'] = discovered_handles['twitter']
    if discovered_handles.get('bluesky'):
        profile['bluesky'] = discovered_handles['bluesky']
    if discovered_handles.get('matrix') and not profile.get('matrix'):
        profile['matrix'] = discovered_handles['matrix']
    if discovered_handles.get('linkedin'):
        profile['linkedin'] = discovered_handles['linkedin']
    if discovered_handles.get('youtube'):
        profile['youtube'] = discovered_handles['youtube']
    if discovered_handles.get('discord'):
        profile['discord'] = discovered_handles['discord']
    if discovered_handles.get('telegram'):
        profile['telegram'] = discovered_handles['telegram']

    # merge discovered emails
    for email in discovered_emails:
        if email not in profile['emails']:
            profile['emails'].append(email)

    print(f"    handles found: {list(discovered_handles.keys())}")

    # determine best contact method
    contact_method, contact_details = determine_contact_method(profile)
    profile['contact_method'] = contact_method
    profile['contact_details'] = contact_details
    print(f"    contact method: {contact_method}")

    # analyze all text for signals
    all_profile_text = ' '.join([
        profile.get('bio') or '',
        profile.get('company') or '',
        profile.get('location') or '',
        ' '.join(profile.get('topics', [])),
    ])

    for linked in profile.get('linked_profiles', {}).values():
        if linked.get('bio'):
            all_profile_text += ' ' + linked['bio']

    text_score, signals, negative = analyze_text(all_profile_text)
    profile['signals'] = signals
    profile['negative_signals'] = negative
    profile['score'] = text_score

    # add builder score
    if len(repos) > 20:
        profile['score'] += 15
    elif len(repos) > 10:
        profile['score'] += 10

    # add topic alignment
    from .signals import TARGET_TOPICS
    aligned_topics = set(profile['topics']) & set(TARGET_TOPICS)
    profile['score'] += len(aligned_topics) * 10
    profile['aligned_topics'] = list(aligned_topics)

    profile['scraped_at'] = datetime.now().isoformat()

    return profile


def check_mutual_github_follows(user_a, user_b):
    """check if two github users follow each other"""
    # check if a follows b
    url = f"https://api.github.com/users/{user_a}/following/{user_b}"
    try:
        resp = requests.get(url, timeout=10, headers={'Accept': 'application/vnd.github.v3+json'})
        if resp.status_code == 204:  # 204 = follows
            return True
    except:
        pass
    return False


def check_shared_repo_contributions(user_a, user_b):
    """
    check if two users have contributed to the same repos
    returns (bool, list of shared repos)
    """
    # this would require checking contribution history
    # for now, we check via the orgs and top_repos stored in extra
    # the full implementation would query:
    # GET /repos/{owner}/{repo}/contributors for their top repos
    return False, []


def check_github_interactions(user_a, user_b):
    """
    check if users have had public interactions
    (comments on each other's issues/PRs)
    this is expensive - only do for high-score matches
    """
    # would need to search:
    # GET /search/issues?q=author:{user_a}+commenter:{user_b}
    # GET /search/issues?q=author:{user_b}+commenter:{user_a}
    return False


def check_already_connected(human_a, human_b, deep_check=False):
    """
    check if two humans are likely already connected
    (same org, co-contributors, mutual follows, interactions)

    connectd's job is connecting ISOLATED builders, not re-introducing coworkers
    """
    # parse extra data if stored as json string
    extra_a = human_a.get('extra', {})
    extra_b = human_b.get('extra', {})
    if isinstance(extra_a, str):
        extra_a = json.loads(extra_a) if extra_a else {}
    if isinstance(extra_b, str):
        extra_b = json.loads(extra_b) if extra_b else {}

    # 1. same github org - check cache first, then stored data
    orgs_a = set(extra_a.get('orgs', []))
    orgs_b = set(extra_b.get('orgs', []))

    # also check org cache for fresher data
    if human_a.get('platform') == 'github':
        cached_a = get_cached_orgs(human_a.get('username', ''))
        if cached_a:
            orgs_a.update(cached_a)
    if human_b.get('platform') == 'github':
        cached_b = get_cached_orgs(human_b.get('username', ''))
        if cached_b:
            orgs_b.update(cached_b)

    shared_orgs = orgs_a & orgs_b

    if shared_orgs:
        return True, f"same org: {', '.join(list(shared_orgs)[:3])}"

    # 2. same company
    company_a = (extra_a.get('company') or '').lower().strip('@').strip()
    company_b = (extra_b.get('company') or '').lower().strip('@').strip()

    if company_a and company_b and len(company_a) > 2:
        if company_a == company_b or company_a in company_b or company_b in company_a:
            return True, f"same company: {company_a or company_b}"

    # 3. co-contributors to same major repos (from stored top_repos)
    repos_a = set()
    repos_b = set()
    for r in extra_a.get('top_repos', []):
        if r.get('stars', 0) > 50:  # only significant repos
            repos_a.add(r.get('name', '').lower())
    for r in extra_b.get('top_repos', []):
        if r.get('stars', 0) > 50:
            repos_b.add(r.get('name', '').lower())

    shared_repos = repos_a & repos_b
    if len(shared_repos) >= 2:
        return True, f"co-contributors: {', '.join(list(shared_repos)[:3])}"

    # 4. deep checks (more API calls - only if requested)
    if deep_check:
        user_a = human_a.get('username', '')
        user_b = human_b.get('username', '')

        # check mutual follows
        if human_a.get('platform') == 'github' and human_b.get('platform') == 'github':
            if check_mutual_github_follows(user_a, user_b):
                return True, "mutual github follows"
            if check_mutual_github_follows(user_b, user_a):
                return True, "mutual github follows"

    return False, None


def save_deep_profile(db, profile):
    """save a deep-scraped profile to the database"""
    # convert to standard human format
    # IMPORTANT: extra field contains ALL data for activity-based contact selection
    human_data = {
        'platform': profile['source'],
        'username': profile['username'],
        'url': profile['url'],
        'name': profile.get('real_name'),
        'bio': profile.get('bio'),
        'location': profile.get('location'),
        'score': profile.get('score', 0),
        'confidence': 0.8 if profile.get('linked_profiles') else 0.5,
        'signals': profile.get('signals', []),
        'negative_signals': profile.get('negative_signals', []),
        'reasons': [],
        'contact': {
            'email': profile.get('email'),
            'emails': profile.get('emails', []),
            'twitter': profile.get('twitter'),
            'mastodon': profile.get('mastodon'),
            'matrix': profile.get('matrix'),
            'websites': profile.get('websites'),
            'contact_method': profile.get('contact_method'),
            'contact_details': profile.get('contact_details'),
        },
        'extra': {
            # identity
            'real_name': profile.get('real_name'),
            'company': profile.get('company'),
            'hireable': profile.get('hireable'),
            'orgs': profile.get('orgs'),

            # github activity (for activity-based contact)
            'top_repos': profile.get('top_repos'),
            'languages': profile.get('languages'),
            'topics': profile.get('topics'),
            'aligned_topics': profile.get('aligned_topics'),
            'followers': profile.get('followers'),
            'public_repos': profile.get('public_repos'),
            'commit_count': len(profile.get('emails', [])),  # rough proxy

            # cross-platform links (for activity-based contact)
            'email': profile.get('email'),
            'emails': profile.get('emails', []),
            'twitter': profile.get('twitter'),
            'mastodon': profile.get('mastodon'),
            'matrix': profile.get('matrix'),
            'bluesky': profile.get('bluesky'),
            'reddit': profile.get('reddit'),
            'lobsters': profile.get('lobsters'),
            'linkedin': profile.get('linkedin'),
            'youtube': profile.get('youtube'),
            'discord': profile.get('discord'),
            'telegram': profile.get('telegram'),
            'linked_profiles': profile.get('linked_profiles'),

            # ALL discovered handles (comprehensive)
            'handles': profile.get('handles', {}),

            # activity counts (populated by platform scrapers)
            'mastodon_statuses': profile.get('mastodon_statuses', 0),
            'twitter_tweets': profile.get('twitter_tweets', 0),
            'reddit_activity': profile.get('reddit_activity', 0),
            'reddit_karma': profile.get('reddit_karma', 0),
            'lobsters_karma': profile.get('lobsters_karma', 0),
            'bluesky_posts': profile.get('bluesky_posts', 0),
        },
        'scraped_at': profile.get('scraped_at'),
    }

    # build reasons
    if profile.get('signals'):
        human_data['reasons'].append(f"signals: {', '.join(profile['signals'][:5])}")
    if profile.get('aligned_topics'):
        human_data['reasons'].append(f"topics: {', '.join(profile['aligned_topics'][:5])}")
    if profile.get('linked_profiles'):
        platforms = list(profile['linked_profiles'].keys())
        human_data['reasons'].append(f"also on: {', '.join(platforms)}")
    if profile.get('location'):
        human_data['reasons'].append(f"location: {profile['location']}")
    if profile.get('contact_method'):
        human_data['reasons'].append(f"contact: {profile['contact_method']}")

    db.save_human(human_data)
    return human_data
