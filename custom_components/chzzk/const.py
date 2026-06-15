"""Constants for the Chzzk integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "chzzk"
MANUFACTURER = "Naver"

DEFAULT_NAME = "Chzzk"
# Default ASR loop. 60 s for the live-status feed keeps per-channel API hits
# at ~1/min — well below anything Chzzk would treat as abuse. Channel
# metadata (name/avatar/follower count) refreshes far less often (see
# coordinator.py).
DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
MIN_SCAN_INTERVAL_SECONDS = 30
MAX_SCAN_INTERVAL_SECONDS = 900

# Channel info changes minutely; only refresh it every Nth live-status poll.
CHANNEL_INFO_EVERY_N_POLLS = 10

# Options-flow keys
CONF_SCAN_INTERVAL = "scan_interval"

# Config entry data keys
CONF_CHANNEL_ID = "channel_id"
CONF_CHANNEL_NAME = "channel_name"
CONF_CHANNELS = "channels"  # list[{channel_id, channel_name}] in entry.options
CONF_NID_AUT = "nid_aut"
CONF_NID_SES = "nid_ses"

# LLM API id
LLM_API_ID = "chzzk"

# Attribution shown on entities
ATTRIBUTION = "Data provided by Chzzk (api.chzzk.naver.com)"

# Live status values returned by the API
STATUS_OPEN = "OPEN"
STATUS_CLOSE = "CLOSE"
