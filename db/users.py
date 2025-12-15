"""
priority users - people who host connectd get direct matching
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / 'connectd.db'

# map user-friendly interests to signal terms
INTEREST_TO_SIGNALS = {
    'self-hosting': ['selfhosted', 'home_automation'],
    'home-assistant': ['home_automation'],
    'intentional-community': ['community', 'cooperative'],
    'cooperatives': ['cooperative', 'community'],
    'solarpunk': ['solarpunk'],
    'privacy': ['privacy', 'local_first'],
    'local-first': ['local_first', 'privacy'],
    'queer-friendly': ['queer'],
    'anti-capitalism': ['cooperative', 'decentralized', 'community'],
    'esports-venue': [],
    'foss': ['foss'],
    'decentralized': ['decentralized'],
    'federated': ['federated_chat'],
    'mesh': ['mesh'],
}


def init_users_table(conn):
    """create priority users table"""
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS priority_users (
        id INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        github TEXT,
        reddit TEXT,
        mastodon TEXT,
        lobsters TEXT,
        matrix TEXT,
        location TEXT,
        bio TEXT,
        interests TEXT,
        looking_for TEXT,
        created_at TEXT,
        active INTEGER DEFAULT 1,
        score REAL DEFAULT 0,
        signals TEXT,
        scraped_profile TEXT,
        last_scored_at TEXT
    )''')

    # matches specifically for priority users
    c.execute('''CREATE TABLE IF NOT EXISTS priority_matches (
        id INTEGER PRIMARY KEY,
        priority_user_id INTEGER,
        matched_human_id INTEGER,
        overlap_score REAL,
        overlap_reasons TEXT,
        status TEXT DEFAULT 'new',
        notified_at TEXT,
        viewed_at TEXT,
        FOREIGN KEY(priority_user_id) REFERENCES priority_users(id),
        FOREIGN KEY(matched_human_id) REFERENCES humans(id)
    )''')

    conn.commit()


def add_priority_user(conn, user_data):
    """add a priority user (someone hosting connectd)"""
    c = conn.cursor()

    c.execute('''INSERT OR REPLACE INTO priority_users
        (name, email, github, reddit, mastodon, lobsters, matrix,
         location, bio, interests, looking_for, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (user_data.get('name'),
         user_data.get('email'),
         user_data.get('github'),
         user_data.get('reddit'),
         user_data.get('mastodon'),
         user_data.get('lobsters'),
         user_data.get('matrix'),
         user_data.get('location'),
         user_data.get('bio'),
         json.dumps(user_data.get('interests', [])),
         user_data.get('looking_for'),
         datetime.now().isoformat()))

    conn.commit()
    return c.lastrowid


def get_priority_users(conn):
    """get all active priority users"""
    c = conn.cursor()
    c.execute('SELECT * FROM priority_users WHERE active = 1')
    return [dict(row) for row in c.fetchall()]


def get_priority_user(conn, user_id):
    """get a specific priority user"""
    c = conn.cursor()
    c.execute('SELECT * FROM priority_users WHERE id = ?', (user_id,))
    row = c.fetchone()
    return dict(row) if row else None


def save_priority_match(conn, priority_user_id, human_id, overlap_data):
    """save a match for a priority user"""
    c = conn.cursor()

    c.execute('''INSERT OR IGNORE INTO priority_matches
        (priority_user_id, matched_human_id, overlap_score, overlap_reasons, status)
        VALUES (?, ?, ?, ?, 'new')''',
        (priority_user_id, human_id,
         overlap_data.get('overlap_score', 0),
         json.dumps(overlap_data.get('overlap_reasons', []))))

    conn.commit()
    return c.lastrowid


def get_priority_user_matches(conn, priority_user_id, status=None, limit=50):
    """get matches for a priority user"""
    c = conn.cursor()

    if status:
        c.execute('''SELECT pm.*, h.* FROM priority_matches pm
                     JOIN humans h ON pm.matched_human_id = h.id
                     WHERE pm.priority_user_id = ? AND pm.status = ?
                     ORDER BY pm.overlap_score DESC
                     LIMIT ?''', (priority_user_id, status, limit))
    else:
        c.execute('''SELECT pm.*, h.* FROM priority_matches pm
                     JOIN humans h ON pm.matched_human_id = h.id
                     WHERE pm.priority_user_id = ?
                     ORDER BY pm.overlap_score DESC
                     LIMIT ?''', (priority_user_id, limit))

    return [dict(row) for row in c.fetchall()]


def mark_match_viewed(conn, match_id):
    """mark a priority match as viewed"""
    c = conn.cursor()
    c.execute('''UPDATE priority_matches SET status = 'viewed', viewed_at = ?
                 WHERE id = ?''', (datetime.now().isoformat(), match_id))
    conn.commit()


def expand_interests_to_signals(interests):
    """expand user-friendly interests to signal terms"""
    signals = set()
    for interest in interests:
        interest_lower = interest.lower().strip()
        if interest_lower in INTEREST_TO_SIGNALS:
            signals.update(INTEREST_TO_SIGNALS[interest_lower])
        else:
            signals.add(interest_lower)

    # always add these aligned signals for priority users
    signals.update(['foss', 'decentralized', 'federated_chat', 'containers', 'unix', 'selfhosted'])
    return list(signals)


def score_priority_user(conn, user_id, scraped_profile=None):
    """
    calculate a score for a priority user based on:
    - their stated interests
    - their scraped github profile (if available)
    - their repos and activity
    """
    c = conn.cursor()
    c.execute('SELECT * FROM priority_users WHERE id = ?', (user_id,))
    row = c.fetchone()
    if not row:
        return None

    user = dict(row)
    score = 0
    signals = set()

    # 1. score from stated interests
    interests = user.get('interests')
    if isinstance(interests, str):
        interests = json.loads(interests) if interests else []

    for interest in interests:
        interest_lower = interest.lower()
        # high-value interests
        if 'solarpunk' in interest_lower:
            score += 30
            signals.add('solarpunk')
        if 'queer' in interest_lower:
            score += 30
            signals.add('queer')
        if 'cooperative' in interest_lower or 'intentional' in interest_lower:
            score += 20
            signals.add('cooperative')
        if 'privacy' in interest_lower:
            score += 10
            signals.add('privacy')
        if 'self-host' in interest_lower or 'selfhost' in interest_lower:
            score += 15
            signals.add('selfhosted')
        if 'home-assistant' in interest_lower:
            score += 15
            signals.add('home_automation')
        if 'foss' in interest_lower or 'open source' in interest_lower:
            score += 10
            signals.add('foss')

    # 2. score from scraped profile
    if scraped_profile:
        # repos
        repos = scraped_profile.get('top_repos', [])
        if len(repos) >= 20:
            score += 20
        elif len(repos) >= 10:
            score += 10
        elif len(repos) >= 5:
            score += 5

        # languages
        languages = scraped_profile.get('languages', {})
        if 'Python' in languages or 'Rust' in languages:
            score += 5
            signals.add('modern_lang')

        # topics from repos
        topics = scraped_profile.get('topics', [])
        for topic in topics:
            if topic in ['self-hosted', 'home-assistant', 'privacy', 'foss']:
                score += 10
                signals.add(topic.replace('-', '_'))

        # followers
        followers = scraped_profile.get('followers', 0)
        if followers >= 100:
            score += 15
        elif followers >= 50:
            score += 10
        elif followers >= 10:
            score += 5

    # 3. add expanded signals
    expanded = expand_interests_to_signals(interests)
    signals.update(expanded)

    # update user
    c.execute('''UPDATE priority_users
                 SET score = ?, signals = ?, scraped_profile = ?, last_scored_at = ?
                 WHERE id = ?''',
              (score, json.dumps(list(signals)), json.dumps(scraped_profile) if scraped_profile else None,
               datetime.now().isoformat(), user_id))
    conn.commit()

    return {'score': score, 'signals': list(signals)}


def auto_match_priority_user(conn, user_id, min_overlap=40):
    """
    automatically find and save matches for a priority user
    uses relationship filtering to skip already-connected people
    """
    from scoutd.deep import check_already_connected

    c = conn.cursor()

    # get user
    c.execute('SELECT * FROM priority_users WHERE id = ?', (user_id,))
    row = c.fetchone()
    if not row:
        return []

    user = dict(row)

    # get user signals
    user_signals = set()
    if user.get('signals'):
        signals = json.loads(user['signals']) if isinstance(user['signals'], str) else user['signals']
        user_signals.update(signals)

    # also expand interests
    if user.get('interests'):
        interests = json.loads(user['interests']) if isinstance(user['interests'], str) else user['interests']
        user_signals.update(expand_interests_to_signals(interests))

    # clear old matches
    c.execute('DELETE FROM priority_matches WHERE priority_user_id = ?', (user_id,))
    conn.commit()

    # get all humans
    c.execute('SELECT * FROM humans WHERE score >= 25')
    columns = [d[0] for d in c.description]

    matches = []
    for row in c.fetchall():
        human = dict(zip(columns, row))

        # skip own profiles
        username = (human.get('username') or '').lower()
        if user.get('github') and username == user['github'].lower():
            continue
        if user.get('reddit') and username == user.get('reddit', '').lower():
            continue

        # check if already connected
        user_human = {'username': user.get('github'), 'platform': 'github', 'extra': {}}
        connected, reason = check_already_connected(user_human, human)
        if connected:
            continue

        # get human signals
        human_signals = human.get('signals', [])
        if isinstance(human_signals, str):
            human_signals = json.loads(human_signals) if human_signals else []

        # calculate overlap
        shared = user_signals & set(human_signals)
        overlap_score = len(shared) * 10

        # high-value bonuses
        if 'queer' in human_signals:
            overlap_score += 40
            shared.add('queer (rare!)')
        if 'solarpunk' in human_signals:
            overlap_score += 30
            shared.add('solarpunk (rare!)')
        if 'cooperative' in human_signals:
            overlap_score += 20
            shared.add('cooperative (values)')

        # location bonus
        location = (human.get('location') or '').lower()
        user_location = (user.get('location') or '').lower()
        if user_location and location:
            if any(x in location for x in ['seattle', 'portland', 'pnw', 'washington', 'oregon']):
                if 'seattle' in user_location or 'pnw' in user_location:
                    overlap_score += 25
                    shared.add('PNW location!')

        if overlap_score >= min_overlap:
            matches.append({
                'human': human,
                'overlap_score': overlap_score,
                'shared': list(shared),
            })

    # sort and save top matches
    matches.sort(key=lambda x: x['overlap_score'], reverse=True)

    for m in matches[:50]:  # save top 50
        save_priority_match(conn, user_id, m['human']['id'], {
            'overlap_score': m['overlap_score'],
            'overlap_reasons': m['shared'],
        })

    return matches


def update_priority_user_profile(conn, user_id, profile_data):
    """update a priority user's profile with new data"""
    c = conn.cursor()

    updates = []
    values = []

    for field in ['name', 'email', 'github', 'reddit', 'mastodon', 'lobsters',
                  'matrix', 'location', 'bio', 'looking_for']:
        if field in profile_data and profile_data[field]:
            updates.append(f'{field} = ?')
            values.append(profile_data[field])

    if 'interests' in profile_data:
        updates.append('interests = ?')
        values.append(json.dumps(profile_data['interests']))

    if updates:
        values.append(user_id)
        c.execute(f'''UPDATE priority_users SET {', '.join(updates)} WHERE id = ?''', values)
        conn.commit()

    return True
