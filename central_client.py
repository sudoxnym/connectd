"""
connectd/central_client.py - client for connectd-central API

provides similar interface to local Database class but uses remote API.
allows distributed instances to share data and coordinate outreach.
"""

import os
import json
import requests
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

CENTRAL_API = os.environ.get('CONNECTD_CENTRAL_API', '')
API_KEY = os.environ.get('CONNECTD_API_KEY', '')
INSTANCE_ID = os.environ.get('CONNECTD_INSTANCE_ID', 'default')


class CentralClient:
    """client for connectd-central API"""
    
    def __init__(self, api_url: str = None, api_key: str = None, instance_id: str = None):
        self.api_url = api_url or CENTRAL_API
        self.api_key = api_key or API_KEY
        self.instance_id = instance_id or INSTANCE_ID
        self.headers = {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        
        if not self.api_key:
            raise ValueError('CONNECTD_API_KEY environment variable required')
    
    def _get(self, endpoint: str, params: dict = None) -> dict:
        resp = requests.get(f'{self.api_url}{endpoint}', headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()
    
    def _post(self, endpoint: str, data: dict) -> dict:
        resp = requests.post(f'{self.api_url}{endpoint}', headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()
    
    # === HUMANS ===
    
    def get_human(self, human_id: int) -> Optional[dict]:
        try:
            return self._get(f'/humans/{human_id}')
        except:
            return None
    
    def get_humans(self, platform: str = None, user_type: str = None, 
                   min_score: float = 0, limit: int = 100, offset: int = 0) -> List[dict]:
        params = {'min_score': min_score, 'limit': limit, 'offset': offset}
        if platform:
            params['platform'] = platform
        if user_type:
            params['user_type'] = user_type
        result = self._get('/humans', params)
        return result.get('humans', [])
    
    def get_all_humans(self, min_score: float = 0, limit: int = 100000) -> List[dict]:
        """get all humans (for matching)"""
        return self.get_humans(min_score=min_score, limit=limit)
    
    def get_lost_builders(self, min_score: float = 30, limit: int = 100) -> List[dict]:
        """get lost builders for outreach"""
        return self.get_humans(user_type='lost', min_score=min_score, limit=limit)
    
    def get_builders(self, min_score: float = 50, limit: int = 100) -> List[dict]:
        """get active builders"""
        return self.get_humans(user_type='builder', min_score=min_score, limit=limit)
    
    def upsert_human(self, human: dict) -> int:
        """create or update human, returns id"""
        result = self._post('/humans', human)
        return result.get('id')
    
    def upsert_humans_bulk(self, humans: List[dict]) -> Tuple[int, int]:
        """bulk upsert humans, returns (created, updated)"""
        result = self._post('/humans/bulk', humans)
        return result.get('created', 0), result.get('updated', 0)
    
    # === MATCHES ===
    
    def get_matches(self, min_score: float = 0, limit: int = 100, offset: int = 0) -> List[dict]:
        params = {'min_score': min_score, 'limit': limit, 'offset': offset}
        result = self._get('/matches', params)
        return result.get('matches', [])
    
    def create_match(self, human_a_id: int, human_b_id: int, 
                     overlap_score: float, overlap_reasons: str = None) -> int:
        """create match, returns id"""
        result = self._post('/matches', {
            'human_a_id': human_a_id,
            'human_b_id': human_b_id,
            'overlap_score': overlap_score,
            'overlap_reasons': overlap_reasons
        })
        return result.get('id')
    
    def create_matches_bulk(self, matches: List[dict]) -> int:
        """bulk create matches, returns count"""
        result = self._post('/matches/bulk', matches)
        return result.get('created', 0)
    
    # === OUTREACH COORDINATION ===
    
    def get_pending_outreach(self, outreach_type: str = None, limit: int = 50) -> List[dict]:
        """get pending outreach that hasn't been claimed"""
        params = {'limit': limit}
        if outreach_type:
            params['outreach_type'] = outreach_type
        result = self._get('/outreach/pending', params)
        return result.get('pending', [])
    
    def claim_outreach(self, human_id: int, match_id: int = None, 
                       outreach_type: str = 'intro') -> Optional[int]:
        """claim outreach for a human, returns outreach_id or None if already claimed"""
        try:
            result = self._post('/outreach/claim', {
                'human_id': human_id,
                'match_id': match_id,
                'outreach_type': outreach_type
            })
            return result.get('outreach_id')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 409:
                return None  # already claimed by another instance
            raise
    
    def complete_outreach(self, outreach_id: int, status: str,
                          sent_via: str = None, draft: str = None, error: str = None):
        """mark outreach as complete"""
        self._post('/outreach/complete', {
            'outreach_id': outreach_id,
            'status': status,
            'sent_via': sent_via,
            'draft': draft,
            'error': error
        })
    
    def get_outreach_history(self, status: str = None, limit: int = 100) -> List[dict]:
        params = {'limit': limit}
        if status:
            params['status'] = status
        result = self._get('/outreach/history', params)
        return result.get('history', [])
    
    def already_contacted(self, human_id: int) -> bool:
        """check if human has been contacted"""
        history = self._get('/outreach/history', {'limit': 10000})
        sent = history.get('history', [])
        return any(h['human_id'] == human_id and h['status'] == 'sent' for h in sent)
    
    # === STATS ===
    
    def get_stats(self) -> dict:
        return self._get('/stats')
    
    # === INSTANCE MANAGEMENT ===
    
    def register_instance(self, name: str, host: str):
        """register this instance with central"""
        self._post(f'/instances/register?name={name}&host={host}', {})
    
    def get_instances(self) -> List[dict]:
        result = self._get('/instances')
        return result.get('instances', [])
    
    # === HEALTH ===
    
    def health_check(self) -> bool:
        try:
            result = self._get('/health')
            return result.get('status') == 'ok'
        except:
            return False


# convenience function
    
    # === TOKENS ===
    
    def get_token(self, user_id: int, match_id: int = None) -> str:
        """get or create a token for a user"""
        params = {}
        if match_id:
            params['match_id'] = match_id
        result = self._get(f'/api/token/{user_id}', params)
        return result.get('token')
    
    def get_interested_count(self, user_id: int) -> int:
        """get count of people interested in this user"""
        try:
            result = self._get(f'/api/interested_count/{user_id}')
            return result.get('count', 0)
        except:
            return 0


# convenience function
def get_client() -> CentralClient:
    return CentralClient()
