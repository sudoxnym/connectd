"""
connectd database layer
sqlite storage for humans, fingerprints, matches, intros
"""

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path

# use env var for DB path (docker) or default to local
DB_PATH = Path(os.environ.get('DB_PATH', Path(__file__).parent / 'connectd.db'))


class Database:
    def __init__(self, path=None):
        self.path = path or DB_PATH
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        c = self.conn.cursor()

        # humans table - all discovered people
        c.execute('''CREATE TABLE IF NOT EXISTS humans (
            id INTEGER PRIMARY KEY,
            platform TEXT NOT NULL,
            username TEXT NOT NULL,
            url TEXT,
            name TEXT,
            bio TEXT,
            location TEXT,
            score REAL DEFAULT 0,
            confidence REAL DEFAULT 0,
            signals TEXT,
            negative_signals TEXT,
            reasons TEXT,
            contact TEXT,
            extra TEXT,
            fingerprint_id INTEGER,
            scraped_at TEXT,
            updated_at TEXT,
            lost_potential_score REAL DEFAULT 0,
            lost_signals TEXT,
            user_type TEXT DEFAULT 'none',
            last_lost_outreach TEXT,
            UNIQUE(platform, username)
        )''')

        # migration: add new columns if they don't exist
        try:
            c.execute('ALTER TABLE humans ADD COLUMN lost_potential_score REAL DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # column exists

        try:
            c.execute('ALTER TABLE humans ADD COLUMN lost_signals TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            c.execute('ALTER TABLE humans ADD COLUMN user_type TEXT DEFAULT "none"')
        except sqlite3.OperationalError:
            pass

        try:
            c.execute('ALTER TABLE humans ADD COLUMN last_lost_outreach TEXT')
        except sqlite3.OperationalError:
            pass

        # fingerprints table - values profiles
        c.execute('''CREATE TABLE IF NOT EXISTS fingerprints (
            id INTEGER PRIMARY KEY,
            human_id INTEGER,
            values_vector TEXT,
            skills TEXT,
            interests TEXT,
            location_pref TEXT,
            availability TEXT,
            generated_at TEXT,
            FOREIGN KEY(human_id) REFERENCES humans(id)
        )''')

        # matches table - paired humans
        c.execute('''CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY,
            human_a_id INTEGER,
            human_b_id INTEGER,
            overlap_score REAL,
            overlap_reasons TEXT,
            complementary_skills TEXT,
            geographic_match INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            reviewed_at TEXT,
            FOREIGN KEY(human_a_id) REFERENCES humans(id),
            FOREIGN KEY(human_b_id) REFERENCES humans(id),
            UNIQUE(human_a_id, human_b_id)
        )''')

        # intros table - outreach attempts
        c.execute('''CREATE TABLE IF NOT EXISTS intros (
            id INTEGER PRIMARY KEY,
            match_id INTEGER,
            recipient_human_id INTEGER,
            channel TEXT,
            draft TEXT,
            status TEXT DEFAULT 'draft',
            approved_by TEXT,
            approved_at TEXT,
            sent_at TEXT,
            response TEXT,
            response_at TEXT,
            FOREIGN KEY(match_id) REFERENCES matches(id),
            FOREIGN KEY(recipient_human_id) REFERENCES humans(id)
        )''')

        # cross-platform links
        c.execute('''CREATE TABLE IF NOT EXISTS cross_platform (
            id INTEGER PRIMARY KEY,
            human_a_id INTEGER,
            human_b_id INTEGER,
            confidence REAL,
            reason TEXT,
            FOREIGN KEY(human_a_id) REFERENCES humans(id),
            FOREIGN KEY(human_b_id) REFERENCES humans(id),
            UNIQUE(human_a_id, human_b_id)
        )''')

        self.conn.commit()

    def save_human(self, data):
        """save or update a human record"""
        c = self.conn.cursor()

        # fields to exclude from extra json
        exclude_fields = ['platform', 'username', 'url', 'name', 'bio',
                          'location', 'score', 'confidence', 'signals',
                          'negative_signals', 'reasons', 'contact',
                          'lost_potential_score', 'lost_signals', 'user_type']

        c.execute('''INSERT OR REPLACE INTO humans
            (platform, username, url, name, bio, location, score, confidence,
             signals, negative_signals, reasons, contact, extra, scraped_at, updated_at,
             lost_potential_score, lost_signals, user_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (data.get('platform'),
             data.get('username'),
             data.get('url'),
             data.get('name'),
             data.get('bio'),
             data.get('location'),
             data.get('score', 0),
             data.get('confidence', 0),
             json.dumps(data.get('signals', [])),
             json.dumps(data.get('negative_signals', [])),
             json.dumps(data.get('reasons', [])),
             json.dumps(data.get('contact', {})),
             json.dumps({k: v for k, v in data.items() if k not in exclude_fields}),
             data.get('scraped_at', datetime.now().isoformat()),
             datetime.now().isoformat(),
             data.get('lost_potential_score', 0),
             json.dumps(data.get('lost_signals', [])),
             data.get('user_type', 'none')))

        self.conn.commit()
        return c.lastrowid

    def get_human(self, platform, username):
        """get a human by platform and username"""
        c = self.conn.cursor()
        c.execute('SELECT * FROM humans WHERE platform = ? AND username = ?',
                  (platform, username))
        row = c.fetchone()
        return dict(row) if row else None

    def get_human_by_id(self, human_id):
        """get a human by id"""
        c = self.conn.cursor()
        c.execute('SELECT * FROM humans WHERE id = ?', (human_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_all_humans(self, min_score=0, limit=1000):
        """get all humans above score threshold"""
        c = self.conn.cursor()
        c.execute('''SELECT * FROM humans
                     WHERE score >= ?
                     ORDER BY score DESC, confidence DESC
                     LIMIT ?''', (min_score, limit))
        return [dict(row) for row in c.fetchall()]

    def get_humans_by_platform(self, platform, min_score=0, limit=500):
        """get humans for a specific platform"""
        c = self.conn.cursor()
        c.execute('''SELECT * FROM humans
                     WHERE platform = ? AND score >= ?
                     ORDER BY score DESC
                     LIMIT ?''', (platform, min_score, limit))
        return [dict(row) for row in c.fetchall()]

    def get_lost_builders(self, min_lost_score=40, min_values_score=20, limit=100):
        """get lost builders who need encouragement"""
        c = self.conn.cursor()
        c.execute('''SELECT * FROM humans
                     WHERE user_type = 'lost' OR user_type = 'both'
                     AND lost_potential_score >= ?
                     AND score >= ?
                     ORDER BY lost_potential_score DESC, score DESC
                     LIMIT ?''', (min_lost_score, min_values_score, limit))
        return [dict(row) for row in c.fetchall()]

    def get_lost_builders_for_outreach(self, min_lost_score=40, min_values_score=20,
                                        cooldown_days=90, limit=50):
        """get lost builders who are ready for outreach (respecting cooldown)"""
        c = self.conn.cursor()
        c.execute('''SELECT * FROM humans
                     WHERE (user_type = 'lost' OR user_type = 'both')
                     AND lost_potential_score >= ?
                     AND score >= ?
                     AND (last_lost_outreach IS NULL
                          OR datetime(last_lost_outreach) < datetime('now', '-' || ? || ' days'))
                     ORDER BY lost_potential_score DESC, score DESC
                     LIMIT ?''', (min_lost_score, min_values_score, cooldown_days, limit))
        return [dict(row) for row in c.fetchall()]

    def get_active_builders(self, min_score=50, limit=100):
        """get active builders who can inspire lost builders"""
        c = self.conn.cursor()
        c.execute('''SELECT * FROM humans
                     WHERE user_type = 'builder'
                     AND score >= ?
                     ORDER BY score DESC, confidence DESC
                     LIMIT ?''', (min_score, limit))
        return [dict(row) for row in c.fetchall()]

    def mark_lost_outreach(self, human_id):
        """mark that we reached out to a lost builder"""
        c = self.conn.cursor()
        c.execute('''UPDATE humans SET last_lost_outreach = ? WHERE id = ?''',
                  (datetime.now().isoformat(), human_id))
        self.conn.commit()

    def save_fingerprint(self, human_id, fingerprint_data):
        """save a fingerprint for a human"""
        c = self.conn.cursor()
        c.execute('''INSERT OR REPLACE INTO fingerprints
            (human_id, values_vector, skills, interests, location_pref, availability, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (human_id,
             json.dumps(fingerprint_data.get('values_vector', {})),
             json.dumps(fingerprint_data.get('skills', [])),
             json.dumps(fingerprint_data.get('interests', [])),
             fingerprint_data.get('location_pref'),
             fingerprint_data.get('availability'),
             datetime.now().isoformat()))

        # update human's fingerprint_id
        c.execute('UPDATE humans SET fingerprint_id = ? WHERE id = ?',
                  (c.lastrowid, human_id))
        self.conn.commit()
        return c.lastrowid

    def get_fingerprint(self, human_id):
        """get fingerprint for a human"""
        c = self.conn.cursor()
        c.execute('SELECT * FROM fingerprints WHERE human_id = ?', (human_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def save_match(self, human_a_id, human_b_id, match_data):
        """save a match between two humans"""
        c = self.conn.cursor()
        c.execute('''INSERT OR REPLACE INTO matches
            (human_a_id, human_b_id, overlap_score, overlap_reasons,
             complementary_skills, geographic_match, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (human_a_id, human_b_id,
             match_data.get('overlap_score', 0),
             json.dumps(match_data.get('overlap_reasons', [])),
             json.dumps(match_data.get('complementary_skills', [])),
             1 if match_data.get('geographic_match') else 0,
             'pending',
             datetime.now().isoformat()))
        self.conn.commit()
        return c.lastrowid

    def get_matches(self, status=None, limit=100):
        """get matches, optionally filtered by status"""
        c = self.conn.cursor()
        if status:
            c.execute('''SELECT * FROM matches WHERE status = ?
                         ORDER BY overlap_score DESC LIMIT ?''', (status, limit))
        else:
            c.execute('''SELECT * FROM matches
                         ORDER BY overlap_score DESC LIMIT ?''', (limit,))
        return [dict(row) for row in c.fetchall()]

    def save_intro(self, match_id, recipient_id, channel, draft):
        """save an intro draft"""
        c = self.conn.cursor()
        c.execute('''INSERT INTO intros
            (match_id, recipient_human_id, channel, draft, status)
            VALUES (?, ?, ?, ?, 'draft')''',
            (match_id, recipient_id, channel, draft))
        self.conn.commit()
        return c.lastrowid

    def get_pending_intros(self, limit=50):
        """get intros pending approval"""
        c = self.conn.cursor()
        c.execute('''SELECT * FROM intros WHERE status = 'draft'
                     ORDER BY id DESC LIMIT ?''', (limit,))
        return [dict(row) for row in c.fetchall()]

    def approve_intro(self, intro_id, approved_by='human'):
        """approve an intro for sending"""
        c = self.conn.cursor()
        c.execute('''UPDATE intros SET status = 'approved',
                     approved_by = ?, approved_at = ? WHERE id = ?''',
                  (approved_by, datetime.now().isoformat(), intro_id))
        self.conn.commit()

    def mark_intro_sent(self, intro_id):
        """mark an intro as sent"""
        c = self.conn.cursor()
        c.execute('''UPDATE intros SET status = 'sent', sent_at = ? WHERE id = ?''',
                  (datetime.now().isoformat(), intro_id))
        self.conn.commit()

    def stats(self):
        """get database statistics"""
        c = self.conn.cursor()
        stats = {}

        c.execute('SELECT COUNT(*) FROM humans')
        stats['total_humans'] = c.fetchone()[0]

        c.execute('SELECT platform, COUNT(*) FROM humans GROUP BY platform')
        stats['by_platform'] = {row[0]: row[1] for row in c.fetchall()}

        c.execute('SELECT COUNT(*) FROM humans WHERE score >= 50')
        stats['high_score_humans'] = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM matches')
        stats['total_matches'] = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM matches WHERE status = "intro_sent"')
        stats['total_intros'] = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM matches WHERE status = "intro_sent"')
        stats['sent_intros'] = c.fetchone()[0]

        # lost builder stats
        c.execute("SELECT COUNT(*) FROM humans WHERE user_type = 'builder'")
        stats['active_builders'] = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM humans WHERE user_type = 'lost'")
        stats['lost_builders'] = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM humans WHERE user_type = 'both'")
        stats['recovering_builders'] = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM humans WHERE lost_potential_score >= 40')
        stats['high_lost_score'] = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM humans WHERE last_lost_outreach IS NOT NULL')
        stats['lost_outreach_sent'] = c.fetchone()[0]

        return stats

    def close(self):
        self.conn.close()
