"""
scoutd - discovery module
finds humans across platforms
"""

from .github import scrape_github, get_github_user
from .reddit import scrape_reddit
from .mastodon import scrape_mastodon
from .lobsters import scrape_lobsters
from .matrix import scrape_matrix
from .twitter import scrape_twitter
from .bluesky import scrape_bluesky
from .lemmy import scrape_lemmy
from .discord import scrape_discord, send_discord_dm
from .deep import (
    deep_scrape_github_user, check_already_connected, save_deep_profile,
    determine_contact_method, get_cached_orgs, cache_orgs,
    get_emails_from_commit_history, scrape_website_for_emails,
)

__all__ = [
    'scrape_github', 'scrape_reddit', 'scrape_mastodon', 'scrape_lobsters',
    'scrape_matrix', 'scrape_twitter', 'scrape_bluesky', 'scrape_lemmy',
    'scrape_discord', 'send_discord_dm',
    'get_github_user', 'deep_scrape_github_user',
    'check_already_connected', 'save_deep_profile', 'determine_contact_method',
    'get_cached_orgs', 'cache_orgs', 'get_emails_from_commit_history',
    'scrape_website_for_emails',
]
