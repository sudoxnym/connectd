#!/usr/bin/env python3
"""
profile page template and helpers for connectd
comprehensive "get to know" page showing ALL data
"""

import json
from urllib.parse import quote

PROFILE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>{name} | connectd</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
            background: #0a0a0f;
            color: #e0e0e0;
            line-height: 1.6;
        }}

        .container {{ max-width: 900px; margin: 0 auto; padding: 20px; }}

        /* header */
        .header {{
            display: flex;
            gap: 24px;
            align-items: flex-start;
            padding: 30px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px;
            margin-bottom: 24px;
            border: 1px solid #333;
        }}
        .avatar {{
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: linear-gradient(135deg, #c792ea 0%, #82aaff 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 48px;
            color: #0a0a0f;
            font-weight: bold;
            flex-shrink: 0;
        }}
        .avatar img {{ width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }}
        .header-info {{ flex: 1; }}
        .name {{ font-size: 2em; color: #c792ea; margin-bottom: 4px; }}
        .username {{ color: #82aaff; font-size: 1.1em; margin-bottom: 8px; }}
        .location {{ color: #0f8; margin-bottom: 8px; }}
        .pronouns {{
            display: inline-block;
            background: #2d3a4a;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            color: #f7c;
        }}
        .score-badge {{
            display: inline-block;
            background: linear-gradient(135deg, #c792ea 0%, #f7c 100%);
            color: #0a0a0f;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
            margin-left: 12px;
        }}
        .user-type {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            margin-left: 8px;
        }}
        .user-type.builder {{ background: #2d4a2d; color: #8f8; }}
        .user-type.lost {{ background: #4a2d2d; color: #f88; }}
        .user-type.none {{ background: #333; color: #888; }}

        /* bio section */
        .bio {{
            background: #1a1a2e;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            border: 1px solid #333;
            font-size: 1.1em;
            color: #ddd;
            font-style: italic;
        }}
        .bio:empty {{ display: none; }}

        /* sections */
        .section {{
            background: #1a1a2e;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid #333;
            overflow: hidden;
        }}
        .section-header {{
            background: #2a2a4e;
            padding: 14px 20px;
            color: #82aaff;
            font-size: 1.1em;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .section-header:hover {{ background: #3a3a5e; }}
        .section-header .toggle {{ color: #666; }}
        .section-content {{ padding: 20px; }}
        .section-content.collapsed {{ display: none; }}

        /* platforms/handles */
        .platforms {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .platform {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: #0d0d15;
            padding: 10px 16px;
            border-radius: 8px;
            border: 1px solid #333;
        }}
        .platform:hover {{ border-color: #0f8; }}
        .platform-icon {{ font-size: 1.2em; }}
        .platform a {{ color: #82aaff; text-decoration: none; }}
        .platform a:hover {{ color: #0f8; }}
        .platform-main {{ color: #c792ea; font-weight: bold; }}

        /* signals/tags */
        .tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .tag {{
            background: #2d3a4a;
            color: #82aaff;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.9em;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .tag:hover {{ background: #3d4a5a; transform: scale(1.05); }}
        .tag.positive {{ background: #2d4a2d; color: #8f8; }}
        .tag.negative {{ background: #4a2d2d; color: #f88; }}
        .tag.rare {{ background: linear-gradient(135deg, #c792ea 0%, #f7c 100%); color: #0a0a0f; }}
        .tag-detail {{
            display: none;
            background: #0d0d15;
            padding: 10px;
            border-radius: 6px;
            margin-top: 8px;
            font-size: 0.85em;
            color: #888;
        }}

        /* repos */
        .repos {{ display: flex; flex-direction: column; gap: 12px; }}
        .repo {{
            background: #0d0d15;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #333;
        }}
        .repo:hover {{ border-color: #c792ea; }}
        .repo-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .repo-name {{ color: #c792ea; font-weight: bold; }}
        .repo-name a {{ color: #c792ea; text-decoration: none; }}
        .repo-name a:hover {{ color: #f7c; }}
        .repo-stats {{ display: flex; gap: 16px; }}
        .repo-stat {{ color: #888; font-size: 0.85em; }}
        .repo-stat .star {{ color: #ffd700; }}
        .repo-desc {{ color: #aaa; font-size: 0.9em; }}
        .repo-lang {{
            display: inline-block;
            background: #333;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            color: #0f8;
        }}

        /* languages */
        .languages {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .lang {{
            background: #0d0d15;
            padding: 8px 14px;
            border-radius: 6px;
            border: 1px solid #333;
        }}
        .lang-name {{ color: #0f8; }}
        .lang-count {{ color: #666; font-size: 0.85em; margin-left: 6px; }}

        /* subreddits */
        .subreddits {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .subreddit {{
            background: #ff4500;
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        .subreddit a {{ color: white; text-decoration: none; }}

        /* matches */
        .match-summary {{
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }}
        .match-stat {{
            background: #0d0d15;
            padding: 16px 24px;
            border-radius: 8px;
            text-align: center;
        }}
        .match-stat b {{ font-size: 2em; color: #c792ea; display: block; }}
        .match-stat small {{ color: #666; }}

        /* raw data */
        .raw-data {{
            background: #0d0d15;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 0.85em;
            color: #888;
        }}
        pre {{ white-space: pre-wrap; word-break: break-all; }}

        /* contact */
        .contact-methods {{ display: flex; flex-direction: column; gap: 12px; }}
        .contact-method {{
            display: flex;
            align-items: center;
            gap: 12px;
            background: #0d0d15;
            padding: 14px 20px;
            border-radius: 8px;
            border: 1px solid #333;
        }}
        .contact-method.preferred {{ border-color: #0f8; background: #1a2a1a; }}
        .contact-method a {{ color: #82aaff; text-decoration: none; }}
        .contact-method a:hover {{ color: #0f8; }}

        /* reasons */
        .reasons {{ display: flex; flex-direction: column; gap: 8px; }}
        .reason {{
            background: #0d0d15;
            padding: 10px 14px;
            border-radius: 6px;
            color: #aaa;
            font-size: 0.9em;
            border-left: 3px solid #c792ea;
        }}

        /* back link */
        .back {{
            display: inline-block;
            color: #666;
            text-decoration: none;
            margin-bottom: 20px;
        }}
        .back:hover {{ color: #0f8; }}

        /* footer */
        .footer {{
            text-align: center;
            padding: 30px;
            color: #444;
            font-size: 0.85em;
        }}
        .footer a {{ color: #666; }}

        /* responsive */
        @media (max-width: 600px) {{
            .header {{ flex-direction: column; align-items: center; text-align: center; }}
            .avatar {{ width: 100px; height: 100px; }}
            .name {{ font-size: 1.5em; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back">← back to dashboard</a>

        <!-- HEADER -->
        <div class="header">
            <div class="avatar">{avatar}</div>
            <div class="header-info">
                <div class="name">
                    {name}
                    <span class="score-badge">{score}</span>
                    <span class="user-type {user_type_class}">{user_type}</span>
                </div>
                <div class="username">@{username} on {platform}</div>
                {location_html}
                {pronouns_html}
            </div>
        </div>

        <!-- BIO -->
        <div class="bio">{bio}</div>

        <!-- WHERE TO FIND THEM -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <span>🌐 where to find them</span>
                <span class="toggle">▼</span>
            </div>
            <div class="section-content">
                <div class="platforms">
                    {platforms_html}
                </div>
            </div>
        </div>

        <!-- WHAT THEY BUILD -->
        {repos_section}

        <!-- WHAT THEY CARE ABOUT -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <span>💜 what they care about ({signal_count} signals)</span>
                <span class="toggle">▼</span>
            </div>
            <div class="section-content">
                <div class="tags">
                    {signals_html}
                </div>
                {negative_signals_html}
            </div>
        </div>

        <!-- WHY THEY SCORED -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <span>📊 why they scored {score}</span>
                <span class="toggle">▼</span>
            </div>
            <div class="section-content">
                <div class="reasons">
                    {reasons_html}
                </div>
            </div>
        </div>

        <!-- COMMUNITIES -->
        {communities_section}

        <!-- MATCHING -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <span>🤝 in the network</span>
                <span class="toggle">▼</span>
            </div>
            <div class="section-content">
                <div class="match-summary">
                    <div class="match-stat">
                        <b>{match_count}</b>
                        <small>matches</small>
                    </div>
                    <div class="match-stat">
                        <b>{lost_score}</b>
                        <small>lost potential</small>
                    </div>
                </div>
            </div>
        </div>

        <!-- CONTACT -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <span>📬 how to connect</span>
                <span class="toggle">▼</span>
            </div>
            <div class="section-content">
                {contact_html}
            </div>
        </div>

        <!-- RAW DATA -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <span>🔍 the data (everything connectd knows)</span>
                <span class="toggle">▼</span>
            </div>
            <div class="section-content collapsed">
                <p style="color: #666; margin-bottom: 16px;">
                    public data is public. this is everything we've gathered from public sources.
                </p>
                <div class="raw-data">
                    <pre>{raw_json}</pre>
                </div>
            </div>
        </div>

        <div class="footer">
            connectd · public data is public ·
            <a href="/api/humans/{id}/full">raw json</a>
        </div>
    </div>

    <script>
        function toggleSection(header) {{
            var content = header.nextElementSibling;
            var toggle = header.querySelector('.toggle');
            if (content.classList.contains('collapsed')) {{
                content.classList.remove('collapsed');
                toggle.textContent = '▼';
            }} else {{
                content.classList.add('collapsed');
                toggle.textContent = '▶';
            }}
        }}
    </script>
</body>
</html>
"""


RARE_SIGNALS = {'queer', 'solarpunk', 'cooperative', 'intentional_community', 'trans', 'nonbinary'}

def parse_json_field(val):
    """safely parse json string or return as-is"""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except:
            return val
    return val or {}


def render_profile(human, match_count=0):
    """render full profile page for a human"""

    # parse json fields
    signals = parse_json_field(human.get('signals', '[]'))
    if isinstance(signals, str):
        signals = []

    negative_signals = parse_json_field(human.get('negative_signals', '[]'))
    if isinstance(negative_signals, str):
        negative_signals = []

    reasons = parse_json_field(human.get('reasons', '[]'))
    if isinstance(reasons, str):
        reasons = []

    contact = parse_json_field(human.get('contact', '{}'))
    extra = parse_json_field(human.get('extra', '{}'))

    # nested extra sometimes
    if 'extra' in extra:
        extra = {**extra, **parse_json_field(extra['extra'])}

    # basic info
    name = human.get('name') or human.get('username', 'unknown')
    username = human.get('username', 'unknown')
    platform = human.get('platform', 'unknown')
    bio = human.get('bio', '')
    location = human.get('location') or extra.get('location', '')
    score = human.get('score', 0)
    user_type = human.get('user_type', 'none')
    lost_score = human.get('lost_potential_score', 0)

    # avatar - first letter or image
    avatar_html = name[0].upper() if name else '?'
    avatar_url = extra.get('avatar_url') or extra.get('profile_image')
    if avatar_url:
        avatar_html = f'<img src="{avatar_url}" alt="{name}">'

    # location html
    location_html = f'<div class="location">📍 {location}</div>' if location else ''

    # pronouns - try to detect
    pronouns = extra.get('pronouns', '')
    if not pronouns and bio:
        bio_lower = bio.lower()
        if 'she/her' in bio_lower:
            pronouns = 'she/her'
        elif 'he/him' in bio_lower:
            pronouns = 'he/him'
        elif 'they/them' in bio_lower:
            pronouns = 'they/them'
    pronouns_html = f'<span class="pronouns">{pronouns}</span>' if pronouns else ''

    # platforms/handles
    handles = extra.get('handles', {})
    platforms_html = []

    # main platform
    if platform == 'github':
        platforms_html.append(f'<div class="platform platform-main"><span class="platform-icon">💻</span><a href="https://github.com/{username}" target="_blank">github.com/{username}</a></div>')
    elif platform == 'reddit':
        platforms_html.append(f'<div class="platform platform-main"><span class="platform-icon">🔴</span><a href="https://reddit.com/u/{username}" target="_blank">u/{username}</a></div>')
    elif platform == 'mastodon':
        instance = human.get('instance', 'mastodon.social')
        platforms_html.append(f'<div class="platform platform-main"><span class="platform-icon">🐘</span><a href="https://{instance}/@{username}" target="_blank">@{username}@{instance}</a></div>')
    elif platform == 'lobsters':
        platforms_html.append(f'<div class="platform platform-main"><span class="platform-icon">🦞</span><a href="https://lobste.rs/u/{username}" target="_blank">lobste.rs/u/{username}</a></div>')

    # other handles
    if handles.get('github') and platform != 'github':
        platforms_html.append(f'<div class="platform"><span class="platform-icon">💻</span><a href="https://github.com/{handles["github"]}" target="_blank">github.com/{handles["github"]}</a></div>')
    if handles.get('twitter'):
        t = handles['twitter'].lstrip('@')
        platforms_html.append(f'<div class="platform"><span class="platform-icon">🐦</span><a href="https://twitter.com/{t}" target="_blank">@{t}</a></div>')
    if handles.get('mastodon') and platform != 'mastodon':
        platforms_html.append(f'<div class="platform"><span class="platform-icon">🐘</span>{handles["mastodon"]}</div>')
    if handles.get('bluesky'):
        platforms_html.append(f'<div class="platform"><span class="platform-icon">🦋</span>{handles["bluesky"]}</div>')
    if handles.get('linkedin'):
        platforms_html.append(f'<div class="platform"><span class="platform-icon">💼</span><a href="https://linkedin.com/in/{handles["linkedin"]}" target="_blank">linkedin</a></div>')
    if handles.get('matrix'):
        platforms_html.append(f'<div class="platform"><span class="platform-icon">💬</span>{handles["matrix"]}</div>')

    # contact methods
    if contact.get('blog'):
        platforms_html.append(f'<div class="platform"><span class="platform-icon">🌐</span><a href="{contact["blog"]}" target="_blank">{contact["blog"]}</a></div>')

    # signals html
    signals_html = []
    for sig in signals:
        cls = 'tag'
        if sig in RARE_SIGNALS:
            cls = 'tag rare'
        signals_html.append(f'<span class="{cls}">{sig}</span>')

    # negative signals
    negative_signals_html = ''
    if negative_signals:
        neg_tags = ' '.join([f'<span class="tag negative">{s}</span>' for s in negative_signals])
        negative_signals_html = f'<div style="margin-top: 16px;"><small style="color: #666;">negative signals:</small><br><div class="tags" style="margin-top: 8px;">{neg_tags}</div></div>'

    # reasons html
    reasons_html = '\n'.join([f'<div class="reason">{r}</div>' for r in reasons]) if reasons else '<div class="reason">no specific reasons recorded</div>'

    # repos section
    repos_section = ''
    top_repos = extra.get('top_repos', [])
    languages = extra.get('languages', {})
    repo_count = extra.get('repo_count', 0)
    total_stars = extra.get('total_stars', 0)

    if top_repos or languages:
        repos_html = ''
        if top_repos:
            for repo in top_repos[:6]:
                repo_name = repo.get('name', 'unknown')
                repo_desc = repo.get('description', '')[:200] or 'no description'
                repo_stars = repo.get('stars', 0)
                repo_lang = repo.get('language', '')
                lang_badge = f'<span class="repo-lang">{repo_lang}</span>' if repo_lang else ''

                repos_html += f'''
                <div class="repo">
                    <div class="repo-header">
                        <span class="repo-name"><a href="https://github.com/{username}/{repo_name}" target="_blank">{repo_name}</a></span>
                        <div class="repo-stats">
                            <span class="repo-stat"><span class="star">★</span> {repo_stars:,}</span>
                            {lang_badge}
                        </div>
                    </div>
                    <div class="repo-desc">{repo_desc}</div>
                </div>
                '''

        # languages
        langs_html = ''
        if languages:
            sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:10]
            for lang, count in sorted_langs:
                langs_html += f'<div class="lang"><span class="lang-name">{lang}</span><span class="lang-count">×{count}</span></div>'

        repos_section = f'''
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <span>🔨 what they build ({repo_count} repos, {total_stars:,} ★)</span>
                <span class="toggle">▼</span>
            </div>
            <div class="section-content">
                <div class="languages" style="margin-bottom: 16px;">
                    {langs_html}
                </div>
                <div class="repos">
                    {repos_html}
                </div>
            </div>
        </div>
        '''

    # communities section (subreddits, etc)
    communities_section = ''
    subreddits = extra.get('subreddits', [])
    topics = extra.get('topics', [])

    if subreddits or topics:
        subs_html = ''
        if subreddits:
            subs_html = '<div style="margin-bottom: 16px;"><small style="color: #666;">subreddits:</small><div class="subreddits" style="margin-top: 8px;">'
            for sub in subreddits:
                subs_html += f'<span class="subreddit"><a href="https://reddit.com/r/{sub}" target="_blank">r/{sub}</a></span>'
            subs_html += '</div></div>'

        topics_html = ''
        if topics:
            topics_html = '<div><small style="color: #666;">topics:</small><div class="tags" style="margin-top: 8px;">'
            for topic in topics:
                topics_html += f'<span class="tag">{topic}</span>'
            topics_html += '</div></div>'

        communities_section = f'''
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <span>👥 communities</span>
                <span class="toggle">▼</span>
            </div>
            <div class="section-content">
                {subs_html}
                {topics_html}
            </div>
        </div>
        '''

    # contact section
    contact_html = '<div class="contact-methods">'
    emails = contact.get('emails', [])
    if contact.get('email') and contact['email'] not in emails:
        emails = [contact['email']] + emails

    if emails:
        for i, email in enumerate(emails[:3]):
            preferred = 'preferred' if i == 0 else ''
            contact_html += f'<div class="contact-method {preferred}"><span>📧</span><a href="mailto:{email}">{email}</a></div>'

    if contact.get('mastodon'):
        contact_html += f'<div class="contact-method"><span>🐘</span>{contact["mastodon"]}</div>'
    if contact.get('matrix'):
        contact_html += f'<div class="contact-method"><span>💬</span>{contact["matrix"]}</div>'
    if contact.get('twitter'):
        contact_html += f'<div class="contact-method"><span>🐦</span>@{contact["twitter"]}</div>'

    if not emails and not contact.get('mastodon') and not contact.get('matrix'):
        contact_html += '<div class="contact-method">no contact methods discovered</div>'

    contact_html += '</div>'

    # raw json
    raw_json = json.dumps(human, indent=2, default=str)

    # render
    return PROFILE_HTML.format(
        name=name,
        username=username,
        platform=platform,
        bio=bio,
        score=int(score),
        user_type=user_type,
        user_type_class=user_type,
        avatar=avatar_html,
        location_html=location_html,
        pronouns_html=pronouns_html,
        platforms_html='\n'.join(platforms_html),
        signals_html='\n'.join(signals_html),
        signal_count=len(signals),
        negative_signals_html=negative_signals_html,
        reasons_html=reasons_html,
        repos_section=repos_section,
        communities_section=communities_section,
        match_count=match_count,
        lost_score=int(lost_score),
        contact_html=contact_html,
        raw_json=raw_json,
        id=human.get('id', 0)
    )
