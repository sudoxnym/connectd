# connectd add-on for home assistant

find isolated builders with aligned values. auto-discovers humans on github, mastodon, lemmy, discord, and more.

## installation

1. add this repository to your home assistant add-on store
2. install the connectd add-on
3. configure your HOST_USER (github username) in the add-on settings
4. start the add-on

## configuration

### required
- **host_user**: your github username (connectd will auto-discover your profile)

### optional host info
- **host_name**: your display name
- **host_email**: your email
- **host_mastodon**: mastodon handle (@user@instance)
- **host_reddit**: reddit username
- **host_lemmy**: lemmy handle (@user@instance)
- **host_lobsters**: lobsters username
- **host_matrix**: matrix handle (@user:server)
- **host_discord**: discord user id
- **host_bluesky**: bluesky handle (handle.bsky.social)
- **host_location**: your location
- **host_interests**: comma-separated interests
- **host_looking_for**: what you're looking for

### api credentials
- **github_token**: for higher rate limits
- **groq_api_key**: for LLM-drafted intros
- **mastodon_token**: for DM delivery
- **discord_bot_token**: for discord discovery/delivery

## hacs integration

after starting the add-on, install the connectd integration via HACS:

1. add custom repository: `https://github.com/sudoxnym/connectd`
2. install connectd integration
3. add integration in HA settings
4. configure with host: `localhost`, port: `8099`

## sensors

- total humans, high score humans, active builders
- platform counts (github, mastodon, reddit, lemmy, discord, lobsters)
- priority matches, top humans
- countdown timers (next scout, match, intro)
- your personal score and profile
