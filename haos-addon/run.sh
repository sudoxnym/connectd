#!/usr/bin/with-contenv bashio
# shellcheck shell=bash

# read options from add-on config
export HOST_USER=$(bashio::config 'host_user')
export HOST_NAME=$(bashio::config 'host_name')
export HOST_EMAIL=$(bashio::config 'host_email')
export HOST_MASTODON=$(bashio::config 'host_mastodon')
export HOST_REDDIT=$(bashio::config 'host_reddit')
export HOST_LEMMY=$(bashio::config 'host_lemmy')
export HOST_LOBSTERS=$(bashio::config 'host_lobsters')
export HOST_MATRIX=$(bashio::config 'host_matrix')
export HOST_DISCORD=$(bashio::config 'host_discord')
export HOST_BLUESKY=$(bashio::config 'host_bluesky')
export HOST_LOCATION=$(bashio::config 'host_location')
export HOST_INTERESTS=$(bashio::config 'host_interests')
export HOST_LOOKING_FOR=$(bashio::config 'host_looking_for')

export GITHUB_TOKEN=$(bashio::config 'github_token')
export GROQ_API_KEY=$(bashio::config 'groq_api_key')

export MASTODON_TOKEN=$(bashio::config 'mastodon_token')
export MASTODON_INSTANCE=$(bashio::config 'mastodon_instance')

export DISCORD_BOT_TOKEN=$(bashio::config 'discord_bot_token')
export DISCORD_TARGET_SERVERS=$(bashio::config 'discord_target_servers')

export LEMMY_INSTANCE=$(bashio::config 'lemmy_instance')
export LEMMY_USERNAME=$(bashio::config 'lemmy_username')
export LEMMY_PASSWORD=$(bashio::config 'lemmy_password')

export SMTP_HOST=$(bashio::config 'smtp_host')
export SMTP_PORT=$(bashio::config 'smtp_port')
export SMTP_USER=$(bashio::config 'smtp_user')
export SMTP_PASS=$(bashio::config 'smtp_pass')

# set data paths
export DB_PATH=/data/db/connectd.db
export CACHE_DIR=/data/cache

bashio::log.info "starting connectd daemon..."
bashio::log.info "HOST_USER: ${HOST_USER}"

cd /app
exec python3 daemon.py
