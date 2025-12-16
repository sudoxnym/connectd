"""
matchd/fingerprint.py - generate values profiles for humans
"""

import json
from collections import defaultdict

# values dimensions we track
VALUES_DIMENSIONS = [
    'privacy',          # surveillance concern, degoogle, self-hosted
    'decentralization', # p2p, fediverse, local-first
    'cooperation',      # coops, mutual aid, community
    'queer_friendly',   # lgbtq+, pronouns
    'environmental',    # solarpunk, degrowth, sustainability
    'anticapitalist',   # post-capitalism, worker ownership
    'builder',          # creates vs consumes
    'pnw_oriented',     # pacific northwest connection
]

# skill categories
SKILL_CATEGORIES = [
    'backend',      # python, go, rust, databases
    'frontend',     # js, react, css
    'devops',       # docker, k8s, linux admin
    'hardware',     # electronics, embedded, iot
    'design',       # ui/ux, graphics
    'community',    # organizing, facilitation
    'writing',      # documentation, content
]

# signal to dimension mapping
SIGNAL_TO_DIMENSION = {
    'privacy': 'privacy',
    'selfhosted': 'privacy',
    'degoogle': 'privacy',
    'decentralized': 'decentralization',
    'local_first': 'decentralization',
    'p2p': 'decentralization',
    'federated_chat': 'decentralization',
    'foss': 'decentralization',
    'cooperative': 'cooperation',
    'community': 'cooperation',
    'mutual_aid': 'cooperation',
    'intentional_community': 'cooperation',
    'queer': 'queer_friendly',
    'pronouns': 'queer_friendly',
    'blm': 'queer_friendly',
    'acab': 'queer_friendly',
    'solarpunk': 'environmental',
    'anticapitalist': 'anticapitalist',
    'pnw': 'pnw_oriented',
    'pnw_state': 'pnw_oriented',
    'remote': 'pnw_oriented',
    'home_automation': 'builder',
    'modern_lang': 'builder',
    'unix': 'builder',
    'containers': 'builder',
}

# language to skill mapping
LANGUAGE_TO_SKILL = {
    'python': 'backend',
    'go': 'backend',
    'rust': 'backend',
    'java': 'backend',
    'ruby': 'backend',
    'php': 'backend',
    'javascript': 'frontend',
    'typescript': 'frontend',
    'html': 'frontend',
    'css': 'frontend',
    'vue': 'frontend',
    'shell': 'devops',
    'dockerfile': 'devops',
    'nix': 'devops',
    'hcl': 'devops',
    'c': 'hardware',
    'c++': 'hardware',
    'arduino': 'hardware',
    'verilog': 'hardware',
}


def generate_fingerprint(human_data):
    """
    generate a values fingerprint for a human

    input: human dict from database (has signals, languages, etc)
    output: fingerprint dict with values_vector, skills, interests
    """
    # parse stored json fields
    signals = human_data.get('signals', [])
    if isinstance(signals, str):
        signals = json.loads(signals)

    extra = human_data.get('extra', {})
    if isinstance(extra, str):
        extra = json.loads(extra)

    languages = extra.get('languages', {})
    topics = extra.get('topics', [])

    # build values vector
    values_vector = defaultdict(float)

    # from signals
    for signal in signals:
        dimension = SIGNAL_TO_DIMENSION.get(signal)
        if dimension:
            values_vector[dimension] += 1.0

    # normalize values vector (0-1 scale)
    max_val = max(values_vector.values()) if values_vector else 1
    values_vector = {k: min(v / max_val, 1.0) for k, v in values_vector.items()}

    # fill in missing dimensions with 0
    for dim in VALUES_DIMENSIONS:
        if dim not in values_vector:
            values_vector[dim] = 0.0

    # determine skills from languages
    skills = defaultdict(float)
    total_repos = sum(languages.values()) if languages else 1

    for lang, count in languages.items():
        skill = LANGUAGE_TO_SKILL.get(lang.lower())
        if skill:
            skills[skill] += count / total_repos

    # normalize skills
    if skills:
        max_skill = max(skills.values())
        skills = {k: min(v / max_skill, 1.0) for k, v in skills.items()}

    # interests from topics and signals
    interests = list(set(topics + signals))

    # location preference
    location_pref = None
    if 'pnw' in signals or 'pnw_state' in signals:
        location_pref = 'pnw'
    elif 'remote' in signals:
        location_pref = 'remote'
    elif human_data.get('location'):
        loc = human_data['location'].lower()
        if any(x in loc for x in ['seattle', 'portland', 'washington', 'oregon', 'pnw', 'cascadia']):
            location_pref = 'pnw'

    # availability (based on hireable flag if present)
    availability = None
    if extra.get('hireable'):
        availability = 'open'

    return {
        'human_id': human_data.get('id'),
        'values_vector': dict(values_vector),
        'skills': dict(skills),
        'interests': interests,
        'location_pref': location_pref,
        'availability': availability,
    }


def fingerprint_similarity(fp_a, fp_b):
    """
    calculate similarity between two fingerprints
    returns 0-1 score
    """
    # values similarity (cosine-ish)
    va = fp_a.get('values_vector', {})
    vb = fp_b.get('values_vector', {})

    all_dims = set(va.keys()) | set(vb.keys())
    if not all_dims:
        return 0.0

    dot_product = sum(va.get(d, 0) * vb.get(d, 0) for d in all_dims)
    mag_a = sum(v**2 for v in va.values()) ** 0.5
    mag_b = sum(v**2 for v in vb.values()) ** 0.5

    if mag_a == 0 or mag_b == 0:
        values_sim = 0.0
    else:
        values_sim = dot_product / (mag_a * mag_b)

    # interest overlap (jaccard)
    ia = set(fp_a.get('interests', []))
    ib = set(fp_b.get('interests', []))

    if ia or ib:
        interest_sim = len(ia & ib) / len(ia | ib)
    else:
        interest_sim = 0.0

    # location compatibility
    loc_a = fp_a.get('location_pref')
    loc_b = fp_b.get('location_pref')

    loc_sim = 0.0
    if loc_a == loc_b and loc_a is not None:
        loc_sim = 1.0
    elif loc_a == 'remote' or loc_b == 'remote':
        loc_sim = 0.5
    elif loc_a == 'pnw' or loc_b == 'pnw':
        loc_sim = 0.3

    # weighted combination
    similarity = (values_sim * 0.5) + (interest_sim * 0.3) + (loc_sim * 0.2)

    return similarity
