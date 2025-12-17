"""
introd/draft.py - AI writes intro messages referencing both parties' work
now with interest system links
"""

import json

# base URL for connectd profiles
CONNECTD_URL = "https://connectd.sudoxreboot.com"

# intro template - now with interest links
INTRO_TEMPLATE = """hi {recipient_name},

i'm an AI that connects isolated builders working on similar things.

you're building: {recipient_summary}

{other_name} is building: {other_summary}

overlap: {overlap_summary}

thought you might benefit from knowing each other.

their profile: {profile_url}
{interested_line}

no pitch. just connection. ignore if not useful.

- connectd
"""

# shorter version for platforms with character limits
SHORT_TEMPLATE = """hi {recipient_name} - i'm an AI connecting aligned builders.

you: {recipient_summary}
{other_name}: {other_summary}

overlap: {overlap_summary}

their profile: {profile_url}

no pitch, just connection.
"""


def summarize_human(human_data):
    """generate a brief summary of what someone is building/interested in"""
    parts = []

    # name or username
    name = human_data.get('name') or human_data.get('username', 'unknown')

    # platform context
    platform = human_data.get('platform', '')

    # signals/interests
    signals = human_data.get('signals', [])
    if isinstance(signals, str):
        try:
            signals = json.loads(signals)
        except:
            signals = []

    # extra data
    extra = human_data.get('extra', {})
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except:
            extra = {}

    # build summary based on available data
    topics = extra.get('topics', [])
    languages = list(extra.get('languages', {}).keys())[:3]
    repo_count = extra.get('repo_count', 0)
    subreddits = extra.get('subreddits', [])

    if platform == 'github':
        if topics:
            parts.append(f"working on {', '.join(topics[:3])}")
        if languages:
            parts.append(f"using {', '.join(languages)}")
        if repo_count > 10:
            parts.append(f"({repo_count} repos)")

    elif platform == 'reddit':
        if subreddits:
            parts.append(f"active in r/{', r/'.join(subreddits[:3])}")

    elif platform == 'mastodon':
        instance = extra.get('instance', '')
        if instance:
            parts.append(f"on {instance}")

    elif platform == 'lobsters':
        karma = extra.get('karma', 0)
        if karma > 50:
            parts.append(f"active on lobste.rs ({karma} karma)")

    # add key signals
    key_signals = [s for s in signals if s in ['selfhosted', 'privacy', 'cooperative',
                                                 'solarpunk', 'intentional_community',
                                                 'home_automation', 'foss']]
    if key_signals:
        parts.append(f"interested in {', '.join(key_signals[:3])}")

    if not parts:
        parts.append(f"builder on {platform}")

    return ' | '.join(parts)


def summarize_overlap(overlap_data):
    """generate overlap summary"""
    reasons = overlap_data.get('overlap_reasons', [])
    if isinstance(reasons, str):
        try:
            reasons = json.loads(reasons)
        except:
            reasons = []

    if reasons:
        return ' | '.join(reasons[:3])

    # fallback
    shared = overlap_data.get('shared_signals', [])
    if shared:
        return f"shared interests: {', '.join(shared[:3])}"

    return "aligned values and interests"


def draft_intro(match_data, recipient='a', recipient_token=None, interested_count=0):
    """
    draft an intro message for a match

    match_data: dict with human_a, human_b, overlap info
    recipient: 'a' or 'b' - who receives this intro
    recipient_token: token for the recipient (to track who clicked)
    interested_count: how many people are already interested in the recipient

    returns: dict with draft text, channel, metadata
    """
    if recipient == 'a':
        recipient_human = match_data['human_a']
        other_human = match_data['human_b']
    else:
        recipient_human = match_data['human_b']
        other_human = match_data['human_a']

    # get names
    recipient_name = recipient_human.get('name') or recipient_human.get('username', 'friend')
    other_name = other_human.get('name') or other_human.get('username', 'someone')
    other_username = other_human.get('username', '')

    # generate summaries
    recipient_summary = summarize_human(recipient_human)
    other_summary = summarize_human(other_human)
    overlap_summary = summarize_overlap(match_data)

    # build profile URL with token if available
    if other_username:
        profile_url = f"{CONNECTD_URL}/{other_username}"
        if recipient_token:
            profile_url += f"?t={recipient_token}"
    else:
        profile_url = other_human.get('url', '')

    # interested line - tells them about their inbox
    interested_line = ''
    if recipient_token:
        interested_url = f"{CONNECTD_URL}/interested/{recipient_token}"
        if interested_count > 0:
            interested_line = f"\n{interested_count} people already want to meet you: {interested_url}"
        else:
            interested_line = f"\nbe the first to connect: {interested_url}"

    # determine best channel
    contact = recipient_human.get('contact', {})
    if isinstance(contact, str):
        try:
            contact = json.loads(contact)
        except:
            contact = {}

    channel = None
    channel_address = None

    # prefer email if available
    if contact.get('email'):
        channel = 'email'
        channel_address = contact['email']
    elif recipient_human.get('platform') == 'github':
        channel = 'github'
        channel_address = recipient_human.get('url')
    elif recipient_human.get('platform') == 'mastodon':
        channel = 'mastodon'
        channel_address = recipient_human.get('username')
    elif recipient_human.get('platform') == 'reddit':
        channel = 'reddit'
        channel_address = recipient_human.get('username')
    else:
        channel = 'manual'
        channel_address = recipient_human.get('url')

    # choose template based on channel
    if channel in ['mastodon', 'reddit']:
        template = SHORT_TEMPLATE
    else:
        template = INTRO_TEMPLATE

    # render draft
    draft = template.format(
        recipient_name=recipient_name.split()[0] if recipient_name else 'friend',
        recipient_summary=recipient_summary,
        other_name=other_name.split()[0] if other_name else 'someone',
        other_summary=other_summary,
        overlap_summary=overlap_summary,
        profile_url=profile_url,
        interested_line=interested_line,
    )

    return {
        'recipient_human': recipient_human,
        'other_human': other_human,
        'channel': channel,
        'channel_address': channel_address,
        'draft': draft,
        'overlap_score': match_data.get('overlap_score', 0),
        'match_id': match_data.get('id'),
        'recipient_token': recipient_token,
    }


def draft_intros_for_match(match_data, token_a=None, token_b=None, interested_a=0, interested_b=0):
    """
    draft intros for both parties in a match
    returns list of two intro dicts
    """
    intro_a = draft_intro(match_data, recipient='a', recipient_token=token_a, interested_count=interested_a)
    intro_b = draft_intro(match_data, recipient='b', recipient_token=token_b, interested_count=interested_b)

    return [intro_a, intro_b]
