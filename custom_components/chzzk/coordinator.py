"""Per-channel polling coordinator.

To keep Chzzk's API happy we split the per-poll work in two:

* ``live-status`` is fetched on every tick (default 60 s). This is what
  changes minute-to-minute: `is_live`, viewer count, title, thumbnail URL.
* ``channel`` (name, avatar, follower count) is refreshed only every Nth tick
  (default 10 → every ~10 minutes). It barely changes and re-fetching it on
  every poll is what tends to trip Chzzk's "too many requests from one
  session" heuristic and invalidate the NID cookies.

If a channel-info refresh fails we keep using the cached value rather than
marking the whole coordinator as failed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ChannelInfo,
    ChzzkApiError,
    ChzzkChannelNotFound,
    ChzzkClient,
    LiveStatus,
)
from .const import CHANNEL_INFO_EVERY_N_POLLS, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChzzkData:
    """Snapshot returned from each refresh."""

    channel: ChannelInfo
    live: LiveStatus


class ChzzkCoordinator(DataUpdateCoordinator[ChzzkData]):
    """Polls Chzzk once per channel."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ChzzkClient,
        channel_id: str,
        channel_name: str,
        update_interval: timedelta | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{channel_id}",
            update_interval=update_interval or DEFAULT_SCAN_INTERVAL,
        )
        self._client = client
        self.channel_id = channel_id
        self.channel_name = channel_name
        self._cached_channel: ChannelInfo | None = None
        self._tick = 0  # incremented each successful poll

    async def _async_update_data(self) -> ChzzkData:
        # live-status: every tick. Cheap polling endpoint; lacks the thumbnail.
        try:
            live = await self._client.get_live_status(self.channel_id)
        except ChzzkChannelNotFound as exc:
            raise UpdateFailed(f"Channel {self.channel_id} not found: {exc}") from exc
        except ChzzkApiError as exc:
            raise UpdateFailed(str(exc)) from exc

        # If the channel is live, fetch the thumbnail (only available on the
        # heavier live-detail endpoint). One extra call/min/live-channel.
        if live.is_live:
            try:
                thumb = await self._client.get_live_thumbnail(self.channel_id)
            except ChzzkApiError as exc:
                _LOGGER.debug("Live thumbnail fetch failed (non-fatal): %s", exc)
                thumb = None
            if thumb:
                live = replace(live, live_image_url=thumb)

        # channel info: first tick, then every Nth tick. Fall back to the cache
        # on failure so a transient blip doesn't blank out the entity device
        # info.
        if (
            self._cached_channel is None
            or self._tick % CHANNEL_INFO_EVERY_N_POLLS == 0
        ):
            try:
                self._cached_channel = await self._client.get_channel(self.channel_id)
            except ChzzkChannelNotFound as exc:
                if self._cached_channel is None:
                    raise UpdateFailed(
                        f"Channel {self.channel_id} not found: {exc}"
                    ) from exc
                _LOGGER.warning(
                    "Channel info disappeared, keeping cache: %s", exc
                )
            except ChzzkApiError as exc:
                if self._cached_channel is None:
                    raise UpdateFailed(str(exc)) from exc
                _LOGGER.warning(
                    "Channel info refresh failed, keeping cache: %s", exc
                )

        self._tick += 1
        assert self._cached_channel is not None
        if self._cached_channel.channel_name:
            self.channel_name = self._cached_channel.channel_name
        return ChzzkData(channel=self._cached_channel, live=live)
