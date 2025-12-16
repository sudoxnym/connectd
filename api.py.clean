#!/usr/bin/env python3
"""
connectd/api.py - REST API for stats and control

exposes daemon stats for home assistant integration.
runs on port 8099 by default.
"""

import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from db import Database
from db.users import get_priority_users, get_priority_user_matches, get_priority_user

API_PORT = int(os.environ.get('CONNECTD_API_PORT', 8099))

# shared state (updated by daemon)
_daemon_state = {
    'running': False,
    'dry_run': False,
    'last_scout': None,
    'last_match': None,
    'last_intro': None,
    'last_lost': None,
    'intros_today': 0,
    'lost_intros_today': 0,
    'started_at': None,
}


def update_daemon_state(state_dict):
    """update shared daemon state (called by daemon)"""
    global _daemon_state
    _daemon_state.update(state_dict)


def get_daemon_state():
    """get current daemon state"""
    return _daemon_state.copy()


class APIHandler(BaseHTTPRequestHandler):
    """simple REST API handler"""

    def log_message(self, format, *args):
        """suppress default logging"""
        pass

    def _send_json(self, data, status=200):
        """send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        """handle GET requests"""
        if self.path == '/api/stats':
            self._handle_stats()
        elif self.path == '/api/health':
            self._handle_health()
        elif self.path == '/api/state':
            self._handle_state()
        elif self.path == '/api/priority_matches':
            self._handle_priority_matches()
        elif self.path == '/api/top_humans':
            self._handle_top_humans()
        elif self.path == '/api/user':
            self._handle_user()
        else:
            self._send_json({'error': 'not found'}, 404)

    def _handle_stats(self):
        """return database statistics"""
        try:
            db = Database()
            stats = db.stats()
            db.close()
            self._send_json(stats)
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_health(self):
        """return daemon health status"""
        state = get_daemon_state()

        health = {
            'status': 'running' if state['running'] else 'stopped',
            'dry_run': state['dry_run'],
            'uptime_seconds': None,
        }

        if state['started_at']:
            uptime = datetime.now() - datetime.fromisoformat(state['started_at'])
            health['uptime_seconds'] = int(uptime.total_seconds())

        self._send_json(health)

    def _handle_state(self):
        """return full daemon state"""
        state = get_daemon_state()

        # convert datetimes to strings
        for key in ['last_scout', 'last_match', 'last_intro', 'last_lost', 'started_at']:
            if state[key] and isinstance(state[key], datetime):
                state[key] = state[key].isoformat()

        self._send_json(state)

    def _handle_priority_matches(self):
        """return priority matches for HA sensor"""
        try:
            db = Database()
            users = get_priority_users(db.conn)

            if not users:
                self._send_json({
                    'count': 0,
                    'new_count': 0,
                    'top_matches': [],
                })
                db.close()
                return

            # get matches for first priority user (host)
            user = users[0]
            matches = get_priority_user_matches(db.conn, user['id'], limit=10)

            new_count = sum(1 for m in matches if m.get('status') == 'new')

            top_matches = []
            for m in matches[:5]:
                overlap_reasons = m.get('overlap_reasons', '[]')
                if isinstance(overlap_reasons, str):
                    import json as json_mod
                    overlap_reasons = json_mod.loads(overlap_reasons) if overlap_reasons else []

                top_matches.append({
                    'username': m.get('username'),
                    'platform': m.get('platform'),
                    'score': m.get('score', 0),
                    'overlap_score': m.get('overlap_score', 0),
                    'reasons': overlap_reasons[:3],
                    'url': m.get('url'),
                    'status': m.get('status', 'new'),
                })

            db.close()
            self._send_json({
                'count': len(matches),
                'new_count': new_count,
                'top_matches': top_matches,
            })
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_top_humans(self):
        """return top scoring humans for HA sensor"""
        try:
            db = Database()
            humans = db.get_all_humans(min_score=50, limit=5)

            top_humans = []
            for h in humans:
                contact = h.get('contact', '{}')
                if isinstance(contact, str):
                    import json as json_mod
                    contact = json_mod.loads(contact) if contact else {}

                signals = h.get('signals', '[]')
                if isinstance(signals, str):
                    import json as json_mod
                    signals = json_mod.loads(signals) if signals else []

                top_humans.append({
                    'username': h.get('username'),
                    'platform': h.get('platform'),
                    'score': h.get('score', 0),
                    'name': h.get('name'),
                    'signals': signals[:5],
                    'contact_method': 'email' if contact.get('email') else
                                     'mastodon' if contact.get('mastodon') else
                                     'matrix' if contact.get('matrix') else 'manual',
                })

            db.close()
            self._send_json({
                'count': len(humans),
                'top_humans': top_humans,
            })
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_user(self):
        """return priority user info for HA sensor"""
        try:
            db = Database()
            users = get_priority_users(db.conn)

            if not users:
                self._send_json({
                    'configured': False,
                    'score': 0,
                    'signals': [],
                    'match_count': 0,
                })
                db.close()
                return

            user = users[0]
            signals = user.get('signals', '[]')
            if isinstance(signals, str):
                import json as json_mod
                signals = json_mod.loads(signals) if signals else []

            interests = user.get('interests', '[]')
            if isinstance(interests, str):
                import json as json_mod
                interests = json_mod.loads(interests) if interests else []

            matches = get_priority_user_matches(db.conn, user['id'], limit=100)

            db.close()
            self._send_json({
                'configured': True,
                'name': user.get('name'),
                'github': user.get('github'),
                'mastodon': user.get('mastodon'),
                'reddit': user.get('reddit'),
                'lobsters': user.get('lobsters'),
                'matrix': user.get('matrix'),
                'lemmy': user.get('lemmy'),
                'discord': user.get('discord'),
                'bluesky': user.get('bluesky'),
                'score': user.get('score', 0),
                'signals': signals[:10],
                'interests': interests,
                'location': user.get('location'),
                'bio': user.get('bio'),
                'match_count': len(matches),
                'new_match_count': sum(1 for m in matches if m.get('status') == 'new'),
            })
        except Exception as e:
            self._send_json({'error': str(e)}, 500)


def run_api_server():
    """run the API server in a thread"""
    server = HTTPServer(('0.0.0.0', API_PORT), APIHandler)
    print(f"connectd api running on port {API_PORT}")
    server.serve_forever()


def start_api_thread():
    """start API server in background thread"""
    thread = threading.Thread(target=run_api_server, daemon=True)
    thread.start()
    return thread


if __name__ == '__main__':
    # standalone mode for testing
    print(f"starting connectd api on port {API_PORT}...")
    run_api_server()
