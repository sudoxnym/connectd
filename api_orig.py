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
        path = self.path.split('?')[0]  # strip query params for routing
        if path == '/api/stats':
            self._handle_stats()
        elif path == '/api/health':
            self._handle_health()
        elif path == '/api/state':
            self._handle_state()
        elif path == '/api/priority_matches':
            self._handle_priority_matches()
        elif path == '/api/top_humans':
            self._handle_top_humans()
        elif path == '/api/user':
            self._handle_user()
        elif path == '/dashboard' or path == '/':
            self._handle_dashboard()
        elif path == '/api/preview_intros':
            self._handle_preview_intros()
        elif path == '/api/sent_intros':
            self._handle_sent_intros()
        elif path == '/api/failed_intros':
            self._handle_failed_intros()
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


# === DASHBOARD ENDPOINTS ===

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>connectd dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: monospace;
            background: #0a0a0f;
            color: #00ffc8;
            padding: 20px;
            line-height: 1.6;
        }
        h1 { color: #c792ea; margin-bottom: 20px; }
        h2 { color: #82aaff; margin: 20px 0 10px; border-bottom: 1px solid #333; padding-bottom: 5px; }
        .stats { display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 20px; }
        .stat {
            background: #1a1a2e;
            padding: 15px 25px;
            border-radius: 8px;
            border: 1px solid #333;
        }
        .stat-value { font-size: 2em; color: #c792ea; }
        .stat-label { color: #888; font-size: 0.9em; }
        .intro-card {
            background: #1a1a2e;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .intro-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            color: #82aaff;
        }
        .intro-score {
            background: #2a2a4e;
            padding: 2px 8px;
            border-radius: 4px;
            color: #c792ea;
        }
        .intro-body {
            background: #0d0d15;
            padding: 15px;
            border-radius: 4px;
            white-space: pre-wrap;
            font-size: 0.95em;
            color: #ddd;
        }
        .intro-meta { color: #666; font-size: 0.85em; margin-top: 10px; }
        .method {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.85em;
        }
        .method-email { background: #2d4a2d; color: #8f8; }
        .method-mastodon { background: #3d3a5c; color: #c792ea; }
        .method-github { background: #2d3a4a; color: #82aaff; }
        .method-manual { background: #4a3a2d; color: #ffa; }
        .tab-buttons { margin-bottom: 20px; }
        .tab-btn {
            background: #1a1a2e;
            border: 1px solid #333;
            color: #00ffc8;
            padding: 10px 20px;
            cursor: pointer;
            font-family: monospace;
        }
        .tab-btn.active { background: #2a2a4e; border-color: #00ffc8; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .refresh-btn {
            background: #00ffc8;
            color: #0a0a0f;
            border: none;
            padding: 10px 20px;
            cursor: pointer;
            font-family: monospace;
            font-weight: bold;
            margin-left: 20px;
        }
        .error { color: #ff6b6b; }
        .success { color: #69ff69; }
    </style>
</head>
<body>
    <h1>connectd <span style="color:#666;font-size:0.6em">dashboard</span></h1>

    <div class="stats" id="stats"></div>

    <div class="tab-buttons">
        <button class="tab-btn active" onclick="showTab('pending')">pending previews</button>
        <button class="tab-btn" onclick="showTab('sent')">sent intros</button>
        <button class="tab-btn" onclick="showTab('failed')">failed</button>
        <button class="refresh-btn" onclick="loadAll()">refresh</button>
    </div>

    <div id="pending" class="tab-content active"></div>
    <div id="sent" class="tab-content"></div>
    <div id="failed" class="tab-content"></div>

    <script>
        async function loadStats() {
            const res = await fetch('/api/stats');
            const data = await res.json();
            document.getElementById('stats').innerHTML = `
                <div class="stat"><div class="stat-value">${data.total_humans}</div><div class="stat-label">humans tracked</div></div>
                <div class="stat"><div class="stat-value">${data.total_matches}</div><div class="stat-label">total matches</div></div>
                <div class="stat"><div class="stat-value">${data.sent_intros}</div><div class="stat-label">intros sent</div></div>
                <div class="stat"><div class="stat-value">${data.high_score_humans}</div><div class="stat-label">high score</div></div>
            `;
        }

        async function loadPending() {
            const res = await fetch('/api/preview_intros?limit=10');
            const data = await res.json();
            let html = '<h2>pending intro previews</h2>';
            if (data.previews) {
                for (const p of data.previews) {
                    html += `<div class="intro-card">
                        <div class="intro-header">
                            <span>${p.from_platform}:${p.from_user} -> ${p.to_platform}:${p.to_user}</span>
                            <span class="intro-score">score: ${p.score}</span>
                        </div>
                        <div class="intro-body">${p.draft || '[generating...]' }</div>
                        <div class="intro-meta">
                            method: <span class="method method-${p.method}">${p.method}</span>
                            | contact: ${p.contact_info || 'n/a'}
                            | reasons: ${(p.reasons || []).slice(0,2).join(', ') || 'aligned values'}
                        </div>
                    </div>`;
                }
            }
            document.getElementById('pending').innerHTML = html;
        }

        async function loadSent() {
            const res = await fetch('/api/sent_intros?limit=20');
            const data = await res.json();
            let html = '<h2>sent intros</h2>';
            if (data.sent) {
                for (const s of data.sent) {
                    html += `<div class="intro-card">
                        <div class="intro-header">
                            <span>${s.recipient_id}</span>
                            <span class="method method-${s.method}">${s.method}</span>
                        </div>
                        <div class="intro-meta">
                            sent: ${s.timestamp} | score: ${s.overlap_score?.toFixed(0) || '?'}
                        </div>
                    </div>`;
                }
            }
            document.getElementById('sent').innerHTML = html;
        }

        async function loadFailed() {
            const res = await fetch('/api/failed_intros');
            const data = await res.json();
            let html = '<h2>failed deliveries</h2>';
            if (data.failed) {
                for (const f of data.failed) {
                    html += `<div class="intro-card">
                        <div class="intro-header">
                            <span>${f.recipient_id}</span>
                            <span class="method method-${f.method}">${f.method}</span>
                        </div>
                        <div class="intro-meta error">error: ${f.error}</div>
                    </div>`;
                }
            }
            document.getElementById('failed').innerHTML = html;
        }

        function showTab(name) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(name).classList.add('active');
            event.target.classList.add('active');
        }

        function loadAll() {
            loadStats();
            loadPending();
            loadSent();
            loadFailed();
        }

        loadAll();
        setInterval(loadAll, 30000);
    </script>
</body>
</html>
"""


class DashboardMixin:
    """mixin to add dashboard endpoints to APIHandler"""

    def _handle_dashboard(self):
        """serve the dashboard HTML"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(DASHBOARD_HTML.encode())

    def _handle_preview_intros(self):
        """preview pending intros with draft generation"""
        import sqlite3
        import json
        from introd.groq_draft import draft_intro_with_llm, determine_contact_method

        # parse limit from query string
        limit = 5
        if '?' in self.path:
            query = self.path.split('?')[1]
            for param in query.split('&'):
                if param.startswith('limit='):
                    try:
                        limit = int(param.split('=')[1])
                    except:
                        pass

        conn = sqlite3.connect('/data/db/connectd.db')
        c = conn.cursor()

        c.execute("""SELECT h1.username, h1.platform, h1.contact, h1.extra,
                            h2.username, h2.platform, h2.contact, h2.extra,
                            m.overlap_score, m.overlap_reasons
                     FROM matches m
                     JOIN humans h1 ON m.human_a_id = h1.id
                     JOIN humans h2 ON m.human_b_id = h2.id
                     WHERE m.status = 'pending' AND m.overlap_score >= 60
                     ORDER BY m.overlap_score DESC
                     LIMIT ?""", (limit,))

        previews = []
        for row in c.fetchall():
            human_a = {
                'username': row[0], 'platform': row[1],
                'contact': json.loads(row[2]) if row[2] else {},
                'extra': json.loads(row[3]) if row[3] else {}
            }
            human_b = {
                'username': row[4], 'platform': row[5],
                'contact': json.loads(row[6]) if row[6] else {},
                'extra': json.loads(row[7]) if row[7] else {}
            }
            reasons = json.loads(row[9]) if row[9] else []

            match_data = {
                'human_a': human_a, 'human_b': human_b,
                'overlap_score': row[8], 'overlap_reasons': reasons
            }

            # determine contact method
            method, contact_info = determine_contact_method(human_a)

            # generate draft (skip if too slow)
            draft = None
            try:
                result, _ = draft_intro_with_llm(match_data, recipient='a', dry_run=True)
                if result:
                    draft = result.get('draft')
            except:
                pass

            previews.append({
                'from_platform': human_b['platform'],
                'from_user': human_b['username'],
                'to_platform': human_a['platform'],
                'to_user': human_a['username'],
                'score': int(row[8]),
                'reasons': reasons[:3],
                'method': method,
                'contact_info': str(contact_info) if contact_info else None,
                'draft': draft
            })

        conn.close()
        self._send_json({'previews': previews})

    def _handle_sent_intros(self):
        """return sent intro history from delivery log"""
        import json
        from pathlib import Path

        limit = 20
        if '?' in self.path:
            query = self.path.split('?')[1]
            for param in query.split('&'):
                if param.startswith('limit='):
                    try:
                        limit = int(param.split('=')[1])
                    except:
                        pass

        log_path = Path('/app/data/delivery_log.json')
        if log_path.exists():
            with open(log_path) as f:
                log = json.load(f)
            sent = log.get('sent', [])[-limit:]
            sent.reverse()  # newest first
        else:
            sent = []

        self._send_json({'sent': sent})

    def _handle_failed_intros(self):
        """return failed delivery attempts"""
        import json
        from pathlib import Path

        log_path = Path('/app/data/delivery_log.json')
        if log_path.exists():
            with open(log_path) as f:
                log = json.load(f)
            failed = log.get('failed', [])
        else:
            failed = []

        self._send_json({'failed': failed})
