"""
scoutd/lost.py - lost builder detection

finds people with potential who haven't found it yet, gave up, or are too beaten down to try.

these aren't failures. they're seeds that never got water.

detection signals:
- github: forked but never modified, starred many but built nothing, learning repos abandoned
- reddit/forums: "i wish i could...", stuck asking beginner questions for years, helping others but never sharing
- social: retoots builders but never posts own work, imposter syndrome language, isolation signals
- profiles: bio says what they WANT to be, "aspiring" for 2+ years, empty portfolios

the goal isn't to recruit them. it's to show them the door exists.
"""

import re
from datetime import datetime, timedelta
from collections import defaultdict


# signal definitions with weights
LOST_SIGNALS = {
    # github signals
    'forked_never_modified': {
        'weight': 15,
        'category': 'github',
        'description': 'forked repos but never pushed changes',
    },
    'starred_many_built_nothing': {
        'weight': 20,
        'category': 'github',
        'description': 'starred 50+ repos but has 0-2 own repos',
    },
    'account_no_repos': {
        'weight': 10,
        'category': 'github',
        'description': 'account exists but no public repos',
    },
    'inactivity_bursts': {
        'weight': 15,
        'category': 'github',
        'description': 'long gaps then brief activity bursts',
    },
    'only_issues_comments': {
        'weight': 12,
        'category': 'github',
        'description': 'only activity is issues/comments on others work',
    },
    'abandoned_learning_repos': {
        'weight': 18,
        'category': 'github',
        'description': 'learning/tutorial repos that were never finished',
    },
    'readme_only_repos': {
        'weight': 10,
        'category': 'github',
        'description': 'repos with just README, no actual code',
    },

    # language signals (from posts/comments/bio)
    'wish_i_could': {
        'weight': 12,
        'category': 'language',
        'description': '"i wish i could..." language',
        'patterns': [
            r'i wish i could',
            r'i wish i knew how',
            r'wish i had the (time|energy|motivation|skills?)',
        ],
    },
    'someday_want': {
        'weight': 10,
        'category': 'language',
        'description': '"someday i want to..." language',
        'patterns': [
            r'someday i (want|hope|plan) to',
            r'one day i\'ll',
            r'eventually i\'ll',
            r'when i have time i\'ll',
        ],
    },
    'stuck_beginner': {
        'weight': 20,
        'category': 'language',
        'description': 'asking beginner questions for years',
        'patterns': [
            r'still (trying|learning|struggling) (to|with)',
            r'can\'t seem to (get|understand|figure)',
            r'been trying for (months|years)',
        ],
    },
    'self_deprecating': {
        'weight': 15,
        'category': 'language',
        'description': 'self-deprecating about abilities',
        'patterns': [
            r'i\'m (not smart|too dumb|not good) enough',
            r'i (suck|am terrible) at',
            r'i\'ll never be able to',
            r'people like me (can\'t|don\'t)',
            r'i\'m just not (a|the) (type|kind)',
        ],
    },
    'no_energy': {
        'weight': 18,
        'category': 'language',
        'description': '"how do people have energy" posts',
        'patterns': [
            r'how do (people|you|they) have (the )?(energy|time|motivation)',
            r'where do (people|you|they) find (the )?(energy|motivation)',
            r'i\'m (always|constantly) (tired|exhausted|drained)',
            r'no (energy|motivation) (left|anymore)',
        ],
    },
    'imposter_syndrome': {
        'weight': 15,
        'category': 'language',
        'description': 'imposter syndrome language',
        'patterns': [
            r'imposter syndrome',
            r'feel like (a |an )?(fraud|fake|imposter)',
            r'don\'t (belong|deserve)',
            r'everyone else (seems|is) (so much )?(better|smarter)',
            r'they\'ll (find out|realize) i\'m',
        ],
    },
    'should_really': {
        'weight': 8,
        'category': 'language',
        'description': '"i should really..." posts',
        'patterns': [
            r'i (should|need to) really',
            r'i keep (meaning|wanting) to',
            r'i\'ve been (meaning|wanting) to',
        ],
    },
    'isolation_signals': {
        'weight': 20,
        'category': 'language',
        'description': 'isolation/loneliness language',
        'patterns': [
            r'no one (understands|gets it|to talk to)',
            r'(feel|feeling) (so )?(alone|isolated|lonely)',
            r'don\'t have anyone (to|who)',
            r'wish i (had|knew) (someone|people)',
        ],
    },
    'enthusiasm_for_others': {
        'weight': 10,
        'category': 'behavior',
        'description': 'celebrates others but dismissive of self',
    },

    # subreddit/community signals
    'stuck_communities': {
        'weight': 15,
        'category': 'community',
        'description': 'active in stuck/struggling communities',
        'subreddits': [
            'learnprogramming',
            'findapath',
            'getdisciplined',
            'getmotivated',
            'decidingtobebetter',
            'selfimprovement',
            'adhd',
            'depression',
            'anxiety',
        ],
    },

    # profile signals
    'aspirational_bio': {
        'weight': 12,
        'category': 'profile',
        'description': 'bio says what they WANT to be',
        'patterns': [
            r'aspiring',
            r'future',
            r'want(ing)? to (be|become)',
            r'learning to',
            r'trying to (become|be|learn)',
            r'hoping to',
        ],
    },
    'empty_portfolio': {
        'weight': 15,
        'category': 'profile',
        'description': 'links to empty portfolio sites',
    },
    'long_aspiring': {
        'weight': 20,
        'category': 'profile',
        'description': '"aspiring" in bio for 2+ years',
    },
}

# subreddits that indicate someone might be stuck
STUCK_SUBREDDITS = {
    'learnprogramming': 8,
    'findapath': 15,
    'getdisciplined': 12,
    'getmotivated': 10,
    'decidingtobebetter': 12,
    'selfimprovement': 8,
    'adhd': 10,
    'depression': 15,
    'anxiety': 12,
    'socialanxiety': 12,
    'neet': 20,
    'lostgeneration': 15,
    'antiwork': 5,  # could be aligned OR stuck
    'careerguidance': 8,
    'cscareerquestions': 5,
}


def analyze_text_for_lost_signals(text):
    """analyze text for lost builder language patterns"""
    if not text:
        return [], 0

    text_lower = text.lower()
    signals_found = []
    total_weight = 0

    for signal_name, signal_data in LOST_SIGNALS.items():
        if 'patterns' not in signal_data:
            continue

        for pattern in signal_data['patterns']:
            if re.search(pattern, text_lower):
                signals_found.append(signal_name)
                total_weight += signal_data['weight']
                break  # only count each signal once

    return signals_found, total_weight


def analyze_github_for_lost_signals(profile):
    """analyze github profile for lost builder signals"""
    signals_found = []
    total_weight = 0

    if not profile:
        return signals_found, total_weight

    repos = profile.get('repos', []) or profile.get('top_repos', [])
    extra = profile.get('extra', {})

    public_repos = profile.get('public_repos', len(repos))
    followers = profile.get('followers', 0)
    following = profile.get('following', 0)

    # starred many but built nothing
    # (we'd need to fetch starred count separately, approximate with following ratio)
    if public_repos <= 2 and following > 50:
        signals_found.append('starred_many_built_nothing')
        total_weight += LOST_SIGNALS['starred_many_built_nothing']['weight']

    # account but no repos
    if public_repos == 0:
        signals_found.append('account_no_repos')
        total_weight += LOST_SIGNALS['account_no_repos']['weight']

    # check repos for signals
    forked_count = 0
    forked_modified = 0
    learning_repos = 0
    readme_only = 0

    learning_keywords = ['learning', 'tutorial', 'course', 'practice', 'exercise',
                         'bootcamp', 'udemy', 'freecodecamp', 'odin', 'codecademy']

    for repo in repos:
        name = (repo.get('name') or '').lower()
        description = (repo.get('description') or '').lower()
        language = repo.get('language')
        is_fork = repo.get('fork', False)

        # forked but never modified
        if is_fork:
            forked_count += 1
            # if pushed_at is close to created_at, never modified
            # (simplified: just count forks for now)

        # learning/tutorial repos
        if any(kw in name or kw in description for kw in learning_keywords):
            learning_repos += 1

        # readme only (no language detected usually means no code)
        if not language and not is_fork:
            readme_only += 1

    if forked_count >= 5 and public_repos - forked_count <= 2:
        signals_found.append('forked_never_modified')
        total_weight += LOST_SIGNALS['forked_never_modified']['weight']

    if learning_repos >= 3:
        signals_found.append('abandoned_learning_repos')
        total_weight += LOST_SIGNALS['abandoned_learning_repos']['weight']

    if readme_only >= 2:
        signals_found.append('readme_only_repos')
        total_weight += LOST_SIGNALS['readme_only_repos']['weight']

    # check bio for lost signals
    bio = profile.get('bio') or ''
    bio_signals, bio_weight = analyze_text_for_lost_signals(bio)
    signals_found.extend(bio_signals)
    total_weight += bio_weight

    # aspirational bio check
    bio_lower = bio.lower()
    if any(re.search(p, bio_lower) for p in LOST_SIGNALS['aspirational_bio']['patterns']):
        if 'aspirational_bio' not in signals_found:
            signals_found.append('aspirational_bio')
            total_weight += LOST_SIGNALS['aspirational_bio']['weight']

    return signals_found, total_weight


def analyze_reddit_for_lost_signals(activity, subreddits):
    """analyze reddit activity for lost builder signals"""
    signals_found = []
    total_weight = 0

    # check subreddit activity
    stuck_sub_activity = 0
    for sub in subreddits:
        if sub.lower() in STUCK_SUBREDDITS:
            stuck_sub_activity += STUCK_SUBREDDITS[sub.lower()]

    if stuck_sub_activity >= 20:
        signals_found.append('stuck_communities')
        total_weight += min(stuck_sub_activity, 30)  # cap at 30

    # analyze post/comment text
    all_text = []
    for item in activity:
        if item.get('title'):
            all_text.append(item['title'])
        if item.get('body'):
            all_text.append(item['body'])

    combined_text = ' '.join(all_text)
    text_signals, text_weight = analyze_text_for_lost_signals(combined_text)
    signals_found.extend(text_signals)
    total_weight += text_weight

    # check for helping others but never sharing own work
    help_count = 0
    share_count = 0
    for item in activity:
        body = (item.get('body') or '').lower()
        title = (item.get('title') or '').lower()

        # helping patterns
        if any(p in body for p in ['try this', 'you could', 'have you tried', 'i recommend']):
            help_count += 1

        # sharing patterns
        if any(p in body + title for p in ['i built', 'i made', 'my project', 'check out my', 'i created']):
            share_count += 1

    if help_count >= 5 and share_count == 0:
        signals_found.append('enthusiasm_for_others')
        total_weight += LOST_SIGNALS['enthusiasm_for_others']['weight']

    return signals_found, total_weight


def analyze_social_for_lost_signals(profile, posts):
    """analyze mastodon/social for lost builder signals"""
    signals_found = []
    total_weight = 0

    # check bio
    bio = profile.get('bio') or profile.get('note') or ''
    bio_signals, bio_weight = analyze_text_for_lost_signals(bio)
    signals_found.extend(bio_signals)
    total_weight += bio_weight

    # check posts
    boost_count = 0
    original_count = 0
    own_work_count = 0

    for post in posts:
        content = (post.get('content') or '').lower()
        is_boost = post.get('reblog') is not None or post.get('repost')

        if is_boost:
            boost_count += 1
        else:
            original_count += 1

            # check if sharing own work
            if any(p in content for p in ['i built', 'i made', 'my project', 'working on', 'just shipped']):
                own_work_count += 1

        # analyze text
        text_signals, text_weight = analyze_text_for_lost_signals(content)
        for sig in text_signals:
            if sig not in signals_found:
                signals_found.append(sig)
                total_weight += LOST_SIGNALS[sig]['weight']

    # boosts builders but never posts own work
    if boost_count >= 10 and own_work_count == 0:
        signals_found.append('enthusiasm_for_others')
        total_weight += LOST_SIGNALS['enthusiasm_for_others']['weight']

    return signals_found, total_weight


def calculate_lost_potential_score(signals_found):
    """calculate overall lost potential score from signals"""
    total = 0
    for signal in signals_found:
        if signal in LOST_SIGNALS:
            total += LOST_SIGNALS[signal]['weight']
    return total


def classify_user(lost_score, builder_score, values_score):
    """
    classify user as builder, lost, or neither

    returns: 'builder' | 'lost' | 'both' | 'none'
    """
    # high builder score = active builder
    if builder_score >= 50 and lost_score < 30:
        return 'builder'

    # high lost score + values alignment = lost builder (priority outreach)
    if lost_score >= 40 and values_score >= 20:
        return 'lost'

    # both signals = complex case, might be recovering
    if lost_score >= 30 and builder_score >= 30:
        return 'both'

    return 'none'


def get_signal_descriptions(signals_found):
    """get human-readable descriptions of detected signals"""
    descriptions = []
    for signal in signals_found:
        if signal in LOST_SIGNALS:
            descriptions.append(LOST_SIGNALS[signal]['description'])
    return descriptions


def should_outreach_lost(user_data, config=None):
    """
    determine if we should reach out to a lost builder

    considers:
    - lost_potential_score threshold
    - values alignment
    - cooldown period
    - manual review requirement
    """
    config = config or {}

    lost_score = user_data.get('lost_potential_score', 0)
    values_score = user_data.get('score', 0)  # regular alignment score

    # minimum thresholds
    min_lost = config.get('min_lost_score', 40)
    min_values = config.get('min_values_score', 20)

    if lost_score < min_lost:
        return False, 'lost_score too low'

    if values_score < min_values:
        return False, 'values_score too low'

    # check cooldown
    last_outreach = user_data.get('last_lost_outreach')
    if last_outreach:
        cooldown_days = config.get('cooldown_days', 90)
        last_dt = datetime.fromisoformat(last_outreach)
        if datetime.now() - last_dt < timedelta(days=cooldown_days):
            return False, f'cooldown active (90 days)'

    # always require manual review for lost outreach
    return True, 'requires_review'
