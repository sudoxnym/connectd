"""
introd/draft.py - AI writes intro messages referencing both parties' work
"""

import json

# intro template - transparent about being AI, neutral third party
INTRO_TEMPLATE = """hi {recipient_name},

i'm an AI that connects isolated builders working on similar things.

you're building: {recipient_summary}

{other_name} is building: {other_summary}

overlap: {overlap_summary}

thought you might benefit from knowing each other.

their work: {other_url}

no pitch. just connection. ignore if not useful.

- connectd
"""

# shorter version for platforms with character limits
SHORT_TEMPLATE = """hi {recipient_name} - i'm an AI connecting aligned builders.

you: {recipient_summary}
{other_name}: {other_summary}

overlap: {overlap_summary}

their work: {other_url}

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
        signals = json.loads(signals)

    # extra data
    extra = human_data.get('extra', {})
    if isinstance(extra, str):
        extra = json.loads(extra)

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
        reasons = json.loads(reasons)

    if reasons:
        return ' | '.join(reasons[:3])

    # fallback
    shared = overlap_data.get('shared_signals', [])
    if shared:
        return f"shared interests: {', '.join(shared[:3])}"

    return "aligned values and interests"


def draft_intro(match_data, recipient='a'):
    """
    draft an intro message for a match

    match_data: dict with human_a, human_b, overlap info
    recipient: 'a' or 'b' - who receives this intro

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

    # generate summaries
    recipient_summary = summarize_human(recipient_human)
    other_summary = summarize_human(other_human)
    overlap_summary = summarize_overlap(match_data)

    # other's url
    other_url = other_human.get('url', '')

    # determine best channel
    contact = recipient_human.get('contact', {})
    if isinstance(contact, str):
        contact = json.loads(contact)

    channel = None
    channel_address = None

    # prefer email if available
    if contact.get('email'):
        channel = 'email'
        channel_address = contact['email']
    # github issue/discussion
    elif recipient_human.get('platform') == 'github':
        channel = 'github'
        channel_address = recipient_human.get('url')
    # mastodon DM
    elif recipient_human.get('platform') == 'mastodon':
        channel = 'mastodon'
        channel_address = recipient_human.get('username')
    # reddit message
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
        recipient_name=recipient_name.split()[0] if recipient_name else 'friend',  # first name only
        recipient_summary=recipient_summary,
        other_name=other_name.split()[0] if other_name else 'someone',
        other_summary=other_summary,
        overlap_summary=overlap_summary,
        other_url=other_url,
    )

    return {
        'recipient_human': recipient_human,
        'other_human': other_human,
        'channel': channel,
        'channel_address': channel_address,
        'draft': draft,
        'overlap_score': match_data.get('overlap_score', 0),
        'match_id': match_data.get('id'),
    }


def draft_intros_for_match(match_data):
    """
    draft intros for both parties in a match
    returns list of two intro dicts
    """
    intro_a = draft_intro(match_data, recipient='a')
    intro_b = draft_intro(match_data, recipient='b')

    return [intro_a, intro_b]
