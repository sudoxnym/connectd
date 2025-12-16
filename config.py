"""
connectd/config.py - central configuration

all configurable settings in one place.
"""

import os
from pathlib import Path

# base paths
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / 'db'
DATA_DIR = BASE_DIR / 'data'
CACHE_DIR = DB_DIR / 'cache'

# ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)


# === DAEMON CONFIG ===
SCOUT_INTERVAL = 3600 * 4       # full scout every 4 hours
MATCH_INTERVAL = 3600           # check matches every hour
INTRO_INTERVAL = 1800       # send intros every 2 hours
MAX_INTROS_PER_DAY = 250         # rate limit builder-to-builder outreach


# === MATCHING CONFIG ===
MIN_OVERLAP_PRIORITY = 30       # min score for priority user matches
MIN_OVERLAP_STRANGERS = 50      # higher bar for stranger intros
MIN_HUMAN_SCORE = 25            # min values score to be considered


# === LOST BUILDER CONFIG ===
# these people need encouragement, not networking.
# the goal isn't to recruit them - it's to show them the door exists.

LOST_CONFIG = {
    # detection thresholds
    'min_lost_score': 40,           # minimum lost_potential_score
    'min_values_score': 20,         # must have SOME values alignment

    # outreach settings
    'enabled': True,
    'max_per_day': 20,               # lower volume, higher care
    'require_review': False,        # fully autonomous
    'cooldown_days': 90,            # don't spam struggling people

    # matching settings
    'min_builder_score': 50,        # inspiring builders must be active
    'min_match_overlap': 10,        # must have SOME shared interests

    # LLM drafting
    'use_llm': True,
    'llm_temperature': 0.7,         # be genuine, not robotic

    # message guidelines (for LLM prompt)
    'tone': 'genuine, not salesy',
    'max_words': 150,               # they don't have energy for long messages
    'no_pressure': True,            # never pushy
    'sign_off': '- connectd',
}


# === API CREDENTIALS ===
# all credentials from environment variables - no defaults

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
MASTODON_TOKEN = os.environ.get('MASTODON_TOKEN', '')
MASTODON_INSTANCE = os.environ.get('MASTODON_INSTANCE', '')

BLUESKY_HANDLE = os.environ.get('BLUESKY_HANDLE', '')
BLUESKY_APP_PASSWORD = os.environ.get('BLUESKY_APP_PASSWORD', '')

MATRIX_HOMESERVER = os.environ.get('MATRIX_HOMESERVER', '')
MATRIX_USER_ID = os.environ.get('MATRIX_USER_ID', '')
MATRIX_ACCESS_TOKEN = os.environ.get('MATRIX_ACCESS_TOKEN', '')

DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
DISCORD_TARGET_SERVERS = os.environ.get('DISCORD_TARGET_SERVERS', '')

# lemmy (for authenticated access to private instance)
LEMMY_INSTANCE = os.environ.get('LEMMY_INSTANCE', '')
LEMMY_USERNAME = os.environ.get('LEMMY_USERNAME', '')
LEMMY_PASSWORD = os.environ.get('LEMMY_PASSWORD', '')

# email (for sending intros)
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')

# === HOST USER CONFIG ===
# the person running connectd - gets priority matching
HOST_USER = os.environ.get('HOST_USER', '')  # alias like sudoxnym
HOST_NAME = os.environ.get('HOST_NAME', '')
HOST_EMAIL = os.environ.get('HOST_EMAIL', '')
HOST_GITHUB = os.environ.get('HOST_GITHUB', '')
HOST_MASTODON = os.environ.get('HOST_MASTODON', '')  # user@instance
HOST_REDDIT = os.environ.get('HOST_REDDIT', '')
HOST_LEMMY = os.environ.get('HOST_LEMMY', '')  # user@instance
HOST_LOBSTERS = os.environ.get('HOST_LOBSTERS', '')
HOST_MATRIX = os.environ.get('HOST_MATRIX', '')  # @user:server
HOST_DISCORD = os.environ.get('HOST_DISCORD', '')  # user id
HOST_BLUESKY = os.environ.get('HOST_BLUESKY', '')  # handle.bsky.social
HOST_LOCATION = os.environ.get('HOST_LOCATION', '')
HOST_INTERESTS = os.environ.get('HOST_INTERESTS', '')  # comma separated
HOST_LOOKING_FOR = os.environ.get('HOST_LOOKING_FOR', '')


def get_lost_config():
    """get lost builder configuration"""
    return LOST_CONFIG.copy()


def update_lost_config(updates):
    """update lost builder configuration"""
    global LOST_CONFIG
    LOST_CONFIG.update(updates)
    return LOST_CONFIG.copy()
