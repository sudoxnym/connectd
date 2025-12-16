"""
shared signal patterns for all scrapers
"""

import re

# positive signals - what we're looking for
POSITIVE_PATTERNS = [
    # values
    (r'\b(solarpunk|cyberpunk)\b', 'solarpunk', 10),
    (r'\b(anarchis[tm]|mutual.?aid)\b', 'mutual_aid', 10),
    (r'\b(cooperative|collective|worker.?owned?|coop|co.?op)\b', 'cooperative', 15),
    (r'\b(community|commons)\b', 'community', 5),
    (r'\b(intentional.?community|cohousing|commune)\b', 'intentional_community', 20),

    # queer-friendly
    (r'\b(queer|lgbtq?|trans|nonbinary|enby|genderqueer)\b', 'queer', 15),
    (r'\b(they/them|she/her|he/him|xe/xem|any.?pronouns)\b', 'pronouns', 10),
    (r'\bblm\b', 'blm', 5),
    (r'\b(acab|1312)\b', 'acab', 5),

    # tech values
    (r'\b(privacy|surveillance|anti.?surveillance)\b', 'privacy', 10),
    (r'\b(self.?host(?:ed|ing)?|homelab|home.?server)\b', 'selfhosted', 15),
    (r'\b(local.?first|offline.?first)\b', 'local_first', 15),
    (r'\b(decentralized?|federation|federated|fediverse)\b', 'decentralized', 10),
    (r'\b(foss|libre|open.?source|copyleft)\b', 'foss', 10),
    (r'\b(home.?assistant|home.?automation)\b', 'home_automation', 10),
    (r'\b(mesh|p2p|peer.?to.?peer)\b', 'p2p', 10),
    (r'\b(matrix|xmpp|irc)\b', 'federated_chat', 5),
    (r'\b(degoogle|de.?google)\b', 'degoogle', 10),

    # location/availability
    (r'\b(seattle|portland|pnw|cascadia|pacific.?northwest)\b', 'pnw', 20),
    (r'\b(washington|oregon)\b', 'pnw_state', 10),
    (r'\b(remote|anywhere|relocate|looking.?to.?move)\b', 'remote', 10),

    # anti-capitalism
    (r'\b(anti.?capitalis[tm]|post.?capitalis[tm]|degrowth)\b', 'anticapitalist', 10),

    # neurodivergent (often overlaps with our values)
    (r'\b(neurodivergent|adhd|autistic|autism)\b', 'neurodivergent', 5),

    # technical skills (bonus for builders)
    (r'\b(rust|go|python|typescript)\b', 'modern_lang', 3),
    (r'\b(linux|bsd|nixos)\b', 'unix', 3),
    (r'\b(kubernetes|docker|podman)\b', 'containers', 3),
]

# negative signals - red flags
NEGATIVE_PATTERNS = [
    (r'\b(qanon|maga|trump|wwg1wga)\b', 'maga', -50),
    (r'\b(covid.?hoax|plandemic|5g.?conspiracy)\b', 'conspiracy', -50),
    (r'\b(nwo|illuminati|deep.?state)\b', 'conspiracy', -30),
    (r'\b(anti.?vax|antivax)\b', 'antivax', -30),
    (r'\b(sovereign.?citizen)\b', 'sovcit', -40),
    (r'\b(crypto.?bro|web3|nft|blockchain|bitcoin|ethereum)\b', 'crypto', -15),
    (r'\b(conservative|republican)\b', 'conservative', -20),
    (r'\b(free.?speech.?absolutist)\b', 'freeze_peach', -20),
]

# target topics for repo discovery
TARGET_TOPICS = [
    'local-first', 'self-hosted', 'privacy', 'mesh-network',
    'cooperative', 'solarpunk', 'decentralized', 'p2p',
    'fediverse', 'activitypub', 'matrix-org', 'homeassistant',
    'esphome', 'open-source-hardware', 'right-to-repair',
    'mutual-aid', 'commons', 'degoogle', 'privacy-tools',
]

# ecosystem repos - high signal contributors
ECOSYSTEM_REPOS = [
    'home-assistant/core',
    'esphome/esphome',
    'matrix-org/synapse',
    'LemmyNet/lemmy',
    'mastodon/mastodon',
    'owncast/owncast',
    'nextcloud/server',
    'immich-app/immich',
    'jellyfin/jellyfin',
    'navidrome/navidrome',
    'paperless-ngx/paperless-ngx',
    'actualbudget/actual',
    'firefly-iii/firefly-iii',
    'logseq/logseq',
    'AppFlowy-IO/AppFlowy',
    'siyuan-note/siyuan',
    'anytype/anytype-ts',
    'calcom/cal.com',
    'plausible/analytics',
    'umami-software/umami',
]

# aligned subreddits
ALIGNED_SUBREDDITS = {
    'intentionalcommunity': 25,
    'cohousing': 25,
    'cooperatives': 20,
    'solarpunk': 20,
    'selfhosted': 15,
    'homeassistant': 15,
    'homelab': 10,
    'privacy': 15,
    'PrivacyGuides': 15,
    'degoogle': 15,
    'anticonsumption': 10,
    'Frugal': 5,
    'simpleliving': 5,
    'Seattle': 10,
    'Portland': 10,
    'cascadia': 15,
    'linux': 5,
    'opensource': 10,
    'FOSS': 10,
}

# negative subreddits
NEGATIVE_SUBREDDITS = [
    'conspiracy', 'conservative', 'walkaway', 'louderwithcrowder',
    'JordanPeterson', 'TimPool', 'NoNewNormal', 'LockdownSkepticism',
]

# high-signal mastodon instances
ALIGNED_INSTANCES = {
    'tech.lgbt': 20,
    'social.coop': 25,
    'fosstodon.org': 10,
    'hackers.town': 15,
    'hachyderm.io': 10,
    'infosec.exchange': 5,
}


def analyze_text(text):
    """
    analyze text for signals
    returns: (score, signals_found, negative_signals)
    """
    if not text:
        return 0, [], []

    text = text.lower()
    score = 0
    signals = []
    negatives = []

    for pattern, signal_name, points in POSITIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            score += points
            signals.append(signal_name)

    for pattern, signal_name, points in NEGATIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            score += points  # points are already negative
            negatives.append(signal_name)

    return score, list(set(signals)), list(set(negatives))
