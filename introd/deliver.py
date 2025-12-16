"""
introd/deliver.py - intro delivery via multiple channels

supports:
- email (smtp)
- mastodon dm (if they allow dms)
- bluesky dm (via AT Protocol)
- matrix dm (creates DM room and sends message)
- github issue (opens intro as issue on their most active repo)
- manual queue (for review before sending)

contact method is determined by ACTIVITY-BASED SELECTION:
- picks the platform where the user is MOST ACTIVE
- verified handles (from rel="me" links) get a bonus

NOTE: reddit is NOT a delivery method - it's discovery only.
reddit-discovered users are contacted via their external links.
"""

import os
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

# config from env - no hardcoded credentials
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 465))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', '')

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
MASTODON_TOKEN = os.environ.get('MASTODON_TOKEN', '')
MASTODON_INSTANCE = os.environ.get('MASTODON_INSTANCE', '')
BLUESKY_HANDLE = os.environ.get('BLUESKY_HANDLE', '')
BLUESKY_APP_PASSWORD = os.environ.get('BLUESKY_APP_PASSWORD', '')
MATRIX_HOMESERVER = os.environ.get('MATRIX_HOMESERVER', '')
MATRIX_USER_ID = os.environ.get('MATRIX_USER_ID', '')
MATRIX_ACCESS_TOKEN = os.environ.get('MATRIX_ACCESS_TOKEN', '')

# delivery log
DELIVERY_LOG = Path(__file__).parent.parent / 'data' / 'delivery_log.json'
MANUAL_QUEUE = Path(__file__).parent.parent / 'data' / 'manual_queue.json'


def load_delivery_log():
    """load delivery history"""
    if DELIVERY_LOG.exists():
        return json.loads(DELIVERY_LOG.read_text())
    return {'sent': [], 'failed': [], 'queued': []}


def save_delivery_log(log):
    """save delivery history"""
    DELIVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    DELIVERY_LOG.write_text(json.dumps(log, indent=2))


def load_manual_queue():
    """load manual review queue"""
    if MANUAL_QUEUE.exists():
        return json.loads(MANUAL_QUEUE.read_text())
    return []


def save_manual_queue(queue):
    """save manual review queue"""
    MANUAL_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    MANUAL_QUEUE.write_text(json.dumps(queue, indent=2))


def already_contacted(recipient_id):
    """check if we've already sent an intro to this person"""
    log = load_delivery_log()
    sent_ids = [s.get('recipient_id') for s in log.get('sent', [])]
    return recipient_id in sent_ids


def send_email(to_email, subject, body, dry_run=False):
    """send email via smtp"""
    if dry_run:
        print(f"  [dry run] would email {to_email}")
        print(f"    subject: {subject}")
        print(f"    body preview: {body[:100]}...")
        return True, "dry run"

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email

        # plain text
        text_part = MIMEText(body, 'plain')
        msg.attach(text_part)

        # html version (simple)
        html_body = body.replace('\n', '<br>')
        html_part = MIMEText(f"<html><body><p>{html_body}</p></body></html>", 'html')
        msg.attach(html_part)

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_email, msg.as_string())

        return True, None
    except Exception as e:
        return False, str(e)


def create_github_issue(owner, repo, title, body, dry_run=False):
    """create github issue as intro"""
    if not GITHUB_TOKEN:
        return False, "GITHUB_TOKEN not set"

    if dry_run:
        print(f"  [dry run] would create issue on {owner}/{repo}")
        print(f"    title: {title}")
        return True, "dry run"

    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        resp = requests.post(
            url,
            headers={
                'Authorization': f'token {GITHUB_TOKEN}',
                'Accept': 'application/vnd.github.v3+json',
            },
            json={
                'title': title,
                'body': body,
                'labels': ['introduction', 'community'],
            },
            timeout=30,
        )

        if resp.status_code == 201:
            issue_url = resp.json().get('html_url')
            return True, issue_url
        else:
            return False, f"github api error: {resp.status_code} - {resp.text}"
    except Exception as e:
        return False, str(e)


def send_mastodon_dm(recipient_acct, message, dry_run=False):
    """send mastodon direct message"""
    if not MASTODON_TOKEN:
        return False, "MASTODON_TOKEN not set"

    if dry_run:
        print(f"  [dry run] would DM {recipient_acct}")
        print(f"    message preview: {message[:100]}...")
        return True, "dry run"

    try:
        # post as direct message (visibility: direct, mention recipient)
        url = f"https://{MASTODON_INSTANCE}/api/v1/statuses"
        resp = requests.post(
            url,
            headers={
                'Authorization': f'Bearer {MASTODON_TOKEN}',
                'Content-Type': 'application/json',
            },
            json={
                'status': f"@{recipient_acct} {message}",
                'visibility': 'direct',
            },
            timeout=30,
        )

        if resp.status_code in [200, 201]:
            return True, resp.json().get('url')
        else:
            return False, f"mastodon api error: {resp.status_code} - {resp.text}"
    except Exception as e:
        return False, str(e)


def send_bluesky_dm(recipient_handle, message, dry_run=False):
    """send bluesky direct message via AT Protocol"""
    if not BLUESKY_APP_PASSWORD:
        return False, "BLUESKY_APP_PASSWORD not set"

    if dry_run:
        print(f"  [dry run] would DM {recipient_handle} on bluesky")
        print(f"    message preview: {message[:100]}...")
        return True, "dry run"

    try:
        # authenticate with bluesky
        auth_url = "https://bsky.social/xrpc/com.atproto.server.createSession"
        auth_resp = requests.post(
            auth_url,
            json={
                'identifier': BLUESKY_HANDLE,
                'password': BLUESKY_APP_PASSWORD,
            },
            timeout=30,
        )

        if auth_resp.status_code != 200:
            return False, f"bluesky auth failed: {auth_resp.status_code}"

        auth_data = auth_resp.json()
        access_token = auth_data.get('accessJwt')
        did = auth_data.get('did')

        # resolve recipient DID
        resolve_url = f"https://bsky.social/xrpc/com.atproto.identity.resolveHandle"
        resolve_resp = requests.get(
            resolve_url,
            params={'handle': recipient_handle.lstrip('@')},
            timeout=30,
        )

        if resolve_resp.status_code != 200:
            return False, f"couldn't resolve handle {recipient_handle}"

        recipient_did = resolve_resp.json().get('did')

        # create chat/DM (using convo namespace)
        # first get or create conversation
        convo_url = "https://bsky.social/xrpc/chat.bsky.convo.getConvoForMembers"
        convo_resp = requests.get(
            convo_url,
            headers={'Authorization': f'Bearer {access_token}'},
            params={'members': [recipient_did]},
            timeout=30,
        )

        if convo_resp.status_code != 200:
            # try creating conversation
            return False, f"couldn't get/create conversation: {convo_resp.status_code}"

        convo_id = convo_resp.json().get('convo', {}).get('id')

        # send message
        msg_url = "https://bsky.social/xrpc/chat.bsky.convo.sendMessage"
        msg_resp = requests.post(
            msg_url,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
            json={
                'convoId': convo_id,
                'message': {'text': message},
            },
            timeout=30,
        )

        if msg_resp.status_code in [200, 201]:
            return True, f"sent to {recipient_handle}"
        else:
            return False, f"bluesky dm failed: {msg_resp.status_code} - {msg_resp.text}"

    except Exception as e:
        return False, str(e)


def send_matrix_dm(recipient_mxid, message, dry_run=False):
    """send matrix direct message"""
    if not MATRIX_ACCESS_TOKEN:
        return False, "MATRIX_ACCESS_TOKEN not set"

    if dry_run:
        print(f"  [dry run] would DM {recipient_mxid} on matrix")
        print(f"    message preview: {message[:100]}...")
        return True, "dry run"

    try:
        # create or get direct room with recipient
        # first, check if we already have a DM room
        headers = {'Authorization': f'Bearer {MATRIX_ACCESS_TOKEN}'}

        # create a new DM room
        create_room_resp = requests.post(
            f'{MATRIX_HOMESERVER}/_matrix/client/v3/createRoom',
            headers=headers,
            json={
                'is_direct': True,
                'invite': [recipient_mxid],
                'preset': 'trusted_private_chat',
            },
            timeout=30,
        )

        if create_room_resp.status_code not in [200, 201]:
            return False, f"matrix room creation failed: {create_room_resp.status_code} - {create_room_resp.text}"

        room_id = create_room_resp.json().get('room_id')

        # send message to room
        import time
        txn_id = str(int(time.time() * 1000))

        msg_resp = requests.put(
            f'{MATRIX_HOMESERVER}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}',
            headers=headers,
            json={
                'msgtype': 'm.text',
                'body': message,
            },
            timeout=30,
        )

        if msg_resp.status_code in [200, 201]:
            return True, f"sent to {recipient_mxid} in {room_id}"
        else:
            return False, f"matrix send failed: {msg_resp.status_code} - {msg_resp.text}"

    except Exception as e:
        return False, str(e)


def add_to_manual_queue(intro_data):
    """add intro to manual review queue"""
    queue = load_manual_queue()
    queue.append({
        **intro_data,
        'queued_at': datetime.now().isoformat(),
        'status': 'pending',
    })
    save_manual_queue(queue)
    return True


def determine_best_contact(human):
    """
    determine best contact method based on WHERE THEY'RE MOST ACTIVE
    
    returns: (method, info, fallbacks)
    uses activity-based selection - ranks by user's actual usage
    """
    from introd.groq_draft import determine_contact_method as activity_based_contact
    
    method, info, fallbacks = activity_based_contact(human)
    
    # convert github_issue info to dict format for delivery
    def format_info(m, i):
        if m == 'github_issue' and isinstance(i, str) and '/' in i:
            parts = i.split('/', 1)
            return {'owner': parts[0], 'repo': parts[1]}
        return i
    
    info = format_info(method, info)
    fallbacks = [(m, format_info(m, i)) for m, i in fallbacks]
    
    return method, info, fallbacks


def deliver_intro(match_data, intro_draft, dry_run=False):
    """
    deliver an intro via the best available method

    match_data: {human_a, human_b, overlap_score, overlap_reasons}
    intro_draft: the text to send (from groq)
    """
    recipient = match_data.get('human_b', {})
    recipient_id = f"{recipient.get('platform')}:{recipient.get('username')}"

    # check if already contacted
    if already_contacted(recipient_id):
        return False, "already contacted", None

    # determine contact method with fallbacks
    method, contact_info, fallbacks = determine_best_contact(recipient)

    log = load_delivery_log()
    result = {
        'recipient_id': recipient_id,
        'recipient_name': recipient.get('name') or recipient.get('username'),
        'method': method,
        'contact_info': contact_info,
        'overlap_score': match_data.get('overlap_score'),
        'timestamp': datetime.now().isoformat(),
    }

    success = False
    error = None

    if method == 'email':
        subject = f"someone you might want to know - connectd"
        success, error = send_email(contact_info, subject, intro_draft, dry_run)

    elif method == 'mastodon':
        success, error = send_mastodon_dm(contact_info, intro_draft, dry_run)

    elif method == 'bluesky':
        success, error = send_bluesky_dm(contact_info, intro_draft, dry_run)

    elif method == 'matrix':
        success, error = send_matrix_dm(contact_info, intro_draft, dry_run)

    elif method == 'discord':
        from scoutd.discord import send_discord_dm
        success, error = send_discord_dm(contact_info, intro_draft, dry_run)

    elif method == 'lemmy':
        from scoutd.lemmy import send_lemmy_dm
        success, error = send_lemmy_dm(contact_info, intro_draft, dry_run)

    elif method == 'github_issue':
        owner = contact_info.get('owner')
        repo = contact_info.get('repo')
        title = "community introduction from connectd"
        # format for github
        github_body = f"""hey {recipient.get('name') or recipient.get('username')},

{intro_draft}

---
*this is an automated introduction from [connectd](https://github.com/connectd-daemon), a daemon that finds isolated builders with aligned values and connects them. if this feels spammy, i apologize - you can close this issue and we won't reach out again.*
"""
        success, error = create_github_issue(owner, repo, title, github_body, dry_run)

    elif method == 'manual':
        # add to review queue
        add_to_manual_queue({
            'match': match_data,
            'draft': intro_draft,
            'recipient': recipient,
        })
        success = True
        error = "added to manual queue"

    # if failed and we have fallbacks, try them
    if not success and fallbacks:
        for fallback_method, fallback_info in fallbacks:
            result['fallback_attempts'] = result.get('fallback_attempts', [])
            result['fallback_attempts'].append({
                'method': fallback_method,
                'contact_info': fallback_info
            })
            
            fb_success = False
            fb_error = None
            
            if fallback_method == 'email':
                subject = f"someone you might want to know - connectd"
                fb_success, fb_error = send_email(fallback_info, subject, intro_draft, dry_run)
            elif fallback_method == 'mastodon':
                fb_success, fb_error = send_mastodon_dm(fallback_info, intro_draft, dry_run)
            elif fallback_method == 'bluesky':
                fb_success, fb_error = send_bluesky_dm(fallback_info, intro_draft, dry_run)
            elif fallback_method == 'matrix':
                fb_success, fb_error = send_matrix_dm(fallback_info, intro_draft, dry_run)
            elif fallback_method == 'lemmy':
                from scoutd.lemmy import send_lemmy_dm
                fb_success, fb_error = send_lemmy_dm(fallback_info, intro_draft, dry_run)
            elif fallback_method == 'discord':
                from scoutd.discord import send_discord_dm
                fb_success, fb_error = send_discord_dm(fallback_info, intro_draft, dry_run)
            elif fallback_method == 'github_issue':
                owner = fallback_info.get('owner')
                repo = fallback_info.get('repo')
                title = "community introduction from connectd"
                github_body = f"""hey {recipient.get('name') or recipient.get('username')},

{intro_draft}

---
*automated introduction from connectd*
"""
                fb_success, fb_error = create_github_issue(owner, repo, title, github_body, dry_run)
            
            if fb_success:
                success = True
                method = fallback_method
                contact_info = fallback_info
                error = None
                result['fallback_succeeded'] = fallback_method
                break
            else:
                result['fallback_attempts'][-1]['error'] = fb_error
    
    # log result
    result['success'] = success
    result['error'] = error
    result['final_method'] = method
    
    if success:
        log['sent'].append(result)
    else:
        log['failed'].append(result)
    
    save_delivery_log(log)
    
    return success, error, method


def deliver_batch(matches_with_intros, dry_run=False):
    """
    deliver intros for a batch of matches

    matches_with_intros: list of {match_data, intro_draft}
    """
    results = []

    for item in matches_with_intros:
        match_data = item.get('match_data') or item.get('match')
        intro_draft = item.get('intro_draft') or item.get('draft')

        if not match_data or not intro_draft:
            continue

        success, error, method = deliver_intro(match_data, intro_draft, dry_run)
        results.append({
            'recipient': match_data.get('human_b', {}).get('username'),
            'method': method,
            'success': success,
            'error': error,
        })

        print(f"  {match_data.get('human_b', {}).get('username')}: {method} - {'ok' if success else error}")

    return results


def get_delivery_stats():
    """get delivery statistics"""
    log = load_delivery_log()
    queue = load_manual_queue()

    return {
        'sent': len(log.get('sent', [])),
        'failed': len(log.get('failed', [])),
        'queued': len(log.get('queued', [])),
        'manual_pending': len([q for q in queue if q.get('status') == 'pending']),
        'by_method': {
            'email': len([s for s in log.get('sent', []) if s.get('method') == 'email']),
            'mastodon': len([s for s in log.get('sent', []) if s.get('method') == 'mastodon']),
            'github_issue': len([s for s in log.get('sent', []) if s.get('method') == 'github_issue']),
            'manual': len([s for s in log.get('sent', []) if s.get('method') == 'manual']),
        },
    }


def review_manual_queue():
    """review and process manual queue"""
    queue = load_manual_queue()
    pending = [q for q in queue if q.get('status') == 'pending']

    if not pending:
        print("no items in manual queue")
        return

    print(f"\n{len(pending)} items pending review:\n")

    for i, item in enumerate(pending, 1):
        recipient = item.get('recipient', {})
        match = item.get('match', {})

        print(f"[{i}] {recipient.get('name') or recipient.get('username')}")
        print(f"    platform: {recipient.get('platform')}")
        print(f"    url: {recipient.get('url')}")
        print(f"    overlap: {match.get('overlap_score')}")
        print(f"    draft preview: {item.get('draft', '')[:80]}...")
        print()

    return pending
