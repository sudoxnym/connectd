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
