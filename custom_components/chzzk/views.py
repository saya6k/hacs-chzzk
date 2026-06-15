"""Authenticated REST endpoint that aggregates every configured Chzzk channel.

Intended consumer: the `custom-api` widget in glanceapp/glance. One HTTP GET
returns the snapshot of every channel — Glance renders the rest as a card.

  GET /api/chzzk/channels
  Authorization: Bearer <Home Assistant long-lived access token>

Response shape::

    {
      "count": 2,
      "live_count": 1,
      "channels": [
        {
          "channel_id": "abc...",
          "name": "원규",
          "is_live": true,
          "title": "오늘은 발로란트",
          "category": "발로란트",
          "viewers": 1234,
          "started_at": "2026-05-19T17:12:18+00:00",
          "channel_url": "https://chzzk.naver.com/abc...",
          "live_url":    "https://chzzk.naver.com/live/abc...",
          "avatar_url":  "https://...",
          "live_thumbnail_url": "https://...",
          "follower_count": 5678,
          "available": true
        },
        { ... offline channel ... }
      ]
    }
"""

from __future__ import annotations

from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ChzzkCoordinator, ChzzkData


def _serialize(coord: ChzzkCoordinator) -> dict[str, Any]:
    channel_id = coord.channel_id
    data: ChzzkData | None = coord.data
    if data is None:
        return {
            "channel_id": channel_id,
            "name": coord.channel_name,
            "available": False,
        }
    live = data.live
    return {
        "channel_id": channel_id,
        "name": data.channel.channel_name or coord.channel_name,
        "is_live": live.is_live,
        "title": live.title if live.is_live else None,
        "category": live.category_value if live.is_live else None,
        "viewers": live.concurrent_user_count if live.is_live else None,
        "started_at": (
            live.open_date.isoformat()
            if live.is_live and live.open_date is not None
            else None
        ),
        "channel_url": f"https://chzzk.naver.com/{channel_id}",
        "live_url": (
            f"https://chzzk.naver.com/live/{channel_id}" if live.is_live else None
        ),
        "avatar_url": data.channel.channel_image_url,
        "live_thumbnail_url": live.live_image_url if live.is_live else None,
        "follower_count": data.channel.follower_count,
        "available": True,
    }


class ChzzkChannelsView(HomeAssistantView):
    """GET /api/chzzk/channels → live status of every configured channel."""

    url = "/api/chzzk/channels"
    name = "api:chzzk:channels"
    # requires_auth defaults to True — clients must pass a Bearer token.

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        bucket = self._hass.data.get(DOMAIN, {})
        coords: dict[str, ChzzkCoordinator] = bucket.get("coordinators", {})
        channels = [_serialize(c) for c in coords.values()]
        # Live channels first (highest-viewer first), offline last.
        # Server-side sort keeps the Glance/satellite templates tiny.
        channels.sort(key=_sort_key)
        return self.json(
            {
                "count": len(channels),
                "live_count": sum(1 for c in channels if c.get("is_live")),
                "channels": channels,
            }
        )


def _sort_key(channel: dict[str, Any]) -> tuple[int, int, str]:
    is_live = bool(channel.get("is_live"))
    viewers = channel.get("viewers") or 0
    name = channel.get("name") or ""
    return (0 if is_live else 1, -int(viewers), name)
