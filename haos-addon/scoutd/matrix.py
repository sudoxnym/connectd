"""
scoutd/matrix.py - matrix room membership discovery
finds users in multiple aligned public rooms
"""

import requests
import json
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from .signals import analyze_text

HEADERS = {'User-Agent': 'connectd/1.0', 'Accept': 'application/json'}
CACHE_DIR = Path(__file__).parent.parent / 'db' / 'cache' / 'matrix'

# public matrix rooms to check membership
ALIGNED_ROOMS = [
    '#homeassistant:matrix.org',
    '#esphome:matrix.org',
    '#selfhosted:matrix.org',
    '#privacy:matrix.org',
    '#solarpunk:matrix.org',
    '#cooperative:matrix.org',
    '#foss:matrix.org',
    '#linux:matrix.org',
]

# homeservers to query
HOMESERVERS = [
    'matrix.org',
    'matrix.envs.net',
    'tchncs.de',
]


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

    time.sleep(1)

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        cache_file.write_text(json.dumps({'_cached_at': time.time(), '_data': result}))
        return result
    except requests.exceptions.RequestException as e:
        # matrix apis often fail, don't spam errors
        return None


def get_room_members(homeserver, room_alias):
    """
    get members of a public room
    note: most matrix servers don't expose this publicly
    this is a best-effort scrape
    """
    # resolve room alias to id first
    try:
        alias_url = f'https://{homeserver}/_matrix/client/r0/directory/room/{room_alias}'
        alias_data = _api_get(alias_url)
        if not alias_data or 'room_id' not in alias_data:
            return []

        room_id = alias_data['room_id']

        # try to get members (usually requires auth)
        members_url = f'https://{homeserver}/_matrix/client/r0/rooms/{room_id}/members'
        members_data = _api_get(members_url)

        if members_data and 'chunk' in members_data:
            members = []
            for event in members_data['chunk']:
                if event.get('type') == 'm.room.member' and event.get('content', {}).get('membership') == 'join':
                    user_id = event.get('state_key')
                    display_name = event.get('content', {}).get('displayname')
                    if user_id:
                        members.append({'user_id': user_id, 'display_name': display_name})
            return members
    except:
        pass

    return []


def get_public_rooms(homeserver, limit=100):
    """get public rooms directory"""
    url = f'https://{homeserver}/_matrix/client/r0/publicRooms'
    data = _api_get(url, {'limit': limit})
    return data.get('chunk', []) if data else []


def analyze_matrix_user(user_id, rooms_joined, display_name=None):
    """analyze a matrix user based on room membership"""
    # score based on room membership overlap
    room_score = len(rooms_joined) * 10

    # multi-room bonus
    if len(rooms_joined) >= 4:
        room_score += 20
    elif len(rooms_joined) >= 2:
        room_score += 10

    # analyze display name if available
    text_score = 0
    signals = []
    if display_name:
        text_score, signals, _ = analyze_text(display_name)

    total_score = room_score + text_score

    confidence = 0.3
    if len(rooms_joined) >= 3:
        confidence += 0.3
    if display_name:
        confidence += 0.1
    confidence = min(confidence, 0.8)

    reasons = [f"in {len(rooms_joined)} aligned rooms: {', '.join(rooms_joined[:3])}"]
    if signals:
        reasons.append(f"signals: {', '.join(signals[:3])}")

    return {
        'platform': 'matrix',
        'username': user_id,
        'url': f"https://matrix.to/#/{user_id}",
        'name': display_name,
        'score': total_score,
        'confidence': confidence,
        'signals': signals,
        'rooms': rooms_joined,
        'reasons': reasons,
        'scraped_at': datetime.now().isoformat(),
    }


def scrape_matrix(db):
    """
    matrix scrape - limited due to auth requirements
    best effort on public room data
    """
    print("scoutd/matrix: starting scrape (limited - most apis require auth)...")

    user_rooms = defaultdict(list)

    # try to get public room directories
    for homeserver in HOMESERVERS:
        print(f"  checking {homeserver} public rooms...")
        rooms = get_public_rooms(homeserver, limit=50)

        for room in rooms:
            room_alias = room.get('canonical_alias', '')
            # check if it matches any aligned room patterns
            aligned_keywords = ['homeassistant', 'selfhosted', 'privacy', 'linux', 'foss', 'cooperative']
            if any(kw in room_alias.lower() or kw in room.get('name', '').lower() for kw in aligned_keywords):
                print(f"    found aligned room: {room_alias or room.get('name')}")

    # try to get members from aligned rooms (usually fails without auth)
    for room_alias in ALIGNED_ROOMS[:3]:  # limit attempts
        for homeserver in HOMESERVERS[:1]:  # just try matrix.org
            members = get_room_members(homeserver, room_alias)
            if members:
                print(f"  {room_alias}: {len(members)} members")
                for member in members:
                    user_rooms[member['user_id']].append(room_alias)

    # filter for multi-room users
    multi_room = {u: rooms for u, rooms in user_rooms.items() if len(rooms) >= 2}
    print(f"  {len(multi_room)} users in 2+ aligned rooms")

    # analyze
    results = []
    for user_id, rooms in multi_room.items():
        try:
            result = analyze_matrix_user(user_id, rooms)
            if result and result['score'] > 0:
                results.append(result)
                db.save_human(result)
        except Exception as e:
            print(f"    error: {e}")

    print(f"scoutd/matrix: found {len(results)} aligned humans (limited by auth)")
    return results
