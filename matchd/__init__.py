"""
matchd - pairing module
generates fingerprints, finds overlaps, ranks matches
"""

from .fingerprint import generate_fingerprint
from .overlap import find_overlap
from .rank import rank_matches, find_all_matches

__all__ = ['generate_fingerprint', 'find_overlap', 'rank_matches', 'find_all_matches']
