# connectd home assistant integration

monitor your connectd daemon from home assistant.

## installation

### HACS (recommended)

1. open HACS in home assistant
2. click the three dots menu → custom repositories
3. add `https://github.com/sudoxnym/connectd` with category "integration"
4. search for "connectd" and install
5. restart home assistant
6. go to settings → devices & services → add integration → connectd

### manual

1. copy `custom_components/connectd` to your HA `config/custom_components/` directory
2. restart home assistant
3. go to settings → devices & services → add integration → connectd

## configuration

enter the host and port of your connectd daemon:
- **host**: IP or hostname where connectd is running (e.g., `192.168.1.8`)
- **port**: API port (default: `8099`)

## sensors

the integration creates these sensors:

### stats
- `sensor.connectd_total_humans` - total discovered humans
- `sensor.connectd_high_score_humans` - humans with high values alignment
- `sensor.connectd_total_matches` - total matches found
- `sensor.connectd_total_intros` - total intro drafts
- `sensor.connectd_sent_intros` - intros successfully sent
- `sensor.connectd_active_builders` - active builder count
- `sensor.connectd_lost_builders` - lost builder count
- `sensor.connectd_recovering_builders` - recovering builder count
- `sensor.connectd_lost_outreach_sent` - lost builder outreach count

### state
- `sensor.connectd_intros_today` - intros sent today
- `sensor.connectd_lost_intros_today` - lost builder intros today
- `sensor.connectd_status` - daemon status (running/dry_run/stopped)

### per-platform
- `sensor.connectd_github_humans`
- `sensor.connectd_mastodon_humans`
- `sensor.connectd_reddit_humans`
- `sensor.connectd_lemmy_humans`
- `sensor.connectd_discord_humans`
- `sensor.connectd_lobsters_humans`

## example dashboard card

```yaml
type: entities
title: connectd
entities:
  - entity: sensor.connectd_status
  - entity: sensor.connectd_total_humans
  - entity: sensor.connectd_intros_today
  - entity: sensor.connectd_lost_intros_today
  - entity: sensor.connectd_active_builders
  - entity: sensor.connectd_lost_builders
```

## automations

example: notify when an intro is sent:

```yaml
automation:
  - alias: "connectd intro notification"
    trigger:
      - platform: state
        entity_id: sensor.connectd_intros_today
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
    action:
      - service: notify.mobile_app
        data:
          title: "connectd"
          message: "sent intro #{{ states('sensor.connectd_intros_today') }} today"
```
