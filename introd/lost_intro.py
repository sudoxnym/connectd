"""
introd/lost_intro.py - intro drafting for lost builders

different tone than builder-to-builder intros.
these people need encouragement, not networking.

the goal isn't to recruit them. it's to show them the door exists.
they take it or they don't. but they'll know someone saw them.
"""

import os
import json
import requests
from datetime import datetime

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
MODEL = os.environ.get('GROQ_MODEL', 'llama-3.1-70b-versatile')


LOST_INTRO_TEMPLATE = """hey {name},

i'm connectd. i'm a daemon that finds people who might need a nudge.

i noticed you're interested in {interests}. you ask good questions. you clearly get it.

but maybe you haven't built anything yet. or you started and stopped. or you don't think you can.

that's okay. most people don't.

but some people do. here's one: {builder_name} ({builder_url})

{builder_description}

they started where you are. look at what they built.

you're not behind. you're just not started yet.

no pressure. just wanted you to know someone noticed.

- connectd"""


SYSTEM_PROMPT = """you are connectd, a daemon that finds isolated builders with aligned values and connects them.

right now you're reaching out to someone who has POTENTIAL but hasn't found it yet. maybe they gave up, maybe they're stuck, maybe they don't believe they can do it.

your job is to:
1. acknowledge where they are without being condescending
2. point them to an active builder who could inspire them
3. be genuine, not salesy or motivational-speaker-y
4. keep it short - these people are tired, don't overwhelm them
5. use lowercase, be human, no corporate bullshit
6. make it clear there's no pressure, no follow-up spam

you're not recruiting. you're not selling. you're just showing them a door.

the template structure:
- acknowledge them (you noticed something about them)
- normalize where they are (most people don't build things)
- show them someone who did (the builder)
- brief encouragement (you're not behind, just not started)
- sign off with no pressure

do NOT:
- be preachy or lecture them
- use motivational cliches ("you got this!", "believe in yourself!")
- make promises about outcomes
- be too long - they don't have energy for long messages
- make them feel bad about where they are"""


def draft_lost_intro(lost_user, inspiring_builder, config=None):
    """
    draft an intro for a lost builder, pairing them with an inspiring active builder.

    lost_user: the person who needs a nudge
    inspiring_builder: an active builder with similar interests who could inspire them
    """
    config = config or {}

    # gather info about lost user
    lost_name = lost_user.get('name') or lost_user.get('username', 'there')
    lost_signals = lost_user.get('lost_signals', [])
    lost_interests = extract_interests(lost_user)

    # gather info about inspiring builder
    builder_name = inspiring_builder.get('name') or inspiring_builder.get('username')
    builder_url = inspiring_builder.get('url') or f"https://github.com/{inspiring_builder.get('username')}"
    builder_description = create_builder_description(inspiring_builder)

    # use LLM to personalize
    if GROQ_API_KEY and config.get('use_llm', True):
        return draft_with_llm(lost_user, inspiring_builder, lost_interests, builder_description)

    # fallback to template
    return LOST_INTRO_TEMPLATE.format(
        name=lost_name,
        interests=', '.join(lost_interests[:3]) if lost_interests else 'building things',
        builder_name=builder_name,
        builder_url=builder_url,
        builder_description=builder_description,
    ), None


def extract_interests(user):
    """extract interests from user profile"""
    interests = []

    # from topics/tags
    extra = user.get('extra', {})
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except:
            extra = {}

    topics = extra.get('topics', []) or extra.get('aligned_topics', [])
    interests.extend(topics[:5])

    # from subreddits
    subreddits = user.get('subreddits', [])
    for sub in subreddits[:3]:
        if sub.lower() not in ['learnprogramming', 'findapath', 'getdisciplined']:
            interests.append(sub)

    # from bio keywords
    bio = user.get('bio') or ''
    bio_lower = bio.lower()

    interest_keywords = [
        'rust', 'python', 'javascript', 'go', 'linux', 'self-hosting', 'homelab',
        'privacy', 'security', 'open source', 'foss', 'decentralized', 'ai', 'ml',
        'web dev', 'backend', 'frontend', 'devops', 'data', 'automation',
    ]

    for kw in interest_keywords:
        if kw in bio_lower and kw not in interests:
            interests.append(kw)

    return interests[:5] if interests else ['technology', 'building things']


def create_builder_description(builder):
    """create a brief description of what the builder has done"""
    extra = builder.get('extra', {})
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except:
            extra = {}

    parts = []

    # what they build
    repos = extra.get('top_repos', [])[:3]
    if repos:
        repo_names = [r.get('name') for r in repos if r.get('name')]
        if repo_names:
            parts.append(f"they've built things like {', '.join(repo_names[:2])}")

    # their focus
    topics = extra.get('aligned_topics', []) or extra.get('topics', [])
    if topics:
        parts.append(f"they work on {', '.join(topics[:3])}")

    # their vibe
    signals = builder.get('signals', [])
    if 'self-hosted' in str(signals).lower():
        parts.append("they're into self-hosting and owning their own infrastructure")
    if 'privacy' in str(signals).lower():
        parts.append("they care about privacy")
    if 'community' in str(signals).lower():
        parts.append("they're community-focused")

    if parts:
        return '. '.join(parts) + '.'
    else:
        return "they're building cool stuff in the open."


def draft_with_llm(lost_user, inspiring_builder, interests, builder_description):
    """use LLM to draft personalized intro"""

    lost_name = lost_user.get('name') or lost_user.get('username', 'there')
    lost_signals = lost_user.get('lost_signals', [])
    lost_bio = lost_user.get('bio', '')

    builder_name = inspiring_builder.get('name') or inspiring_builder.get('username')
    builder_url = inspiring_builder.get('url') or f"https://github.com/{inspiring_builder.get('username')}"

    user_prompt = f"""draft an intro for this lost builder:

LOST USER:
- name: {lost_name}
- interests: {', '.join(interests)}
- signals detected: {', '.join(lost_signals[:5]) if lost_signals else 'general stuck/aspiring patterns'}
- bio: {lost_bio[:200] if lost_bio else 'none'}

INSPIRING BUILDER TO SHOW THEM:
- name: {builder_name}
- url: {builder_url}
- what they do: {builder_description}

write a short, genuine message. no fluff. no motivational cliches. just human.
keep it under 150 words.
use lowercase.
end with "- connectd"
"""

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={
                'Authorization': f'Bearer {GROQ_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': MODEL,
                'messages': [
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': user_prompt},
                ],
                'temperature': 0.7,
                'max_tokens': 500,
            },
            timeout=30,
        )

        if resp.status_code == 200:
            content = resp.json()['choices'][0]['message']['content']
            return content.strip(), None
        else:
            return None, f"llm error: {resp.status_code}"

    except Exception as e:
        return None, str(e)


def get_lost_intro_config():
    """get configuration for lost builder outreach"""
    return {
        'enabled': True,
        'max_per_day': 5,  # lower volume, higher care
        'require_review': True,  # always manual approval
        'cooldown_days': 90,  # don't spam struggling people
        'min_lost_score': 40,
        'min_values_score': 20,
        'use_llm': True,
    }
