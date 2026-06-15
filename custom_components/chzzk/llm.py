"""LLM API tools that expose Chzzk channel status to conversation agents.

Tool results follow the convention used by
``jxlarrea/voice-satellite-card-llm-tools`` so the matching
``voice-satellite-card-integration`` Lovelace card can render visual feedback
without extra glue. Specifically:

* Top-level: ``source``, ``query``, ``num_results``, ``auto_display``,
  ``instruction``, ``results``.
* ``results[]``: per-item ``image_url`` + ``thumbnail_url`` + ``title`` +
  ``source_url`` so the card's image-grid renderer accepts each channel as an
  "image" tile (live thumbnail for live channels, channel avatar for offline).
* Extra per-item keys (``is_streaming``, ``stream_title``, ``category``,
  ``viewer_count``, …) are carried for the LLM to read and narrate — the card
  ignores keys it doesn't recognise.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util import slugify

from .const import DOMAIN, LLM_API_ID
from .coordinator import ChzzkCoordinator, ChzzkData


_NARRATION_HINT = (
    "Do NOT list image URLs, thumbnail URLs, or repeat the channel id verbatim. "
    "The user's Voice Satellite card already shows each channel's thumbnail and "
    "title visually. Reply with one or two natural-language sentences "
    "summarising who is streaming, what they're streaming, and the viewer "
    "count (only if asked)."
)


def _result_item(coordinator: ChzzkCoordinator) -> dict[str, Any]:
    """Build a single ``results[]`` item the satellite card can render."""
    data: ChzzkData | None = coordinator.data
    channel_id = coordinator.channel_id
    channel_url = f"https://chzzk.naver.com/{channel_id}"
    live_url = f"https://chzzk.naver.com/live/{channel_id}"

    if data is None:
        # Coordinator not yet populated — return a minimal placeholder so the
        # LLM still sees the channel exists. No image_url means the card skips
        # this tile rather than rendering a broken image.
        return {
            "title": coordinator.channel_name,
            "channel_id": channel_id,
            "source": "chzzk",
            "source_url": channel_url,
            "available": False,
        }

    live = data.live
    avatar = data.channel.channel_image_url
    live_thumb = live.live_image_url if live.is_live else None
    image_url = live_thumb or avatar

    return {
        # --- keys the satellite card consumes ---
        "image_url": image_url,
        "thumbnail_url": live_thumb or avatar,
        "title": data.channel.channel_name or coordinator.channel_name,
        "source": "chzzk",
        "source_url": live_url if live.is_live else channel_url,
        # --- extras for the LLM (and ignored by the renderer) ---
        "channel_id": channel_id,
        "is_streaming": live.is_live,
        "stream_title": live.title if live.is_live else None,
        "category": live.category_value if live.is_live else None,
        "viewer_count": live.concurrent_user_count if live.is_live else None,
        "started_at": (
            live.open_date.isoformat()
            if live.is_live and live.open_date is not None
            else None
        ),
        "follower_count": data.channel.follower_count,
        "available": True,
    }


def _all_coordinators(hass: HomeAssistant) -> list[ChzzkCoordinator]:
    bucket = hass.data.get(DOMAIN, {})
    return list(bucket.get("coordinators", {}).values())


def _find_coordinator(hass: HomeAssistant, needle: str) -> ChzzkCoordinator | None:
    needle = (needle or "").strip()
    if not needle:
        return None
    needle_lower = needle.lower()
    needle_slug = slugify(needle)
    for coord in _all_coordinators(hass):
        if coord.channel_id.lower() == needle_lower:
            return coord
        if coord.channel_name and coord.channel_name.lower() == needle_lower:
            return coord
        if slugify(coord.channel_name) == needle_slug:
            return coord
    return None


def _empty_response(query: str, message: str, *, error: str | None = None) -> dict:
    response: dict[str, Any] = {
        "source": "chzzk",
        "query": query,
        "results": [],
        "num_results": 0,
        "auto_display": False,
        "message": message,
    }
    if error:
        response["error"] = error
    return response


class _ListChannelsTool(llm.Tool):
    name = "chzzk_list_channels"
    description = (
        "List the live status of every Chzzk channel the user has added to "
        "Home Assistant. Use this when the user asks about Chzzk in general "
        "(e.g. 'who is streaming on Chzzk right now')."
    )
    parameters = vol.Schema({})

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        coords = _all_coordinators(hass)
        if not coords:
            return _empty_response(
                query="all",
                message="No Chzzk channels are configured.",
                error="no_channels",
            )
        items = [_result_item(c) for c in coords]
        live_count = sum(1 for it in items if it.get("is_streaming"))
        return {
            "source": "chzzk",
            "query": "all",
            "num_results": len(items),
            "live_count": live_count,
            "auto_display": True,
            "instruction": _NARRATION_HINT,
            "results": items,
        }


class _ChannelStatusTool(llm.Tool):
    name = "chzzk_channel_status"
    description = (
        "Get the current Chzzk live status (streaming flag, title, category, "
        "viewer count, started_at) for ONE channel identified by display "
        "name or 32-character channel id. Returns a result tile the Voice "
        "Satellite card renders inline."
    )
    parameters = vol.Schema(
        {
            vol.Required("channel"): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        needle = tool_input.tool_args["channel"]
        coord = _find_coordinator(hass, needle)
        if coord is None:
            return _empty_response(
                query=needle,
                message=(
                    f"No Chzzk channel matching {needle!r} is configured. "
                    "Add one in Settings → Devices & Services → Chzzk."
                ),
                error="channel_not_configured",
            )
        item = _result_item(coord)
        return {
            "source": "chzzk",
            "query": needle,
            "num_results": 1,
            "auto_display": True,
            "instruction": _NARRATION_HINT,
            "results": [item],
        }


_TOOLS: list[llm.Tool] = [_ListChannelsTool(), _ChannelStatusTool()]


class ChzzkLLMAPI(llm.API):
    """The integration-level LLM API. Each conversation agent opts in to it."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass=hass,
            id=LLM_API_ID,
            name="Chzzk",
        )

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt=(
                "You can query the live status of Chzzk streaming channels the "
                "user has added to Home Assistant. Prefer chzzk_channel_status "
                "when the user names a specific channel; use chzzk_list_channels "
                "for general questions. The user's Voice Satellite card renders "
                "the thumbnails returned by these tools — your spoken reply "
                "should narrate, not list URLs."
            ),
            llm_context=llm_context,
            tools=_TOOLS,
        )


def async_register(hass: HomeAssistant) -> None:
    """Register the API once, idempotently."""
    if hass.data.get(f"{DOMAIN}_llm_registered"):
        return
    llm.async_register_api(hass, ChzzkLLMAPI(hass))
    hass.data[f"{DOMAIN}_llm_registered"] = True
