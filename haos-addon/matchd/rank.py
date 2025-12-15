"""
matchd/rank.py - score and rank match quality
"""

from itertools import combinations
from .fingerprint import generate_fingerprint
from .overlap import find_overlap, is_same_person
from scoutd.deep import check_already_connected


def rank_matches(matches):
    """
    rank a list of matches by quality
    returns sorted list with quality scores
    """
    ranked = []

    for match in matches:
        # base score from overlap
        score = match.get('overlap_score', 0)

        # bonus for geographic match
        if match.get('geographic_match'):
            score *= 1.2

        # bonus for high fingerprint similarity
        fp_sim = match.get('fingerprint_similarity')
        if fp_sim and fp_sim > 0.7:
            score *= 1.3

        # bonus for complementary skills
        comp_skills = match.get('complementary_skills', [])
        if len(comp_skills) >= 3:
            score *= 1.1

        match['quality_score'] = score
        ranked.append(match)

    # sort by quality score
    ranked.sort(key=lambda x: x['quality_score'], reverse=True)

    return ranked


def find_all_matches(db, min_score=30, min_overlap=20):
    """
    find all potential matches from database
    returns list of match dicts
    """
    print("matchd: finding all potential matches...")

    # get all humans above threshold
    humans = db.get_all_humans(min_score=min_score)
    print(f"  {len(humans)} humans to match")

    # generate fingerprints
    fingerprints = {}
    for human in humans:
        fp = generate_fingerprint(human)
        fingerprints[human['id']] = fp
        db.save_fingerprint(human['id'], fp)

    print(f"  generated {len(fingerprints)} fingerprints")

    # find all pairs
    matches = []
    checked = 0
    skipped_same = 0
    skipped_connected = 0

    for human_a, human_b in combinations(humans, 2):
        checked += 1

        # skip if likely same person
        if is_same_person(human_a, human_b):
            skipped_same += 1
            continue

        # skip if already connected (same org, company, co-contributors)
        connected, reason = check_already_connected(human_a, human_b)
        if connected:
            skipped_connected += 1
            continue

        # calculate overlap
        fp_a = fingerprints.get(human_a['id'])
        fp_b = fingerprints.get(human_b['id'])

        overlap = find_overlap(human_a, human_b, fp_a, fp_b)

        if overlap['overlap_score'] >= min_overlap:
            match = {
                'human_a': human_a,
                'human_b': human_b,
                **overlap
            }
            matches.append(match)

            # save to db
            db.save_match(human_a['id'], human_b['id'], overlap)

        if checked % 1000 == 0:
            print(f"  checked {checked} pairs, {len(matches)} matches so far...")

    print(f"  checked {checked} pairs")
    print(f"  skipped {skipped_same} (same person), {skipped_connected} (already connected)")
    print(f"  found {len(matches)} potential matches")

    # rank them
    ranked = rank_matches(matches)

    return ranked


def get_top_matches(db, limit=50):
    """
    get top matches from database
    """
    match_rows = db.get_matches(limit=limit)

    matches = []
    for row in match_rows:
        human_a = db.get_human_by_id(row['human_a_id'])
        human_b = db.get_human_by_id(row['human_b_id'])

        if human_a and human_b:
            matches.append({
                'id': row['id'],
                'human_a': human_a,
                'human_b': human_b,
                'overlap_score': row['overlap_score'],
                'overlap_reasons': row['overlap_reasons'],
                'geographic_match': row['geographic_match'],
                'status': row['status'],
            })

    return matches
