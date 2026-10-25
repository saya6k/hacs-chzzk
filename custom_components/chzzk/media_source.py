"""Expose Chzzk live streams and videos as a media source.

Identifiers mirror chzzk.naver.com paths:

* ``<channel_id>`` — a configured channel (browse only): its live stream, if
  on air, followed by its latest videos.
* ``live/<channel_id>`` — the channel's live stream.
* ``video/<video_no>`` — one video (replay or upload).
"""

from __future__ import annotations

from homeassistant.components.media_player import BrowseError, MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import ChzzkApiError, ChzzkClient, VideoInfo, extract_channel_id
from .const import DEFAULT_NAME, DOMAIN
from .coordinator import ChzzkCoordinator

HLS_MIME_TYPE = "application/vnd.apple.mpegurl"


async def async_get_media_source(hass: HomeAssistant) -> ChzzkMediaSource:
    return ChzzkMediaSource(hass)


class ChzzkMediaSource(MediaSource):
    """Per configured channel: its live stream plus its latest videos."""

    name = DEFAULT_NAME

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    def _coordinators(self) -> dict[str, ChzzkCoordinator]:
        return self.hass.data.get(DOMAIN, {}).get("coordinators", {})

    def _client(self) -> ChzzkClient | None:
        return self.hass.data.get(DOMAIN, {}).get("client")

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        kind, _, value = item.identifier.partition("/")
        client = self._client()
        if client is None:
            raise Unresolvable("Chzzk is not loaded")
        # Always ask Chzzk directly: the coordinator's live flag may be up to a
        # poll interval stale, and playback URLs are signed per request.
        try:
            if kind == "live" and (channel_id := extract_channel_id(value)):
                url = await client.get_live_playlist_url(channel_id)
                if url is None:
                    raise Unresolvable(f"Chzzk channel {channel_id} is not live")
                return PlayMedia(url, HLS_MIME_TYPE)
            if kind == "video" and value.isdigit():
                playback = await client.get_video_playback(int(value))
                if playback is None:
                    raise Unresolvable(f"Chzzk video {value} is not playable")
                return PlayMedia(*playback)
        except ChzzkApiError as exc:
            raise Unresolvable(f"Chzzk API error: {exc}") from exc
        raise Unresolvable(f"Invalid Chzzk media: {item.identifier}")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        if not item.identifier:
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier=None,
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.CHANNELS,
                title=DEFAULT_NAME,
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.CHANNEL,
                children=[
                    _channel_item(coord) for coord in self._coordinators().values()
                ],
            )

        coord = self._coordinators().get(item.identifier)
        client = self._client()
        if coord is None or client is None:
            raise BrowseError(f"Unknown Chzzk channel: {item.identifier}")
        try:
            videos = await client.get_videos(coord.channel_id)
        except ChzzkApiError as exc:
            raise BrowseError(f"Chzzk API error: {exc}") from exc
        channel = _channel_item(coord)
        channel.children_media_class = MediaClass.VIDEO
        channel.children = [_video_item(v) for v in videos]
        if live := _live_item(coord):
            channel.children.insert(0, live)
        return channel


def _channel_item(coord: ChzzkCoordinator) -> BrowseMediaSource:
    data = coord.data
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=coord.channel_id,
        media_class=MediaClass.CHANNEL,
        media_content_type=MediaType.CHANNEL,
        title=coord.channel_name,
        can_play=False,
        can_expand=True,
        thumbnail=data.channel.channel_image_url if data else None,
    )


def _live_item(coord: ChzzkCoordinator) -> BrowseMediaSource | None:
    data = coord.data
    if not (data and data.live.is_live):
        return None
    title = "🔴 LIVE"
    if data.live.title:
        title = f"{title} · {data.live.title}"
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=f"live/{coord.channel_id}",
        media_class=MediaClass.VIDEO,
        media_content_type=MediaType.CHANNEL,
        title=title,
        can_play=True,
        can_expand=False,
        thumbnail=data.live.live_image_url or data.channel.channel_image_url,
    )


def _video_item(video: VideoInfo) -> BrowseMediaSource:
    title = video.title
    if video.publish_date:
        title = f"{dt_util.as_local(video.publish_date):%Y-%m-%d} {title}"
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=f"video/{video.video_no}",
        media_class=MediaClass.VIDEO,
        media_content_type=MediaType.VIDEO,
        title=title,
        can_play=True,
        can_expand=False,
        thumbnail=video.thumbnail_url,
    )
