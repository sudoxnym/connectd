"""
introd/send.py - actually deliver intros via appropriate channel
"""

import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

# email config (from env)
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', '')


def send_email(to_email, subject, body):
    """send email via SMTP"""
    msg = MIMEMultipart()
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)


def send_github_issue(repo_url, title, body):
    """
    create a github issue (requires GITHUB_TOKEN)
    note: only works if you have write access to the repo
    typically won't work for random users - fallback to manual
    """
    # extract owner/repo from url
    # https://github.com/owner/repo -> owner/repo
    parts = repo_url.rstrip('/').split('/')
    if len(parts) < 2:
        return False, "invalid github url"

    owner = parts[-2]
    repo = parts[-1]

    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        return False, "no github token"

    # would create issue via API - but this is invasive
    # better to just output the info for manual action
    return False, "github issues not automated - use manual outreach"


def send_mastodon_dm(instance, username, message):
    """
    send mastodon DM (requires account credentials)
    not implemented - requires oauth setup
    """
    return False, "mastodon DMs not automated - use manual outreach"


def send_reddit_message(username, subject, body):
    """
    send reddit message (requires account credentials)
    not implemented - requires oauth setup
    """
    return False, "reddit messages not automated - use manual outreach"


def send_intro(db, intro_id):
    """
    send an approved intro

    returns: (success, error_message)
    """
    # get intro from db
    c = db.conn.cursor()
    c.execute('SELECT * FROM intros WHERE id = ?', (intro_id,))
    row = c.fetchone()

    if not row:
        return False, "intro not found"

    intro = dict(row)

    if intro['status'] != 'approved':
        return False, f"intro not approved (status: {intro['status']})"

    channel = intro.get('channel')
    draft = intro.get('draft')

    # get recipient info
    recipient = db.get_human_by_id(intro['recipient_human_id'])
    if not recipient:
        return False, "recipient not found"

    success = False
    error = None

    if channel == 'email':
        # get email from contact
        import json
        contact = recipient.get('contact', {})
        if isinstance(contact, str):
            contact = json.loads(contact)

        email = contact.get('email')
        if email:
            success, error = send_email(
                email,
                "connection: aligned builder intro",
                draft
            )
        else:
            error = "no email address"

    elif channel == 'github':
        success, error = send_github_issue(
            recipient.get('url'),
            "connection: aligned builder intro",
            draft
        )

    elif channel == 'mastodon':
        success, error = send_mastodon_dm(
            recipient.get('instance'),
            recipient.get('username'),
            draft
        )

    elif channel == 'reddit':
        success, error = send_reddit_message(
            recipient.get('username'),
            "connection: aligned builder intro",
            draft
        )

    else:
        error = f"unknown channel: {channel}"

    # update status
    if success:
        db.mark_intro_sent(intro_id)
        print(f"introd: sent intro {intro_id} via {channel}")
    else:
        # mark as needs manual sending
        c.execute('''UPDATE intros SET status = 'manual_needed',
                     approved_at = ? WHERE id = ?''',
                  (datetime.now().isoformat(), intro_id))
        db.conn.commit()
        print(f"introd: intro {intro_id} needs manual send ({error})")

    return success, error


def send_all_approved(db):
    """
    send all approved intros
    """
    c = db.conn.cursor()
    c.execute('SELECT id FROM intros WHERE status = "approved"')
    rows = c.fetchall()

    if not rows:
        print("no approved intros to send")
        return

    print(f"sending {len(rows)} approved intros...")

    sent = 0
    failed = 0

    for row in rows:
        success, error = send_intro(db, row['id'])
        if success:
            sent += 1
        else:
            failed += 1

    print(f"sent: {sent}, failed/manual: {failed}")


def export_manual_intros(db, output_file='manual_intros.txt'):
    """
    export intros that need manual sending to a text file
    """
    c = db.conn.cursor()
    c.execute('''SELECT i.*, h.username, h.platform, h.url
                 FROM intros i
                 JOIN humans h ON i.recipient_human_id = h.id
                 WHERE i.status IN ('approved', 'manual_needed')''')
    rows = c.fetchall()

    if not rows:
        print("no intros to export")
        return

    with open(output_file, 'w') as f:
        for row in rows:
            f.write("=" * 60 + "\n")
            f.write(f"TO: {row['username']} ({row['platform']})\n")
            f.write(f"URL: {row['url']}\n")
            f.write(f"CHANNEL: {row['channel']}\n")
            f.write("-" * 60 + "\n")
            f.write(row['draft'] + "\n")
            f.write("\n")

    print(f"exported {len(rows)} intros to {output_file}")
