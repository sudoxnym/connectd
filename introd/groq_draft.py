"""
introd/groq_draft.py - groq llama 4 maverick for smart intro drafting

uses groq api to generate personalized, natural intro messages
that don't sound like ai-generated slop
"""

import os
import json
import requests
from datetime import datetime

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
MODEL = os.environ.get('GROQ_MODEL', 'llama-3.1-70b-versatile')


def determine_contact_method(human):
    """
    determine best contact method based on WHERE THEY'RE MOST ACTIVE

    don't use fixed hierarchy - analyze activity per platform:
    - count posts/commits/activity
    - weight by recency (last 30 days matters more)
    - contact them where they already are
    - fall back to email only if no social activity
    """
    from datetime import datetime, timedelta

    extra = human.get('extra', {})
    if isinstance(extra, str):
        extra = json.loads(extra) if extra else {}

    # handle nested extra.extra from old save format
    if 'extra' in extra and isinstance(extra['extra'], dict):
        extra = {**extra, **extra['extra']}

    contact = human.get('contact', {})
    if isinstance(contact, str):
        contact = json.loads(contact) if contact else {}

    # collect activity scores per platform
    activity_scores = {}
    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)
    ninety_days_ago = now - timedelta(days=90)

    # github activity
    github_username = human.get('username') if human.get('platform') == 'github' else extra.get('github')
    if github_username:
        github_score = 0
        top_repos = extra.get('top_repos', [])

        for repo in top_repos:
            # recent commits weight more
            pushed_at = repo.get('pushed_at', '')
            if pushed_at:
                try:
                    push_date = datetime.fromisoformat(pushed_at.replace('Z', '+00:00')).replace(tzinfo=None)
                    if push_date > thirty_days_ago:
                        github_score += 10  # very recent
                    elif push_date > ninety_days_ago:
                        github_score += 5   # somewhat recent
                    else:
                        github_score += 1   # old but exists
                except:
                    github_score += 1

            # stars indicate engagement
            github_score += min(repo.get('stars', 0) // 10, 5)

        # commit activity from deep scrape
        commit_count = extra.get('commit_count', 0)
        github_score += min(commit_count // 10, 20)

        if github_score > 0:
            activity_scores['github_issue'] = {
                'score': github_score,
                'info': f"{github_username}/{top_repos[0]['name']}" if top_repos else github_username
            }

    # mastodon activity
    mastodon_handle = extra.get('mastodon') or contact.get('mastodon')
    if mastodon_handle:
        mastodon_score = 0
        statuses_count = extra.get('mastodon_statuses', 0) or human.get('statuses_count', 0)

        # high post count = active user
        if statuses_count > 1000:
            mastodon_score += 30
        elif statuses_count > 500:
            mastodon_score += 20
        elif statuses_count > 100:
            mastodon_score += 10
        elif statuses_count > 0:
            mastodon_score += 5

        # platform bonus for fediverse (values-aligned)
        mastodon_score += 10

        # bonus if handle was discovered via rel="me" or similar verification
        # (having a handle linked from their website = they want to be contacted there)
        handles = extra.get('handles', {})
        if handles.get('mastodon') == mastodon_handle:
            mastodon_score += 15  # verified handle bonus

        if mastodon_score > 0:
            activity_scores['mastodon'] = {'score': mastodon_score, 'info': mastodon_handle}

    # bluesky activity
    bluesky_handle = extra.get('bluesky') or contact.get('bluesky')
    if bluesky_handle:
        bluesky_score = 0
        posts_count = extra.get('bluesky_posts', 0) or human.get('posts_count', 0)

        if posts_count > 500:
            bluesky_score += 25
        elif posts_count > 100:
            bluesky_score += 15
        elif posts_count > 0:
            bluesky_score += 5

        # newer platform, slightly lower weight
        bluesky_score += 5

        if bluesky_score > 0:
            activity_scores['bluesky'] = {'score': bluesky_score, 'info': bluesky_handle}

    # twitter activity
    twitter_handle = extra.get('twitter') or contact.get('twitter')
    if twitter_handle:
        twitter_score = 0
        tweets_count = extra.get('twitter_tweets', 0)

        if tweets_count > 1000:
            twitter_score += 20
        elif tweets_count > 100:
            twitter_score += 10
        elif tweets_count > 0:
            twitter_score += 5

        # if we found them via twitter hashtags, they're active there
        if human.get('platform') == 'twitter':
            twitter_score += 15

        if twitter_score > 0:
            activity_scores['twitter'] = {'score': twitter_score, 'info': twitter_handle}

    # NOTE: reddit is DISCOVERY ONLY, not a contact method
    # we find users on reddit but reach out via their external links (github, mastodon, etc.)
    # reddit-only users go to manual_queue for review

    # lobsters activity
    lobsters_username = extra.get('lobsters') or contact.get('lobsters')
    if lobsters_username or human.get('platform') == 'lobsters':
        lobsters_score = 0
        lobsters_username = lobsters_username or human.get('username')

        karma = extra.get('lobsters_karma', 0) or human.get('karma', 0)

        # lobsters is invite-only, high signal
        lobsters_score += 15

        if karma > 100:
            lobsters_score += 15
        elif karma > 50:
            lobsters_score += 10
        elif karma > 0:
            lobsters_score += 5

        if lobsters_score > 0:
            activity_scores['lobsters'] = {'score': lobsters_score, 'info': lobsters_username}

    # matrix activity
    matrix_id = extra.get('matrix') or contact.get('matrix')
    if matrix_id:
        matrix_score = 0

        # matrix users are typically privacy-conscious and technical
        matrix_score += 15  # platform bonus for decentralized chat

        # bonus if handle was discovered via rel="me" verification
        handles = extra.get('handles', {})
        if handles.get('matrix') == matrix_id:
            matrix_score += 10  # verified handle bonus

        if matrix_score > 0:
            activity_scores['matrix'] = {'score': matrix_score, 'info': matrix_id}

    # pick highest activity platform
    if activity_scores:
        best_platform = max(activity_scores.items(), key=lambda x: x[1]['score'])
        return best_platform[0], best_platform[1]['info']

    # fall back to email ONLY if no social activity detected
    email = extra.get('email') or contact.get('email')
    # also check emails list
    if not email:
        emails = extra.get('emails') or contact.get('emails') or []
        for e in emails:
            if e and '@' in e and 'noreply' not in e.lower():
                email = e
                break

    if email and '@' in email and 'noreply' not in email.lower():
        return 'email', email

    # last resort: manual
    return 'manual', None


def draft_intro_with_llm(match_data, recipient='a', dry_run=False):
    """
    use groq llama 4 maverick to draft a personalized intro

    match_data should contain:
    - human_a: the first person
    - human_b: the second person
    - overlap_score: numeric score
    - overlap_reasons: list of why they match

    recipient: 'a' or 'b' - who we're writing to
    """
    if not GROQ_API_KEY:
        return None, "GROQ_API_KEY not set"

    # determine recipient and other person
    if recipient == 'a':
        to_person = match_data.get('human_a', {})
        other_person = match_data.get('human_b', {})
    else:
        to_person = match_data.get('human_b', {})
        other_person = match_data.get('human_a', {})

    # build context
    to_name = to_person.get('name') or to_person.get('username', 'friend')
    other_name = other_person.get('name') or other_person.get('username', 'someone')

    to_signals = to_person.get('signals', [])
    if isinstance(to_signals, str):
        to_signals = json.loads(to_signals) if to_signals else []

    other_signals = other_person.get('signals', [])
    if isinstance(other_signals, str):
        other_signals = json.loads(other_signals) if other_signals else []

    overlap_reasons = match_data.get('overlap_reasons', [])
    if isinstance(overlap_reasons, str):
        overlap_reasons = json.loads(overlap_reasons) if overlap_reasons else []

    # parse extra data
    to_extra = to_person.get('extra', {})
    other_extra = other_person.get('extra', {})
    if isinstance(to_extra, str):
        to_extra = json.loads(to_extra) if to_extra else {}
    if isinstance(other_extra, str):
        other_extra = json.loads(other_extra) if other_extra else {}

    # build profile summaries
    to_profile = f"""
name: {to_name}
platform: {to_person.get('platform', 'unknown')}
bio: {to_person.get('bio') or 'no bio'}
location: {to_person.get('location') or 'unknown'}
signals: {', '.join(to_signals[:8])}
repos: {len(to_extra.get('top_repos', []))} public repos
languages: {', '.join(to_extra.get('languages', {}).keys())}
"""

    other_profile = f"""
name: {other_name}
platform: {other_person.get('platform', 'unknown')}
bio: {other_person.get('bio') or 'no bio'}
location: {other_person.get('location') or 'unknown'}
signals: {', '.join(other_signals[:8])}
repos: {len(other_extra.get('top_repos', []))} public repos
languages: {', '.join(other_extra.get('languages', {}).keys())}
url: {other_person.get('url', '')}
"""

    # build prompt
    system_prompt = """you are connectd, an ai that connects isolated builders who share values but don't know each other yet.

your job is to write a short, genuine intro message to one person about another person they might want to know.

rules:
- be brief (3-5 sentences max)
- be genuine, not salesy or fake
- focus on WHY they might want to connect, not just WHAT they have in common
- don't be cringe or use buzzwords
- lowercase preferred (casual tone)
- no emojis unless the person's profile suggests they'd like them
- mention specific things from their profiles, not generic "you both like open source"
- end with a simple invitation, not a hard sell
- sign off as "- connectd" (lowercase)

bad examples:
- "I noticed you're both passionate about..." (too formal)
- "You two would be PERFECT for each other!" (too salesy)
- "As a fellow privacy enthusiast..." (cringe)

good examples:
- "hey, saw you're building X. there's someone else working on similar stuff in Y who might be interesting to know."
- "you might want to check out Z's work on federated systems - similar approach to what you're doing with A."
"""

    user_prompt = f"""write an intro message to {to_name} about {other_name}.

RECIPIENT ({to_name}):
{to_profile}

INTRODUCING ({other_name}):
{other_profile}

WHY THEY MATCH (overlap score {match_data.get('overlap_score', 0)}):
{', '.join(overlap_reasons[:5])}

write a short intro message. remember: lowercase, genuine, not salesy."""

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                'Authorization': f'Bearer {GROQ_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': MODEL,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                'temperature': 0.7,
                'max_tokens': 300,
            },
            timeout=30,
        )

        if response.status_code != 200:
            return None, f"groq api error: {response.status_code} - {response.text}"

        data = response.json()
        draft = data['choices'][0]['message']['content'].strip()

        # determine contact method for recipient
        contact_method, contact_info = determine_contact_method(to_person)

        return {
            'draft': draft,
            'model': MODEL,
            'to': to_name,
            'about': other_name,
            'overlap_score': match_data.get('overlap_score', 0),
            'contact_method': contact_method,
            'contact_info': contact_info,
            'generated_at': datetime.now().isoformat(),
        }, None

    except Exception as e:
        return None, f"groq error: {str(e)}"


def draft_intro_batch(matches, dry_run=False):
    """
    draft intros for multiple matches
    returns list of (match, intro_result, error) tuples
    """
    results = []

    for match in matches:
        # draft for both directions
        intro_a, err_a = draft_intro_with_llm(match, recipient='a', dry_run=dry_run)
        intro_b, err_b = draft_intro_with_llm(match, recipient='b', dry_run=dry_run)

        results.append({
            'match': match,
            'intro_to_a': intro_a,
            'intro_to_b': intro_b,
            'errors': [err_a, err_b],
        })

    return results


def test_groq_connection():
    """test that groq api is working"""
    if not GROQ_API_KEY:
        return False, "GROQ_API_KEY not set"

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                'Authorization': f'Bearer {GROQ_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': MODEL,
                'messages': [{'role': 'user', 'content': 'say "ok" and nothing else'}],
                'max_tokens': 10,
            },
            timeout=10,
        )

        if response.status_code == 200:
            return True, "groq api working"
        else:
            return False, f"groq api error: {response.status_code}"

    except Exception as e:
        return False, f"groq connection error: {str(e)}"
