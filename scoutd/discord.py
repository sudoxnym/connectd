"""
scoutd/discord.py - discord discovery

discord requires a bot token to read messages.
target servers: programming help, career transition, indie hackers, etc.

SETUP:
1. create discord app at discord.com/developers
2. add bot, get token
3. join target servers with bot
4. set DISCORD_BOT_TOKEN env var
"""

import requests
import json
import time
import os
from datetime import datetime
from pathlib import Path

from .signals import analyze_text
from .lost import (
    analyze_social_for_lost_signals,
    classify_user,
)

DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
DISCORD_API = 'https://discord.com/api/v10'

# server IDs to scout (add your own)
# these are public programming/career servers
TARGET_SERVERS = os.environ.get('DISCORD_TARGET_SERVERS', '').split(',')

# channels to focus on (keywords in channel name)
TARGET_CHANNEL_KEYWORDS = [
    'help', 'career', 'jobs', 'learning', 'beginner',
    'general', 'introductions', 'showcase', 'projects',
]

CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'discord'
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_headers():
    """get discord api headers"""
    if not DISCORD_BOT_TOKEN:
        return None
    return {
        'Authorization': f'Bot {DISCORD_BOT_TOKEN}',
        'Content-Type': 'application/json',
    }


def get_guild_channels(guild_id):
    """get channels in a guild"""
    headers = get_headers()
    if not headers:
        return []

    try:
        resp = requests.get(
            f'{DISCORD_API}/guilds/{guild_id}/channels',
            headers=headers,
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_channel_messages(channel_id, limit=100):
    """get recent messages from a channel"""
    headers = get_headers()
    if not headers:
        return []

    try:
        resp = requests.get(
            f'{DISCORD_API}/channels/{channel_id}/messages',
            headers=headers,
            params={'limit': limit},
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def get_user_info(user_id):
    """get discord user info"""
    headers = get_headers()
    if not headers:
        return None

    try:
        resp = requests.get(
            f'{DISCORD_API}/users/{user_id}',
            headers=headers,
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def analyze_discord_user(user_data, messages=None):
    """analyze a discord user for values alignment and lost signals"""
    username = user_data.get('username', '')
    display_name = user_data.get('global_name') or username
    user_id = user_data.get('id')

    # analyze messages
    all_signals = []
    all_text = []
    total_score = 0

    if messages:
        for msg in messages[:20]:
            content = msg.get('content', '')
            if not content or len(content) < 20:
                continue

            all_text.append(content)
            score, signals, _ = analyze_text(content)
            all_signals.extend(signals)
            total_score += score

    all_signals = list(set(all_signals))

    # lost builder detection
    profile_for_lost = {
        'bio': '',
        'message_count': len(messages) if messages else 0,
    }
    posts_for_lost = [{'text': t} for t in all_text]

    lost_signals, lost_weight = analyze_social_for_lost_signals(profile_for_lost, posts_for_lost)
    lost_potential_score = lost_weight
    user_type = classify_user(lost_potential_score, 50, total_score)

    return {
        'platform': 'discord',
        'username': username,
        'url': f"https://discord.com/users/{user_id}",
        'name': display_name,
        'bio': '',
        'location': None,
        'score': total_score,
        'confidence': min(0.8, 0.2 + len(all_signals) * 0.1),
        'signals': all_signals,
        'negative_signals': [],
        'reasons': [],
        'contact': {'discord': f"{username}#{user_data.get('discriminator', '0')}"},
        'extra': {
            'user_id': user_id,
            'message_count': len(messages) if messages else 0,
        },
        'lost_potential_score': lost_potential_score,
        'lost_signals': lost_signals,
        'user_type': user_type,
    }


def scrape_discord(db, limit_per_channel=50):
    """scrape discord servers for aligned builders"""
    if not DISCORD_BOT_TOKEN:
        print("discord: DISCORD_BOT_TOKEN not set, skipping")
        return 0

    if not TARGET_SERVERS or TARGET_SERVERS == ['']:
        print("discord: DISCORD_TARGET_SERVERS not set, skipping")
        return 0

    print("scouting discord...")

    found = 0
    lost_found = 0
    seen_users = set()

    for guild_id in TARGET_SERVERS:
        if not guild_id:
            continue

        guild_id = guild_id.strip()
        channels = get_guild_channels(guild_id)

        if not channels:
            print(f"  guild {guild_id}: no access or no channels")
            continue

        # filter to relevant channels
        target_channels = []
        for ch in channels:
            if ch.get('type') != 0:  # text channels only
                continue
            name = ch.get('name', '').lower()
            if any(kw in name for kw in TARGET_CHANNEL_KEYWORDS):
                target_channels.append(ch)

        print(f"  guild {guild_id}: {len(target_channels)} relevant channels")

        for channel in target_channels[:5]:  # limit channels per server
            messages = get_channel_messages(channel['id'], limit=limit_per_channel)

            if not messages:
                continue

            # group messages by user
            user_messages = {}
            for msg in messages:
                author = msg.get('author', {})
                if author.get('bot'):
                    continue

                user_id = author.get('id')
                if not user_id or user_id in seen_users:
                    continue

                if user_id not in user_messages:
                    user_messages[user_id] = {'user': author, 'messages': []}
                user_messages[user_id]['messages'].append(msg)

            # analyze each user
            for user_id, data in user_messages.items():
                if user_id in seen_users:
                    continue
                seen_users.add(user_id)

                result = analyze_discord_user(data['user'], data['messages'])
                if not result:
                    continue

                if result['score'] >= 20 or result.get('lost_potential_score', 0) >= 30:
                    db.save_human(result)
                    found += 1

                    if result.get('user_type') in ['lost', 'both']:
                        lost_found += 1

            time.sleep(1)  # rate limit between channels

        time.sleep(2)  # between guilds

    print(f"discord: found {found} humans ({lost_found} lost builders)")
    return found


def send_discord_dm(user_id, message, dry_run=False):
    """send a DM to a discord user"""
    if not DISCORD_BOT_TOKEN:
        return False, "DISCORD_BOT_TOKEN not set"

    if dry_run:
        print(f"  [dry run] would DM discord user {user_id}")
        return True, "dry run"

    headers = get_headers()

    try:
        # create DM channel
        dm_resp = requests.post(
            f'{DISCORD_API}/users/@me/channels',
            headers=headers,
            json={'recipient_id': user_id},
            timeout=30
        )

        if dm_resp.status_code not in [200, 201]:
            return False, f"couldn't create DM channel: {dm_resp.status_code}"

        channel_id = dm_resp.json().get('id')

        # send message
        msg_resp = requests.post(
            f'{DISCORD_API}/channels/{channel_id}/messages',
            headers=headers,
            json={'content': message},
            timeout=30
        )

        if msg_resp.status_code in [200, 201]:
            return True, f"sent to {user_id}"
        else:
            return False, f"send failed: {msg_resp.status_code}"

    except Exception as e:
        return False, str(e)
