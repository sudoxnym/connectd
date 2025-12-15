"""
matchd/overlap.py - find pairs with alignment
"""

import json
from .fingerprint import fingerprint_similarity


def find_overlap(human_a, human_b, fp_a=None, fp_b=None):
    """
    analyze overlap between two humans
    returns overlap details: score, shared values, complementary skills
    """
    # parse stored json if needed
    signals_a = human_a.get('signals', [])
    if isinstance(signals_a, str):
        signals_a = json.loads(signals_a)

    signals_b = human_b.get('signals', [])
    if isinstance(signals_b, str):
        signals_b = json.loads(signals_b)

    extra_a = human_a.get('extra', {})
    if isinstance(extra_a, str):
        extra_a = json.loads(extra_a)

    extra_b = human_b.get('extra', {})
    if isinstance(extra_b, str):
        extra_b = json.loads(extra_b)

    # shared signals
    shared_signals = list(set(signals_a) & set(signals_b))

    # shared topics
    topics_a = set(extra_a.get('topics', []))
    topics_b = set(extra_b.get('topics', []))
    shared_topics = list(topics_a & topics_b)

    # complementary skills (what one has that the other doesn't)
    langs_a = set(extra_a.get('languages', {}).keys())
    langs_b = set(extra_b.get('languages', {}).keys())
    complementary_langs = list((langs_a - langs_b) | (langs_b - langs_a))

    # geographic compatibility
    loc_a = human_a.get('location', '').lower() if human_a.get('location') else ''
    loc_b = human_b.get('location', '').lower() if human_b.get('location') else ''

    pnw_keywords = ['seattle', 'portland', 'washington', 'oregon', 'pnw', 'cascadia', 'pacific northwest']
    remote_keywords = ['remote', 'anywhere', 'distributed']

    a_pnw = any(k in loc_a for k in pnw_keywords) or 'pnw' in signals_a
    b_pnw = any(k in loc_b for k in pnw_keywords) or 'pnw' in signals_b
    a_remote = any(k in loc_a for k in remote_keywords) or 'remote' in signals_a
    b_remote = any(k in loc_b for k in remote_keywords) or 'remote' in signals_b

    geographic_match = False
    geo_reason = None

    if a_pnw and b_pnw:
        geographic_match = True
        geo_reason = 'both in pnw'
    elif (a_pnw or b_pnw) and (a_remote or b_remote):
        geographic_match = True
        geo_reason = 'pnw + remote compatible'
    elif a_remote and b_remote:
        geographic_match = True
        geo_reason = 'both remote-friendly'

    # calculate overlap score
    base_score = 0

    # shared values (most important)
    base_score += len(shared_signals) * 10

    # shared interests
    base_score += len(shared_topics) * 5

    # complementary skills bonus (they can help each other)
    if complementary_langs:
        base_score += min(len(complementary_langs), 5) * 3

    # geographic bonus
    if geographic_match:
        base_score += 20

    # fingerprint similarity if available
    fp_score = 0
    if fp_a and fp_b:
        fp_score = fingerprint_similarity(fp_a, fp_b) * 50

    total_score = base_score + fp_score

    # build reasons
    overlap_reasons = []
    if shared_signals:
        overlap_reasons.append(f"shared values: {', '.join(shared_signals[:5])}")
    if shared_topics:
        overlap_reasons.append(f"shared interests: {', '.join(shared_topics[:5])}")
    if geo_reason:
        overlap_reasons.append(geo_reason)
    if complementary_langs:
        overlap_reasons.append(f"complementary skills: {', '.join(complementary_langs[:5])}")

    return {
        'overlap_score': total_score,
        'shared_signals': shared_signals,
        'shared_topics': shared_topics,
        'complementary_skills': complementary_langs,
        'geographic_match': geographic_match,
        'geo_reason': geo_reason,
        'overlap_reasons': overlap_reasons,
        'fingerprint_similarity': fp_score / 50 if fp_a and fp_b else None,
    }


def is_same_person(human_a, human_b):
    """
    check if two records might be the same person (cross-platform)
    """
    # same platform = definitely different records
    if human_a['platform'] == human_b['platform']:
        return False

    # check username similarity
    user_a = human_a.get('username', '').lower().split('@')[0]
    user_b = human_b.get('username', '').lower().split('@')[0]

    if user_a == user_b:
        return True

    # check if github username matches
    contact_a = human_a.get('contact', {})
    contact_b = human_b.get('contact', {})

    if isinstance(contact_a, str):
        contact_a = json.loads(contact_a)
    if isinstance(contact_b, str):
        contact_b = json.loads(contact_b)

    # github cross-reference
    if contact_a.get('github') and contact_a.get('github') == contact_b.get('github'):
        return True
    if contact_a.get('github') == user_b or contact_b.get('github') == user_a:
        return True

    # email cross-reference
    if contact_a.get('email') and contact_a.get('email') == contact_b.get('email'):
        return True

    return False
