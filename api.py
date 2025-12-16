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

# central API config
import requests
CENTRAL_API = os.environ.get('CONNECTD_CENTRAL_API', '')
CENTRAL_KEY = os.environ.get('CONNECTD_API_KEY', '')

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



DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>connectd</title>
    <meta charset="utf-8">
    <link rel="icon" type="image/png" href="/favicon.png">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: monospace; background: #0a0a0f; color: #0f8; padding: 20px; }
        h1 { color: #c792ea; margin-bottom: 15px; }
        h2 { color: #82aaff; margin: 15px 0 10px; }

        .stats { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 15px; }
        .stat { background: #1a1a2e; padding: 10px 16px; border-radius: 6px; border: 1px solid #333; text-align: center; }
        .stat b { font-size: 1.6em; color: #c792ea; display: block; }
        .stat small { color: #666; font-size: 0.75em; }

        .card { background: #1a1a2e; border: 1px solid #333; border-radius: 6px; padding: 10px; margin-bottom: 8px; cursor: pointer; }
        .card:hover { border-color: #0f8; }
        .card-hdr { display: flex; justify-content: space-between; color: #82aaff; }
        .score { background: #2a2a4e; padding: 2px 8px; border-radius: 4px; color: #c792ea; }

        .body { background: #0d0d15; padding: 10px; border-radius: 4px; white-space: pre-wrap; color: #ddd; margin-top: 8px; font-size: 0.85em; display: none; }
        .meta { color: #666; font-size: 0.75em; margin-top: 5px; }

        .m { display: inline-block; padding: 1px 5px; border-radius: 3px; font-size: 0.75em; }
        .m-email { background: #2d4a2d; color: #8f8; }
        .m-mastodon { background: #3d3a5c; color: #c792ea; }
        .m-new { background: #2d3a4a; color: #82aaff; }

        .tabs { margin-bottom: 12px; }
        .tab { background: #1a1a2e; border: 1px solid #333; color: #0f8; padding: 6px 14px; cursor: pointer; font-family: monospace; font-size: 0.9em; }
        .tab.on { background: #2a2a4e; border-color: #0f8; }

        .pnl { display: none; }
        .pnl.on { display: block; }

        .btn { background: #0f8; color: #0a0a0f; border: none; padding: 6px 14px; cursor: pointer; font-family: monospace; font-weight: bold; margin-left: 10px; font-size: 0.9em; }
        .err { color: #f66; }
        a { color: #82aaff; }

        .status { font-size: 0.85em; color: #888; margin-bottom: 10px; }
        .status b { color: #0f8; }
        .cached { color: #555; font-size: 0.7em; }

        .to { color: #f7c; }
        .about { color: #82aaff; }

        .closebtn {
            background: #333;
            color: #f66;
            border: 1px solid #f66;
            padding: 4px 12px;
            cursor: pointer;
            font-family: monospace;
            margin-top: 10px;
            display: inline-block;
        }
        .closebtn:hover { background: #f66; color: #000; }
    </style>
</head>
<body>
    <h1>connectd
        <a href="https://github.com/sudoxnym/connectd" style="font-size:0.5em;color:#82aaff">repo</a>
        <a href="https://github.com/connectd-daemon" style="font-size:0.5em;color:#f7c">org</a>
    </h1>
    <div class="status" id="status"></div>
    <div class="stats" id="stats"></div>
    <div class="tabs" id="tabbar"></div>
    <div id="host" class="pnl on"></div>
    <div id="queue" class="pnl"></div>
    <div id="sent" class="pnl"></div>
    <div id="failed" class="pnl"></div>
    <div id="lost" class="pnl"></div>

<script>
var currentTab = 'host';

function $(id) { return document.getElementById(id); }

function initTabs() {
    var tabbar = $('tabbar');
    tabbar.innerHTML = '';

    var tabs = [
        {id: 'host', label: 'you'},
        {id: 'queue', label: 'queue'},
        {id: 'sent', label: 'sent'},
        {id: 'failed', label: 'failed'},
        {id: 'lost', label: 'lost builders'}
    ];

    tabs.forEach(function(t) {
        var btn = document.createElement('button');
        btn.className = 'tab' + (t.id === currentTab ? ' on' : '');
        btn.textContent = t.label;
        btn.dataset.tab = t.id;
        tabbar.appendChild(btn);
    });

    var refresh = document.createElement('button');
    refresh.className = 'btn';
    refresh.textContent = 'refresh';
    refresh.id = 'refreshBtn';
    tabbar.appendChild(refresh);
}

function showTab(name) {
    currentTab = name;
    document.querySelectorAll('.pnl').forEach(function(el) {
        el.classList.remove('on');
    });
    document.querySelectorAll('.tab').forEach(function(el) {
        el.classList.remove('on');
        if (el.dataset.tab === name) el.classList.add('on');
    });
    $(name).classList.add('on');
}

async function loadStats() {
    var statsRes = await fetch('/api/stats');
    var hostRes = await fetch('/api/host');
    var s = await statsRes.json();
    var h = await hostRes.json();

    var uptime = '0m';
    if (h.uptime_seconds) {
        var hrs = Math.floor(h.uptime_seconds / 3600);
        var mins = Math.floor((h.uptime_seconds % 3600) / 60);
        uptime = hrs + 'h ' + mins + 'm';
    }

    $('status').innerHTML = 'daemon <b>' + (h.running ? 'ON' : 'OFF') + '</b> | ' + uptime + ' | ' + h.intros_today + ' today';

    var centralHtml = '';
    if (s.central && !s.central.error) {
        centralHtml = '<div style="margin-top:10px;padding-top:10px;border-top:1px solid #333">' +
            '<div style="color:#82aaff;font-size:0.8em;margin-bottom:8px">// central api</div>' +
            '<div class="stats">' +
            '<div class="stat"><b>' + s.central.total_humans + '</b><small>humans</small></div>' +
            '<div class="stat"><b>' + s.central.total_matches.toLocaleString() + '</b><small>matches</small></div>' +
            '<div class="stat"><b>' + s.central.lost_builders + '</b><small>lost</small></div>' +
            '<div class="stat"><b>' + s.central.intros_sent + '</b><small>sent</small></div>' +
            '<div class="stat"><b>' + s.central.active_instances + '</b><small>instances</small></div>' +
            '</div></div>';
    }

    $('stats').innerHTML =
        '<div style="color:#666;font-size:0.8em;margin-bottom:8px">// local</div>' +
        '<div class="stats">' +
        '<div class="stat"><b>' + s.total_humans + '</b><small>humans</small></div>' +
        '<div class="stat"><b>' + s.total_matches + '</b><small>matches</small></div>' +
        '<div class="stat"><b>' + h.score_90_plus + '</b><small>90+</small></div>' +
        '<div class="stat"><b>' + h.score_80_89 + '</b><small>80+</small></div>' +
        '<div class="stat"><b>' + h.matches_pending + '</b><small>queue</small></div>' +
        '<div class="stat"><b>' + s.sent_intros + '</b><small>sent</small></div>' +
        '</div>' + centralHtml;
}

async function loadHost() {
    var res = await fetch('/api/host_matches?limit=20');
    var data = await res.json();

    var html = '<h2>your matches (' + data.host + ')</h2>';
    html += '<p style="color:#666;font-size:0.8em;margin-bottom:10px">each match = 2 intros (one to you, one to them)</p>';

    if (!data.matches || !data.matches.length) {
        html += '<div class="meta">no matches yet</div>';
    }

    for (var i = 0; i < (data.matches || []).length; i++) {
        var m = data.matches[i];
        var reasons = (m.reasons || []).slice(0, 2).join(', ');

        html += '<div class="card" data-action="host-preview" data-id="' + m.id + '" data-dir="1">';
        html += '<div class="card-hdr"><span class="to">TO: you</span><span class="score">' + m.score + '</span></div>';
        html += '<div class="meta"><span class="about">ABOUT: ' + m.other_user + '</span> (' + m.other_platform + ')</div>';
        html += '<div class="meta">' + reasons + '</div>';
        html += '<div class="body" id="host-' + m.id + '-a"></div>';
        html += '</div>';

        html += '<div class="card" data-action="host-preview" data-id="' + m.id + '" data-dir="2">';
        html += '<div class="card-hdr"><span class="to">TO: ' + m.other_user + '</span><span class="score">' + m.score + '</span></div>';
        html += '<div class="meta"><span class="about">ABOUT: you</span></div>';
        html += '<div class="meta">' + (m.contact || 'no contact') + '</div>';
        html += '<div class="body" id="host-' + m.id + '-b"></div>';
        html += '</div>';
    }

    $('host').innerHTML = html;
}

async function openHostDraft(id, dir) {
    var elId = 'host-' + id + '-' + (dir === 1 ? 'a' : 'b');
    var el = $(elId);
    if (!el) return;

    if (el.style.display === 'block') return;

    el.innerHTML = 'loading...';
    el.style.display = 'block';

    var direction = (dir === 1) ? 'to_you' : 'to_them';
    var res = await fetch('/api/preview_host_draft?id=' + id + '&dir=' + direction);
    var data = await res.json();

    if (data.error) {
        el.innerHTML = '<span class="err">' + data.error + '</span><br><button class="closebtn" data-close="' + elId + '">CLOSE</button>';
    } else {
        var cached = data.cached ? ' <span class="cached">(cached)</span>' : '';
        el.innerHTML = '<b>SUBJ:</b> ' + data.subject + cached + '<br><br>' + data.draft + '<br><br><button class="closebtn" data-close="' + elId + '">CLOSE</button>';
    }
}

async function loadQueue() {
    var res = await fetch('/api/pending_matches?limit=40');
    var data = await res.json();

    var html = '<h2>outreach queue</h2>';

    if (!data.matches || !data.matches.length) {
        html += '<div class="meta">empty</div>';
    }

    for (var i = 0; i < (data.matches || []).length; i++) {
        var p = data.matches[i];
        var method = p.method || 'new';

        html += '<div class="card" data-action="queue-preview" data-id="' + p.id + '" data-idx="' + i + '">';
        html += '<div class="card-hdr"><span class="to">TO: ' + p.to_user + '</span><span class="score">' + p.score + '</span></div>';
        html += '<div class="meta"><span class="about">ABOUT: ' + p.about_user + '</span> | ';
        html += '<span class="m m-' + method + '">' + (p.method || '?') + '</span> ' + (p.contact || '') + '</div>';
        html += '<div class="body" id="queue-' + p.id + '-' + i + '"></div>';
        html += '</div>';
    }

    $('queue').innerHTML = html;
}

async function openQueueDraft(id, idx) {
    var elId = 'queue-' + id + '-' + idx;
    var el = $(elId);
    if (!el) return;

    if (el.style.display === 'block') return;

    el.innerHTML = 'loading...';
    el.style.display = 'block';

    var res = await fetch('/api/preview_draft?id=' + id);
    var data = await res.json();

    if (data.error) {
        el.innerHTML = '<span class="err">' + data.error + '</span><br><button class="closebtn" data-close="' + elId + '">CLOSE</button>';
    } else {
        var cached = data.cached ? ' <span class="cached">(cached)</span>' : '';
        el.innerHTML = '<b>TO:</b> ' + data.to + '<br><b>ABOUT:</b> ' + data.about + '<br><b>SUBJ:</b> ' + data.subject + cached + '<br><br>' + data.draft + '<br><br><button class="closebtn" data-close="' + elId + '">CLOSE</button>';
    }
}

async function loadSent() {
    var res = await fetch('/api/sent_intros');
    var data = await res.json();

    var html = '<h2>sent</h2>';

    for (var i = 0; i < (data.sent || []).length; i++) {
        var s = data.sent[i];
        html += '<div class="card">';
        html += '<div class="card-hdr">TO: ' + s.recipient_id + ' <span class="m m-' + s.method + '">' + s.method + '</span></div>';
        html += '<div class="body" style="display:block">' + (s.draft || '-') + '</div>';
        html += '<div class="meta">' + s.timestamp + '</div>';
        html += '</div>';
    }

    $('sent').innerHTML = html;
}

async function loadFailed() {
    var res = await fetch('/api/failed_intros');
    var data = await res.json();

    var html = '<h2>failed</h2>';

    for (var i = 0; i < (data.failed || []).length; i++) {
        var f = data.failed[i];
        html += '<div class="card">';
        html += '<div class="card-hdr">' + f.recipient_id + '</div>';
        html += '<div class="meta err">' + f.error + '</div>';
        html += '</div>';
    }

    $('failed').innerHTML = html;
}
async function loadLost() {
    var res = await fetch("/api/lost_builders");
    var data = await res.json();

    var html = "<h2>lost builders (" + (data.total || 0) + ")</h2>";
    html += "<p style=\"color:#c792ea;font-size:0.8em;margin-bottom:10px\">people who need to see that someone like them made it</p>";

    if (!data.matches || data.matches.length === 0) {
        html += "<div class=\"meta\">no lost builders found</div>";
    }

    for (var i = 0; i < (data.matches || []).length; i++) {
        var m = data.matches[i];
        html += "<div class=\"card\">";
        html += "<div class=\"card-hdr\"><span class=\"to\">LOST: " + m.lost_user + "</span><span class=\"score\">" + m.match_score + "</span></div>";
        html += "<div class=\"meta\">lost: " + m.lost_score + " | values: " + m.values_score + "</div>";
        html += "<div class=\"meta\" style=\"color:#0f8\">BUILDER: " + m.builder + " (" + m.builder_platform + ")</div>";
        html += "<div class=\"meta\">score: " + m.builder_score + " | repos: " + m.builder_repos + " | stars: " + m.builder_stars + "</div>";
        html += "<div class=\"meta\">shared: " + (m.shared || []).join(", ") + "</div>";
        html += "</div>";
    }

    $("lost").innerHTML = html;
}


function load() {
    loadStats();
    loadHost();
    loadQueue();
    loadSent();
    loadFailed();
    loadLost();
}

document.addEventListener('click', function(e) {
    var target = e.target;

    if (target.classList.contains('tab') && target.dataset.tab) {
        showTab(target.dataset.tab);
        return;
    }

    if (target.id === 'refreshBtn') {
        load();
        return;
    }

    if (target.dataset.close) {
        var el = $(target.dataset.close);
        if (el) el.style.display = 'none';
        return;
    }

    var card = target.closest('.card');
    if (card) {
        var action = card.dataset.action;
        if (action === 'host-preview') {
            openHostDraft(parseInt(card.dataset.id), parseInt(card.dataset.dir));
        } else if (action === 'queue-preview') {
            openQueueDraft(parseInt(card.dataset.id), parseInt(card.dataset.idx));
        }
    }
});

initTabs();
load();
setInterval(load, 60000);
</script>
</body>
</html>
"""


# draft cache - stores generated drafts so they dont regenerate
_draft_cache = {}

def get_cached_draft(match_id, match_type='match'):
    key = f"{match_type}:{match_id}"
    return _draft_cache.get(key)

def cache_draft(match_id, draft_data, match_type='match'):
    key = f"{match_type}:{match_id}"
    _draft_cache[key] = draft_data

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
        path = self.path.split('?')[0]
        if path == '/favicon.png' or path == '/favicon.ico':
            self._handle_favicon()
        elif path == '/' or path == '/dashboard':
            self._handle_dashboard()
        elif path == '/api/stats':
            self._handle_stats()
        elif path == '/api/host':
            self._handle_host()
        elif path == '/api/host_matches':
            self._handle_host_matches()
        elif path == '/api/your_matches':
            self._handle_your_matches()
        elif path == '/api/preview_match_draft':
            self._handle_preview_match_draft()
        elif path == '/api/preview_host_draft':
            self._handle_preview_host_draft()
        elif path == '/api/preview_draft':
            self._handle_preview_draft()
        elif path == '/api/pending_about_you':
            self._handle_pending_about_you()
        elif path == '/api/pending_to_you':
            self._handle_pending_to_you()
        elif path == '/api/pending_matches':
            self._handle_pending_matches()
        elif path == '/api/sent_intros':
            self._handle_sent_intros()
        elif path == '/api/failed_intros':
            self._handle_failed_intros()
        elif path == '/api/clear_cache':
            global _draft_cache
            _draft_cache = {}
            self._send_json({'status': 'cache cleared'})
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
        elif path == '/api/lost_builders':
            self._handle_lost_builders()
        else:
            self._send_json({'error': 'not found'}, 404)
    def _handle_favicon(self):
        from pathlib import Path
        fav = Path('/app/data/favicon.png')
        if fav.exists():
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.end_headers()
            self.wfile.write(fav.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_dashboard(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(DASHBOARD_HTML.encode())

    def _handle_sent_intros(self):
        from pathlib import Path
        log_path = Path("/app/data/delivery_log.json")
        sent = []
        if log_path.exists():
            with open(log_path) as f:
                log = json.load(f)
            sent = log.get("sent", [])[-20:]
            sent.reverse()
        self._send_json({"sent": sent})

    def _handle_failed_intros(self):
        from pathlib import Path
        log_path = Path("/app/data/delivery_log.json")
        failed = []
        if log_path.exists():
            with open(log_path) as f:
                log = json.load(f)
            failed = log.get("failed", [])
        self._send_json({"failed": failed})

    def _handle_host(self):
        """daemon status and match stats"""
        import sqlite3
        state = get_daemon_state()
        try:
            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM matches WHERE status='pending' AND overlap_score >= 60")
            pending = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM matches WHERE status='intro_sent'")
            sent = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM matches WHERE status='rejected'")
            rejected = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM matches")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM matches WHERE overlap_score >= 90")
            s90 = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM matches WHERE overlap_score >= 80 AND overlap_score < 90")
            s80 = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM matches WHERE overlap_score >= 70 AND overlap_score < 80")
            s70 = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM matches WHERE overlap_score >= 60 AND overlap_score < 70")
            s60 = c.fetchone()[0]
            conn.close()
        except:
            pending = sent = rejected = total = s90 = s80 = s70 = s60 = 0
        uptime = None
        if state.get('started_at'):
            try:
                start = datetime.fromisoformat(state['started_at']) if isinstance(state['started_at'], str) else state['started_at']
                uptime = int((datetime.now() - start).total_seconds())
            except: pass
        self._send_json({
            'running': state.get('running', False), 'dry_run': state.get('dry_run', False),
            'uptime_seconds': uptime, 'intros_today': state.get('intros_today', 0),
            'matches_pending': pending, 'matches_sent': sent, 'matches_rejected': rejected, 'matches_total': total,
            'score_90_plus': s90, 'score_80_89': s80, 'score_70_79': s70, 'score_60_69': s60,
        })

    def _handle_your_matches(self):
        """matches involving the host - shows both directions"""
        import sqlite3
        import json as j
        from db.users import get_priority_users
        limit = 15
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if p.startswith('limit='):
                    try: limit = int(p.split('=')[1])
                    except: pass
        try:
            db = Database()
            users = get_priority_users(db.conn)
            if not users:
                self._send_json({'matches': [], 'host': None})
                db.close()
                return
            host = users[0]
            host_name = host.get('github') or host.get('name')
            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            c.execute("""SELECT m.id, m.overlap_score, m.overlap_reasons, m.status,
                                h1.username, h1.platform, h1.contact,
                                h2.username, h2.platform, h2.contact
                         FROM matches m
                         JOIN humans h1 ON m.human_a_id = h1.id
                         JOIN humans h2 ON m.human_b_id = h2.id
                         WHERE (h1.username = ? OR h2.username = ?)
                         AND m.status = 'pending' AND m.overlap_score >= 60
                         ORDER BY m.overlap_score DESC LIMIT ?""", (host_name, host_name, limit))
            matches = []
            for row in c.fetchall():
                if row[4] == host_name:
                    other_user, other_platform = row[7], row[8]
                    other_contact = j.loads(row[9]) if row[9] else {}
                else:
                    other_user, other_platform = row[4], row[5]
                    other_contact = j.loads(row[6]) if row[6] else {}
                reasons = j.loads(row[2]) if row[2] else []
                matches.append({
                    'id': row[0], 'score': int(row[1]), 'reasons': reasons,
                    'status': row[3], 'other_user': other_user, 'other_platform': other_platform,
                    'contact': other_contact.get('email') or other_contact.get('mastodon') or ''
                })
            conn.close()
            db.close()
            self._send_json({'host': host_name, 'matches': matches})
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_preview_match_draft(self):
        """preview draft for a match - dir=to_you or to_them"""
        import sqlite3
        import json as j
        from introd.groq_draft import draft_intro_with_llm
        from db.users import get_priority_users

        match_id = None
        direction = 'to_you'
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if p.startswith('id='):
                    try: match_id = int(p.split('=')[1])
                    except: pass
                if p.startswith('dir='):
                    direction = p.split('=')[1]

        if not match_id:
            self._send_json({'error': 'need ?id=match_id'}, 400)
            return

        cache_key = f"{match_id}_{direction}"
        cached = get_cached_draft(cache_key, 'match')
        if cached:
            cached['cached'] = True
            self._send_json(cached)
            return

        try:
            db = Database()
            users = get_priority_users(db.conn)
            if not users:
                self._send_json({'error': 'no priority user'}, 404)
                db.close()
                return
            host = users[0]
            host_name = host.get('github') or host.get('name')

            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            c.execute("""SELECT h1.username, h1.platform, h1.contact, h1.extra,
                                h2.username, h2.platform, h2.contact, h2.extra,
                                m.overlap_score, m.overlap_reasons
                         FROM matches m
                         JOIN humans h1 ON m.human_a_id = h1.id
                         JOIN humans h2 ON m.human_b_id = h2.id
                         WHERE m.id = ?""", (match_id,))
            row = c.fetchone()
            conn.close()
            db.close()

            if not row:
                self._send_json({'error': 'match not found'}, 404)
                return

            human_a = {'username': row[0], 'platform': row[1],
                      'contact': j.loads(row[2]) if row[2] else {},
                      'extra': j.loads(row[3]) if row[3] else {}}
            human_b = {'username': row[4], 'platform': row[5],
                      'contact': j.loads(row[6]) if row[6] else {},
                      'extra': j.loads(row[7]) if row[7] else {}}
            reasons = j.loads(row[9]) if row[9] else []

            if human_a['username'] == host_name:
                host_human, other_human = human_a, human_b
            else:
                host_human, other_human = human_b, human_a

            if direction == 'to_you':
                match_data = {'human_a': host_human, 'human_b': other_human,
                             'overlap_score': row[8], 'overlap_reasons': reasons}
                recipient_name = host_name
                about_name = other_human['username']
            else:
                match_data = {'human_a': other_human, 'human_b': host_human,
                             'overlap_score': row[8], 'overlap_reasons': reasons}
                recipient_name = other_human['username']
                about_name = host_name

            result, error = draft_intro_with_llm(match_data, recipient='a', dry_run=True)
            if error:
                self._send_json({'error': error}, 500)
                return

            response = {
                'match_id': match_id,
                'direction': direction,
                'to': recipient_name,
                'about': about_name,
                'subject': result.get('subject'),
                'draft': result.get('draft_html'),
                'score': row[8],
                'cached': False,
            }
            cache_draft(cache_key, response, 'match')
            self._send_json(response)
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_host_matches(self):
        """matches for priority user"""
        import sqlite3
        import json as j
        from db.users import get_priority_users
        limit = 20
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if p.startswith('limit='):
                    try: limit = int(p.split('=')[1])
                    except: pass
        try:
            db = Database()
            users = get_priority_users(db.conn)
            if not users:
                self._send_json({'matches': [], 'host': None})
                db.close()
                return
            host = users[0]
            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            c.execute("""SELECT pm.id, pm.overlap_score, pm.overlap_reasons, pm.status, h.username, h.platform, h.contact
                         FROM priority_matches pm JOIN humans h ON pm.matched_human_id = h.id
                         WHERE pm.priority_user_id = ? ORDER BY pm.overlap_score DESC LIMIT ?""", (host['id'], limit))
            matches = []
            for row in c.fetchall():
                reasons = j.loads(row[2]) if row[2] else []
                contact = j.loads(row[6]) if row[6] else {}
                matches.append({'id': row[0], 'score': int(row[1]), 'reasons': reasons, 'status': row[3],
                               'other_user': row[4], 'other_platform': row[5],
                               'contact': contact.get('email') or contact.get('mastodon') or contact.get('github') or ''})
            conn.close()
            db.close()
            self._send_json({'host': host.get('github') or host.get('name'), 'matches': matches})
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_preview_host_draft(self):
        """preview draft for a priority match - dir=to_you or to_them"""
        import sqlite3
        import json as j
        from introd.groq_draft import draft_intro_with_llm
        from db.users import get_priority_users

        match_id = None
        direction = 'to_you'
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if p.startswith('id='):
                    try: match_id = int(p.split('=')[1])
                    except: pass
                if p.startswith('dir='):
                    direction = p.split('=')[1]

        if not match_id:
            self._send_json({'error': 'need ?id=match_id'}, 400)
            return

        cache_key = f"host_{match_id}_{direction}"
        cached = get_cached_draft(cache_key, 'host')
        if cached:
            cached['cached'] = True
            self._send_json(cached)
            return

        try:
            db = Database()
            users = get_priority_users(db.conn)
            if not users:
                self._send_json({'error': 'no priority user'}, 404)
                db.close()
                return
            host = users[0]

            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            # Get the matched human from priority_matches
            c.execute("""SELECT h.username, h.platform, h.contact, h.extra, pm.overlap_score, pm.overlap_reasons, h.bio
                         FROM priority_matches pm
                         JOIN humans h ON pm.matched_human_id = h.id
                         WHERE pm.id = ?""", (match_id,))
            row = c.fetchone()
            conn.close()
            db.close()

            if not row:
                self._send_json({'error': 'match not found'}, 404)
                return

            # The matched person (who we found for the host)
            other = {'username': row[0], 'platform': row[1], 'bio': row[6],
                    'contact': j.loads(row[2]) if row[2] else {},
                    'extra': j.loads(row[3]) if row[3] else {}}
            
            # Build host as human_a (recipient), other as human_b (subject)
            host_human = {'username': host.get('github') or host.get('name'),
                         'platform': 'priority',
                         'contact': {'email': host.get('email'), 'mastodon': host.get('mastodon'), 'github': host.get('github')},
                         'extra': {'bio': host.get('bio'), 'interests': host.get('interests')}}
            
            reasons = j.loads(row[5]) if row[5] else []
            match_data = {'human_a': host_human, 'human_b': other,
                         'overlap_score': row[4], 'overlap_reasons': reasons}

            # direction determines who gets the intro
            if direction == 'to_you':
                # intro TO host ABOUT other
                match_data = {'human_a': host_human, 'human_b': other,
                             'overlap_score': row[4], 'overlap_reasons': reasons}
                to_name = host.get('github') or host.get('name')
                about_name = other['username']
            else:
                # intro TO other ABOUT host
                match_data = {'human_a': other, 'human_b': host_human,
                             'overlap_score': row[4], 'overlap_reasons': reasons}
                to_name = other['username']
                about_name = host.get('github') or host.get('name')

            result, error = draft_intro_with_llm(match_data, recipient='a', dry_run=True)
            if error:
                self._send_json({'error': error}, 500)
                return

            cache_key = f"host_{match_id}_{direction}"
            response = {
                'match_id': match_id,
                'direction': direction,
                'to': to_name,
                'about': about_name,
                'subject': result.get('subject'),
                'draft': result.get('draft_html'),
                'score': row[4],
                'cached': False,
            }
            cache_draft(cache_key, response, 'host')
            self._send_json(response)
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_preview_draft(self):
        import sqlite3
        import json as j
        from introd.groq_draft import draft_intro_with_llm

        match_id = None
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if p.startswith('id='):
                    try: match_id = int(p.split('=')[1])
                    except: pass

        if not match_id:
            self._send_json({'error': 'need ?id=match_id'}, 400)
            return

        # check cache first
        cached = get_cached_draft(match_id, 'queue')
        if cached:
            cached['cached'] = True
            self._send_json(cached)
            return

        try:
            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            c.execute("""SELECT h1.username, h1.platform, h1.contact, h1.extra,
                                h2.username, h2.platform, h2.contact, h2.extra,
                                m.overlap_score, m.overlap_reasons
                         FROM matches m
                         JOIN humans h1 ON m.human_a_id = h1.id
                         JOIN humans h2 ON m.human_b_id = h2.id
                         WHERE m.id = ?""", (match_id,))
            row = c.fetchone()
            conn.close()

            if not row:
                self._send_json({'error': 'match not found'}, 404)
                return

            human_a = {'username': row[0], 'platform': row[1],
                      'contact': j.loads(row[2]) if row[2] else {},
                      'extra': j.loads(row[3]) if row[3] else {}}
            human_b = {'username': row[4], 'platform': row[5],
                      'contact': j.loads(row[6]) if row[6] else {},
                      'extra': j.loads(row[7]) if row[7] else {}}
            reasons = j.loads(row[9]) if row[9] else []

            match_data = {'human_a': human_a, 'human_b': human_b,
                         'overlap_score': row[8], 'overlap_reasons': reasons}

            result, error = draft_intro_with_llm(match_data, recipient='a', dry_run=True)
            if error:
                self._send_json({'error': error}, 500)
                return

            response = {
                'match_id': match_id,
                'to': human_a['username'],
                'about': human_b['username'],
                'subject': result.get('subject'),
                'draft': result.get('draft_html'),
                'score': row[8],
                'cached': False,
            }
            cache_draft(match_id, response, 'queue')
            self._send_json(response)
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_pending_about_you(self):
        """pending intros where host is human_b (being introduced to others)"""
        import sqlite3
        import json as j
        from db.users import get_priority_users
        limit = 10
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if p.startswith('limit='):
                    try: limit = int(p.split('=')[1])
                    except: pass
        try:
            db = Database()
            users = get_priority_users(db.conn)
            if not users:
                self._send_json({'matches': []})
                db.close()
                return
            host = users[0]
            host_name = host.get('github') or host.get('name')
            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            c.execute("""SELECT m.id, h1.username, h1.platform, h1.contact,
                                m.overlap_score, m.overlap_reasons
                         FROM matches m
                         JOIN humans h1 ON m.human_a_id = h1.id
                         JOIN humans h2 ON m.human_b_id = h2.id
                         WHERE h2.username = ? AND m.status = 'pending' AND m.overlap_score >= 60
                         ORDER BY m.overlap_score DESC LIMIT ?""", (host_name, limit))
            matches = []
            for row in c.fetchall():
                contact = j.loads(row[3]) if row[3] else {}
                reasons = j.loads(row[5]) if row[5] else []
                method = 'email' if contact.get('email') else ('mastodon' if contact.get('mastodon') else None)
                matches.append({'id': row[0], 'to_user': row[1], 'to_platform': row[2],
                               'score': int(row[4]), 'reasons': reasons[:3], 'method': method,
                               'contact': contact.get('email') or contact.get('mastodon') or ''})
            conn.close()
            db.close()
            self._send_json({'matches': matches})
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_pending_to_you(self):
        """pending intros where host is human_a (receiving intro about others)"""
        import sqlite3
        import json as j
        from db.users import get_priority_users
        limit = 20
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if p.startswith('limit='):
                    try: limit = int(p.split('=')[1])
                    except: pass
        try:
            db = Database()
            users = get_priority_users(db.conn)
            if not users:
                self._send_json({'matches': []})
                db.close()
                return
            host = users[0]
            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            c.execute("""SELECT pm.id, h.username, h.platform, pm.overlap_score, pm.overlap_reasons
                         FROM priority_matches pm
                         JOIN humans h ON pm.matched_human_id = h.id
                         WHERE pm.priority_user_id = ? AND pm.status IN ('new', 'pending')
                         ORDER BY pm.overlap_score DESC LIMIT ?""", (host['id'], limit))
            matches = []
            for row in c.fetchall():
                reasons = j.loads(row[4]) if row[4] else []
                matches.append({'id': row[0], 'about_user': row[1], 'about_platform': row[2],
                               'score': int(row[3]), 'reasons': reasons[:3]})
            conn.close()
            db.close()
            self._send_json({'matches': matches})
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_pending_matches(self):
        """pending matches - returns BOTH directions for each match"""
        import sqlite3
        import json as j
        limit = 30
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if p.startswith('limit='):
                    try: limit = int(p.split('=')[1])
                    except: pass
        try:
            conn = sqlite3.connect('/data/db/connectd.db')
            c = conn.cursor()
            c.execute("""SELECT m.id, h1.username, h1.platform, h1.contact,
                                h2.username, h2.platform, h2.contact, m.overlap_score, m.overlap_reasons
                         FROM matches m
                         JOIN humans h1 ON m.human_a_id = h1.id
                         JOIN humans h2 ON m.human_b_id = h2.id
                         WHERE m.status = 'pending' AND m.overlap_score >= 60
                         ORDER BY m.overlap_score DESC LIMIT ?""", (limit // 2,))
            matches = []
            for row in c.fetchall():
                contact_a = j.loads(row[3]) if row[3] else {}
                contact_b = j.loads(row[6]) if row[6] else {}
                reasons = j.loads(row[8]) if row[8] else []
                # direction 1: TO human_a ABOUT human_b
                method_a = 'email' if contact_a.get('email') else ('mastodon' if contact_a.get('mastodon') else None)
                matches.append({'id': row[0], 'to_user': row[1], 'about_user': row[4],
                               'score': int(row[7]), 'reasons': reasons[:3], 'method': method_a,
                               'contact': contact_a.get('email') or contact_a.get('mastodon') or ''})
                # direction 2: TO human_b ABOUT human_a
                method_b = 'email' if contact_b.get('email') else ('mastodon' if contact_b.get('mastodon') else None)
                matches.append({'id': row[0], 'to_user': row[4], 'about_user': row[1],
                               'score': int(row[7]), 'reasons': reasons[:3], 'method': method_b,
                               'contact': contact_b.get('email') or contact_b.get('mastodon') or ''})
            conn.close()
            self._send_json({'matches': matches})
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _handle_stats(self):
        """return database statistics (local + central)"""
        try:
            db = Database()
            stats = db.stats()
            db.close()
            
            # add central API stats if configured
            if CENTRAL_API and CENTRAL_KEY:
                try:
                    headers = {'X-API-Key': CENTRAL_KEY}
                    resp = requests.get(f'{CENTRAL_API}/stats', headers=headers, timeout=5)
                    if resp.status_code == 200:
                        central = resp.json()
                        stats['central'] = {
                            'total_humans': central.get('total_humans', 0),
                            'lost_builders': central.get('lost_builders', 0),
                            'builders': central.get('builders', 0),
                            'total_matches': central.get('total_matches', 0),
                            'intros_sent': central.get('intros_sent', 0),
                            'active_instances': central.get('active_instances', 0),
                        }
                except Exception as ce:
                    stats['central'] = {'error': str(ce)}
            
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



    def _handle_lost_builders(self):
        """return lost builders with their inspiring matches"""
        try:
            from matchd.lost import find_matches_for_lost_builders
            db = Database()
            matches, error = find_matches_for_lost_builders(db, min_lost_score=30, min_values_score=15, limit=50)
            
            result = {
                'total': len(matches) if matches else 0,
                'error': error,
                'matches': []
            }
            
            if matches:
                for m in matches:
                    lost = m.get('lost_user', {})
                    builder = m.get('inspiring_builder', {})
                    result['matches'].append({
                        'lost_user': lost.get('username'),
                        'lost_platform': lost.get('platform'),
                        'lost_score': lost.get('lost_potential_score', 0),
                        'values_score': lost.get('score', 0),
                        'builder': builder.get('username'),
                        'builder_platform': builder.get('platform'),
                        'builder_score': builder.get('score', 0),
                        'builder_repos': m.get('builder_repos', 0),
                        'builder_stars': m.get('builder_stars', 0),
                        'match_score': m.get('match_score', 0),
                        'shared': m.get('shared_interests', [])[:5],
                    })
            
            db.close()
            self._send_json(result)
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
