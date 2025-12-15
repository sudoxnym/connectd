"""
scoutd/handles.py - comprehensive social handle discovery

finds ALL social handles from:
- github bio/profile
- personal websites (rel="me", footers, contact pages, json-ld)
- README files
- linktree/bio.link/carrd pages
- any linked pages

stores structured handle data for activity-based contact selection
"""

import re
import json
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; connectd/1.0)'}

# platform URL patterns -> (platform, handle_extractor)
PLATFORM_PATTERNS = {
    # fediverse
    'mastodon': [
        (r'https?://([^/]+)/@([^/?#]+)', lambda m: f"@{m.group(2)}@{m.group(1)}"),
        (r'https?://([^/]+)/users/([^/?#]+)', lambda m: f"@{m.group(2)}@{m.group(1)}"),
        (r'https?://mastodon\.social/@([^/?#]+)', lambda m: f"@{m.group(1)}@mastodon.social"),
    ],
    'pixelfed': [
        (r'https?://pixelfed\.social/@([^/?#]+)', lambda m: f"@{m.group(1)}@pixelfed.social"),
        (r'https?://([^/]*pixelfed[^/]*)/@([^/?#]+)', lambda m: f"@{m.group(2)}@{m.group(1)}"),
    ],
    'lemmy': [
        (r'https?://([^/]+)/u/([^/?#]+)', lambda m: f"@{m.group(2)}@{m.group(1)}"),
        (r'https?://lemmy\.([^/]+)/u/([^/?#]+)', lambda m: f"@{m.group(2)}@lemmy.{m.group(1)}"),
    ],

    # mainstream
    'twitter': [
        (r'https?://(?:www\.)?(?:twitter|x)\.com/([^/?#]+)', lambda m: f"@{m.group(1)}"),
    ],
    'bluesky': [
        (r'https?://bsky\.app/profile/([^/?#]+)', lambda m: m.group(1)),
        (r'https?://([^.]+)\.bsky\.social', lambda m: f"{m.group(1)}.bsky.social"),
    ],
    'threads': [
        (r'https?://(?:www\.)?threads\.net/@([^/?#]+)', lambda m: f"@{m.group(1)}"),
    ],
    'instagram': [
        (r'https?://(?:www\.)?instagram\.com/([^/?#]+)', lambda m: f"@{m.group(1)}"),
    ],
    'facebook': [
        (r'https?://(?:www\.)?facebook\.com/([^/?#]+)', lambda m: m.group(1)),
    ],
    'linkedin': [
        (r'https?://(?:www\.)?linkedin\.com/in/([^/?#]+)', lambda m: m.group(1)),
        (r'https?://(?:www\.)?linkedin\.com/company/([^/?#]+)', lambda m: f"company/{m.group(1)}"),
    ],

    # dev platforms
    'github': [
        (r'https?://(?:www\.)?github\.com/([^/?#]+)', lambda m: m.group(1)),
    ],
    'gitlab': [
        (r'https?://(?:www\.)?gitlab\.com/([^/?#]+)', lambda m: m.group(1)),
    ],
    'codeberg': [
        (r'https?://codeberg\.org/([^/?#]+)', lambda m: m.group(1)),
    ],
    'sourcehut': [
        (r'https?://sr\.ht/~([^/?#]+)', lambda m: f"~{m.group(1)}"),
        (r'https?://git\.sr\.ht/~([^/?#]+)', lambda m: f"~{m.group(1)}"),
    ],

    # chat
    'matrix': [
        (r'https?://matrix\.to/#/(@[^:]+:[^/?#]+)', lambda m: m.group(1)),
    ],
    'discord': [
        (r'https?://discord\.gg/([^/?#]+)', lambda m: f"invite/{m.group(1)}"),
        (r'https?://discord\.com/invite/([^/?#]+)', lambda m: f"invite/{m.group(1)}"),
    ],
    'telegram': [
        (r'https?://t\.me/([^/?#]+)', lambda m: f"@{m.group(1)}"),
    ],

    # content
    'youtube': [
        (r'https?://(?:www\.)?youtube\.com/@([^/?#]+)', lambda m: f"@{m.group(1)}"),
        (r'https?://(?:www\.)?youtube\.com/c(?:hannel)?/([^/?#]+)', lambda m: m.group(1)),
    ],
    'twitch': [
        (r'https?://(?:www\.)?twitch\.tv/([^/?#]+)', lambda m: m.group(1)),
    ],
    'substack': [
        (r'https?://([^.]+)\.substack\.com', lambda m: m.group(1)),
    ],
    'medium': [
        (r'https?://(?:www\.)?medium\.com/@([^/?#]+)', lambda m: f"@{m.group(1)}"),
        (r'https?://([^.]+)\.medium\.com', lambda m: m.group(1)),
    ],
    'devto': [
        (r'https?://dev\.to/([^/?#]+)', lambda m: m.group(1)),
    ],

    # funding
    'kofi': [
        (r'https?://ko-fi\.com/([^/?#]+)', lambda m: m.group(1)),
    ],
    'patreon': [
        (r'https?://(?:www\.)?patreon\.com/([^/?#]+)', lambda m: m.group(1)),
    ],
    'liberapay': [
        (r'https?://liberapay\.com/([^/?#]+)', lambda m: m.group(1)),
    ],
    'github_sponsors': [
        (r'https?://github\.com/sponsors/([^/?#]+)', lambda m: m.group(1)),
    ],

    # link aggregators (we'll parse these specially)
    'linktree': [
        (r'https?://linktr\.ee/([^/?#]+)', lambda m: m.group(1)),
    ],
    'biolink': [
        (r'https?://bio\.link/([^/?#]+)', lambda m: m.group(1)),
    ],
    'carrd': [
        (r'https?://([^.]+)\.carrd\.co', lambda m: m.group(1)),
    ],
}

# fediverse handle pattern: @user@instance
FEDIVERSE_HANDLE_PATTERN = re.compile(r'@([\w.-]+)@([\w.-]+\.[\w]+)')

# email pattern
EMAIL_PATTERN = re.compile(r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b')

# known fediverse instances (for context-free handle detection)
KNOWN_FEDIVERSE_INSTANCES = [
    'mastodon.social', 'mastodon.online', 'mstdn.social', 'mas.to',
    'tech.lgbt', 'fosstodon.org', 'hackers.town', 'social.coop',
    'kolektiva.social', 'solarpunk.moe', 'wandering.shop',
    'elekk.xyz', 'cybre.space', 'octodon.social', 'chaos.social',
    'infosec.exchange', 'ruby.social', 'phpc.social', 'toot.cafe',
    'mstdn.io', 'pixelfed.social', 'lemmy.ml', 'lemmy.world',
    'kbin.social', 'pleroma.site', 'akkoma.dev',
]


def extract_handle_from_url(url):
    """extract platform and handle from a URL"""
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern, extractor in patterns:
            match = re.match(pattern, url, re.I)
            if match:
                return platform, extractor(match)
    return None, None


def extract_fediverse_handles(text):
    """find @user@instance.tld patterns in text"""
    handles = []
    for match in FEDIVERSE_HANDLE_PATTERN.finditer(text):
        user, instance = match.groups()
        handles.append(f"@{user}@{instance}")
    return handles


def extract_emails(text):
    """find email addresses in text"""
    emails = []
    for match in EMAIL_PATTERN.finditer(text):
        email = match.group(1)
        # filter out common non-personal emails
        if not any(x in email.lower() for x in ['noreply', 'no-reply', 'donotreply', 'example.com']):
            emails.append(email)
    return emails


def scrape_page(url, timeout=15):
    """fetch and parse a web page"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, 'html.parser'), resp.text
    except Exception as e:
        return None, None


def extract_rel_me_links(soup):
    """extract rel="me" links (used for verification)"""
    links = []
    if not soup:
        return links

    for a in soup.find_all('a', rel=lambda x: x and 'me' in x):
        href = a.get('href')
        if href:
            links.append(href)

    return links


def extract_social_links_from_page(soup, base_url=None):
    """extract all social links from a page"""
    links = []
    if not soup:
        return links

    # all links
    for a in soup.find_all('a', href=True):
        href = a['href']
        if base_url and not href.startswith('http'):
            href = urljoin(base_url, href)

        # check if it's a known social platform
        platform, handle = extract_handle_from_url(href)
        if platform:
            links.append({'platform': platform, 'handle': handle, 'url': href})

    return links


def extract_json_ld(soup):
    """extract structured data from JSON-LD"""
    data = {}
    if not soup:
        return data

    for script in soup.find_all('script', type='application/ld+json'):
        try:
            ld = json.loads(script.string)
            # look for sameAs links (social profiles)
            if isinstance(ld, dict):
                same_as = ld.get('sameAs', [])
                if isinstance(same_as, str):
                    same_as = [same_as]
                for url in same_as:
                    platform, handle = extract_handle_from_url(url)
                    if platform:
                        data[platform] = handle
        except:
            pass

    return data


def scrape_linktree(url):
    """scrape a linktree/bio.link/carrd page for all links"""
    handles = {}
    soup, raw = scrape_page(url)
    if not soup:
        return handles

    # linktree uses data attributes and JS, but links are often in the HTML
    links = extract_social_links_from_page(soup, url)
    for link in links:
        if link['platform'] not in ['linktree', 'biolink', 'carrd']:
            handles[link['platform']] = link['handle']

    # also check for fediverse handles in text
    if raw:
        fedi_handles = extract_fediverse_handles(raw)
        if fedi_handles:
            handles['mastodon'] = fedi_handles[0]

    return handles


def scrape_website_for_handles(url, follow_links=True):
    """
    comprehensive website scrape for social handles

    checks:
    - rel="me" links
    - social links in page
    - json-ld structured data
    - /about and /contact pages
    - fediverse handles in text
    - emails
    """
    handles = {}
    emails = []

    soup, raw = scrape_page(url)
    if not soup:
        return handles, emails

    # 1. rel="me" links (most authoritative)
    rel_me = extract_rel_me_links(soup)
    for link in rel_me:
        platform, handle = extract_handle_from_url(link)
        if platform and platform not in handles:
            handles[platform] = handle

    # 2. all social links on page
    social_links = extract_social_links_from_page(soup, url)
    for link in social_links:
        if link['platform'] not in handles:
            handles[link['platform']] = link['handle']

    # 3. json-ld structured data
    json_ld = extract_json_ld(soup)
    for platform, handle in json_ld.items():
        if platform not in handles:
            handles[platform] = handle

    # 4. fediverse handles in text
    if raw:
        fedi = extract_fediverse_handles(raw)
        if fedi and 'mastodon' not in handles:
            handles['mastodon'] = fedi[0]

        # emails
        emails = extract_emails(raw)

    # 5. follow links to /about, /contact
    if follow_links:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        for path in ['/about', '/contact', '/links', '/social']:
            try:
                sub_soup, sub_raw = scrape_page(base + path)
                if sub_soup:
                    sub_links = extract_social_links_from_page(sub_soup, base)
                    for link in sub_links:
                        if link['platform'] not in handles:
                            handles[link['platform']] = link['handle']

                    if sub_raw:
                        fedi = extract_fediverse_handles(sub_raw)
                        if fedi and 'mastodon' not in handles:
                            handles['mastodon'] = fedi[0]

                        emails.extend(extract_emails(sub_raw))
            except:
                pass

    # 6. check for linktree etc in links and follow them
    for platform in ['linktree', 'biolink', 'carrd']:
        if platform in handles:
            # this is actually a link aggregator, scrape it
            link_url = None
            for link in social_links:
                if link['platform'] == platform:
                    link_url = link['url']
                    break

            if link_url:
                aggregator_handles = scrape_linktree(link_url)
                for p, h in aggregator_handles.items():
                    if p not in handles:
                        handles[p] = h

            del handles[platform]  # remove the aggregator itself

    return handles, list(set(emails))


def extract_handles_from_text(text):
    """extract handles from plain text (bio, README, etc)"""
    handles = {}

    if not text:
        return handles

    # fediverse handles
    fedi = extract_fediverse_handles(text)
    if fedi:
        handles['mastodon'] = fedi[0]

    # URL patterns in text
    url_pattern = re.compile(r'https?://[^\s<>"\']+')
    for match in url_pattern.finditer(text):
        url = match.group(0).rstrip('.,;:!?)')
        platform, handle = extract_handle_from_url(url)
        if platform and platform not in handles:
            handles[platform] = handle

    # twitter-style @mentions (only if looks like twitter context)
    if 'twitter' in text.lower() or 'x.com' in text.lower():
        twitter_pattern = re.compile(r'(?:^|[^\w])@(\w{1,15})(?:[^\w]|$)')
        for match in twitter_pattern.finditer(text):
            if 'twitter' not in handles:
                handles['twitter'] = f"@{match.group(1)}"

    # matrix handles
    matrix_pattern = re.compile(r'@([\w.-]+):([\w.-]+)')
    for match in matrix_pattern.finditer(text):
        if 'matrix' not in handles:
            handles['matrix'] = f"@{match.group(1)}:{match.group(2)}"

    return handles


def scrape_github_readme(username):
    """scrape user's profile README (username/username repo)"""
    handles = {}
    emails = []

    url = f"https://raw.githubusercontent.com/{username}/{username}/main/README.md"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            text = resp.text

            # extract handles from text
            handles = extract_handles_from_text(text)

            # extract emails
            emails = extract_emails(text)

            return handles, emails
    except:
        pass

    # try master branch
    url = f"https://raw.githubusercontent.com/{username}/{username}/master/README.md"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            text = resp.text
            handles = extract_handles_from_text(text)
            emails = extract_emails(text)
    except:
        pass

    return handles, emails


def discover_all_handles(github_profile):
    """
    comprehensive handle discovery from a github profile dict

    github_profile should contain:
    - username
    - bio
    - blog (website URL)
    - twitter_username
    - etc.
    """
    handles = {}
    emails = []

    username = github_profile.get('login') or github_profile.get('username')

    print(f"    discovering handles for {username}...")

    # 1. github bio
    bio = github_profile.get('bio', '')
    if bio:
        bio_handles = extract_handles_from_text(bio)
        handles.update(bio_handles)
        emails.extend(extract_emails(bio))

    # 2. twitter from github profile
    twitter = github_profile.get('twitter_username')
    if twitter and 'twitter' not in handles:
        handles['twitter'] = f"@{twitter}"

    # 3. website from github profile
    website = github_profile.get('blog')
    if website:
        if not website.startswith('http'):
            website = f"https://{website}"

        print(f"      scraping website: {website}")
        site_handles, site_emails = scrape_website_for_handles(website)
        for p, h in site_handles.items():
            if p not in handles:
                handles[p] = h
        emails.extend(site_emails)

    # 4. profile README
    if username:
        print(f"      checking profile README...")
        readme_handles, readme_emails = scrape_github_readme(username)
        for p, h in readme_handles.items():
            if p not in handles:
                handles[p] = h
        emails.extend(readme_emails)

    # 5. email from github profile
    github_email = github_profile.get('email')
    if github_email:
        emails.append(github_email)

    # dedupe emails
    emails = list(set(e for e in emails if e and '@' in e and 'noreply' not in e.lower()))

    print(f"      found {len(handles)} handles, {len(emails)} emails")

    return handles, emails


def merge_handles(existing, new):
    """merge new handles into existing, preferring more specific handles"""
    for platform, handle in new.items():
        if platform not in existing:
            existing[platform] = handle
        elif len(handle) > len(existing[platform]):
            # prefer longer/more specific handles
            existing[platform] = handle

    return existing
