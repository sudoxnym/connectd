"""
matchd/lost.py - lost builder matching

lost builders don't get matched to each other (both need energy).
they get matched to ACTIVE builders who can inspire them.

the goal: show them someone like them who made it.
"""

import json
from .overlap import find_overlap, is_same_person


def find_inspiring_builder(lost_user, active_builders, db=None):
    """
    find an active builder who could inspire a lost builder.

    criteria:
    - shared interests (they need to relate to this person)
    - active builder has shipped real work (proof it's possible)
    - similar background signals if possible
    - NOT the same person across platforms
    """
    if not active_builders:
        return None, "no active builders available"

    # parse lost user data
    lost_signals = lost_user.get('signals', [])
    if isinstance(lost_signals, str):
        lost_signals = json.loads(lost_signals) if lost_signals else []

    lost_extra = lost_user.get('extra', {})
    if isinstance(lost_extra, str):
        lost_extra = json.loads(lost_extra) if lost_extra else {}

    # lost user interests
    lost_interests = set()
    lost_interests.update(lost_signals)
    lost_interests.update(lost_extra.get('topics', []))
    lost_interests.update(lost_extra.get('aligned_topics', []))

    # also include subreddits if from reddit (shows interests)
    subreddits = lost_user.get('subreddits', [])
    if isinstance(subreddits, str):
        subreddits = json.loads(subreddits) if subreddits else []
    lost_interests.update(subreddits)

    # score each active builder
    candidates = []

    for builder in active_builders:
        # skip if same person (cross-platform)
        if is_same_person(lost_user, builder):
            continue

        # get builder signals
        builder_signals = builder.get('signals', [])
        if isinstance(builder_signals, str):
            builder_signals = json.loads(builder_signals) if builder_signals else []

        builder_extra = builder.get('extra', {})
        if isinstance(builder_extra, str):
            builder_extra = json.loads(builder_extra) if builder_extra else {}

        # builder interests
        builder_interests = set()
        builder_interests.update(builder_signals)
        builder_interests.update(builder_extra.get('topics', []))
        builder_interests.update(builder_extra.get('aligned_topics', []))

        # calculate match score
        shared_interests = lost_interests & builder_interests
        match_score = len(shared_interests) * 10

        # bonus for high-value shared signals
        high_value_signals = ['privacy', 'selfhosted', 'home_automation', 'foss',
                              'solarpunk', 'cooperative', 'decentralized', 'queer']
        for signal in shared_interests:
            if signal in high_value_signals:
                match_score += 15

        # bonus if builder has shipped real work (proof it's possible)
        repos = builder_extra.get('top_repos', [])
        if len(repos) >= 5:
            match_score += 20  # they've built things
        elif len(repos) >= 2:
            match_score += 10

        # bonus for high stars (visible success)
        total_stars = sum(r.get('stars', 0) for r in repos) if repos else 0
        if total_stars >= 100:
            match_score += 15
        elif total_stars >= 20:
            match_score += 5

        # bonus for similar location (relatable)
        lost_loc = (lost_user.get('location') or '').lower()
        builder_loc = (builder.get('location') or '').lower()
        if lost_loc and builder_loc:
            pnw_keywords = ['seattle', 'portland', 'washington', 'oregon', 'pnw']
            if any(k in lost_loc for k in pnw_keywords) and any(k in builder_loc for k in pnw_keywords):
                match_score += 10

        # minimum threshold - need SOMETHING in common
        if match_score < 10:
            continue

        candidates.append({
            'builder': builder,
            'match_score': match_score,
            'shared_interests': list(shared_interests)[:5],
            'repos_count': len(repos),
            'total_stars': total_stars,
        })

    if not candidates:
        return None, "no matching active builders found"

    # sort by match score, return best
    candidates.sort(key=lambda x: x['match_score'], reverse=True)
    best = candidates[0]

    return best, None


def find_matches_for_lost_builders(db, min_lost_score=40, min_values_score=20, limit=10):
    """
    find inspiring builder matches for all lost builders ready for outreach.

    returns list of (lost_user, inspiring_builder, match_data)
    """
    # get lost builders ready for outreach
    lost_builders = db.get_lost_builders_for_outreach(
        min_lost_score=min_lost_score,
        min_values_score=min_values_score,
        limit=limit
    )

    if not lost_builders:
        return [], "no lost builders ready for outreach"

    # get active builders who can inspire
    active_builders = db.get_active_builders(min_score=50, limit=200)

    if not active_builders:
        return [], "no active builders available"

    matches = []

    for lost_user in lost_builders:
        best_match, error = find_inspiring_builder(lost_user, active_builders, db)

        if best_match:
            matches.append({
                'lost_user': lost_user,
                'inspiring_builder': best_match['builder'],
                'match_score': best_match['match_score'],
                'shared_interests': best_match['shared_interests'],
                'builder_repos': best_match['repos_count'],
                'builder_stars': best_match['total_stars'],
            })

    return matches, None


def get_lost_match_summary(match_data):
    """
    get a human-readable summary of a lost builder match.
    """
    lost = match_data['lost_user']
    builder = match_data['inspiring_builder']

    lost_name = lost.get('name') or lost.get('username', 'someone')
    builder_name = builder.get('name') or builder.get('username', 'a builder')

    lost_signals = match_data.get('lost_signals', [])
    if isinstance(lost_signals, str):
        lost_signals = json.loads(lost_signals) if lost_signals else []

    shared = match_data.get('shared_interests', [])

    summary = f"""
lost builder: {lost_name} ({lost.get('platform')})
  lost score: {lost.get('lost_potential_score', 0)}
  values score: {lost.get('score', 0)}
  url: {lost.get('url')}

inspiring builder: {builder_name} ({builder.get('platform')})
  score: {builder.get('score', 0)}
  repos: {match_data.get('builder_repos', 0)}
  stars: {match_data.get('builder_stars', 0)}
  url: {builder.get('url')}

match score: {match_data.get('match_score', 0)}
shared interests: {', '.join(shared) if shared else 'values alignment'}

this lost builder needs to see that someone like them made it.
"""
    return summary.strip()
