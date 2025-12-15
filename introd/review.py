"""
introd/review.py - human approval queue before sending
"""

import json
from datetime import datetime


def get_pending_intros(db, limit=50):
    """
    get all intros pending human review

    returns list of intro dicts with full context
    """
    rows = db.get_pending_intros(limit=limit)

    intros = []
    for row in rows:
        # get associated match and humans
        match_id = row.get('match_id')
        recipient_id = row.get('recipient_human_id')

        recipient = db.get_human_by_id(recipient_id) if recipient_id else None

        intros.append({
            'id': row['id'],
            'match_id': match_id,
            'recipient': recipient,
            'channel': row.get('channel'),
            'draft': row.get('draft'),
            'status': row.get('status'),
        })

    return intros


def approve_intro(db, intro_id, approved_by='human'):
    """
    approve an intro for sending

    intro_id: database id of the intro
    approved_by: who approved it (for audit trail)
    """
    db.approve_intro(intro_id, approved_by)
    print(f"introd: approved intro {intro_id} by {approved_by}")


def reject_intro(db, intro_id, reason=None):
    """
    reject an intro (won't be sent)
    """
    c = db.conn.cursor()
    c.execute('''UPDATE intros SET status = 'rejected',
                 approved_at = ?, approved_by = ? WHERE id = ?''',
              (datetime.now().isoformat(), f"rejected: {reason}" if reason else "rejected", intro_id))
    db.conn.commit()
    print(f"introd: rejected intro {intro_id}")


def review_intro_interactive(db, intro):
    """
    interactive review of a single intro

    returns: 'approve', 'reject', 'edit', or 'skip'
    """
    print("\n" + "=" * 60)
    print("INTRO FOR REVIEW")
    print("=" * 60)

    recipient = intro.get('recipient', {})
    print(f"\nRecipient: {recipient.get('name') or recipient.get('username')}")
    print(f"Platform: {recipient.get('platform')}")
    print(f"Channel: {intro.get('channel')}")
    print(f"\n--- DRAFT ---")
    print(intro.get('draft'))
    print("--- END ---\n")

    while True:
        choice = input("[a]pprove / [r]eject / [s]kip / [e]dit? ").strip().lower()

        if choice in ['a', 'approve']:
            approve_intro(db, intro['id'])
            return 'approve'
        elif choice in ['r', 'reject']:
            reason = input("reason (optional): ").strip()
            reject_intro(db, intro['id'], reason)
            return 'reject'
        elif choice in ['s', 'skip']:
            return 'skip'
        elif choice in ['e', 'edit']:
            print("editing not yet implemented - approve or reject")
        else:
            print("invalid choice")


def review_all_pending(db):
    """
    interactive review of all pending intros
    """
    intros = get_pending_intros(db)

    if not intros:
        print("no pending intros to review")
        return

    print(f"\n{len(intros)} intros pending review\n")

    approved = 0
    rejected = 0
    skipped = 0

    for intro in intros:
        result = review_intro_interactive(db, intro)

        if result == 'approve':
            approved += 1
        elif result == 'reject':
            rejected += 1
        else:
            skipped += 1

        cont = input("\ncontinue reviewing? [y/n] ").strip().lower()
        if cont != 'y':
            break

    print(f"\nreview complete: {approved} approved, {rejected} rejected, {skipped} skipped")
