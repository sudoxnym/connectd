"""
introd - outreach module
drafts intros, queues for human review, sends via appropriate channel
"""

from .draft import draft_intro
from .review import get_pending_intros, approve_intro, reject_intro
from .send import send_intro

__all__ = ['draft_intro', 'get_pending_intros', 'approve_intro', 'reject_intro', 'send_intro']
