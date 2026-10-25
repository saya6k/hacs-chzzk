"""Thin async client for the public-but-undocumented Chzzk endpoints."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.chzzk.naver.com"
LIVE_STATUS_URL = BASE_URL + "/polling/v2/channels/{channel_id}/live-status"
LIVE_DETAIL_URL = BASE_URL + "/service/v2/channels/{channel_id}/live-detail"
CHANNEL_URL = BASE_URL + "/service/v1/channels/{channel_id}"
VIDEOS_URL = (
    BASE_URL
    + "/service/v1/channels/{channel_id}/videos"
    + "?sortType=LATEST&pagingType=PAGE&page=0&size={size}"
)
VIDEO_URL = BASE_URL + "/service/v3/videos/{video_no}"
VOD_PLAYBACK_URL = (
    "https://apis.naver.com/neonplayer/vodplay/v2/playback/{video_id}?key={in_key}"
)

_CHANNEL_ID_RE = re.compile(r"[0-9a-fA-F]{32}")
_CHANNEL_URL_RE = re.compile(
    r"chzzk\.naver\.com/(?:live/)?(?P<id>[0-9a-fA-F]{32})"
)

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (HomeAssistant; +https://www.home-assistant.io) "
        "hacs-chzzk/0.1"
    ),
}


class ChzzkApiError(Exception):
    """Raised when Chzzk returns a non-success payload or HTTP error."""


class ChzzkChannelNotFound(ChzzkApiError):
    """Raised when the channel ID is well-formed but unknown to Chzzk."""


@dataclass(frozen=True)
class ChannelInfo:
    channel_id: str
    channel_name: str
    channel_image_url: str | None
    channel_description: str | None
    follower_count: int | None
    open_live: bool
    verified_mark: bool


@dataclass(frozen=True)
class LiveStatus:
    is_live: bool
    title: str | None
    category_type: str | None
    category_value: str | None
    concurrent_user_count: int | None
    accumulate_count: int | None
    open_date: datetime | None
    live_image_url: str | None
    adult: bool
    chat_channel_id: str | None


@dataclass(frozen=True)
class VideoInfo:
    video_no: int
    title: str
    thumbnail_url: str | None
    publish_date: datetime | None
    duration: int | None  # seconds
    adult: bool


def extract_channel_id(value: str) -> str | None:
    """Pull a 32-hex channel id out of either a raw id or a chzzk.naver.com URL."""
    value = (value or "").strip()
    if not value:
        return None
    match = _CHANNEL_URL_RE.search(value)
    if match:
        return match.group("id").lower()
    match = _CHANNEL_ID_RE.fullmatch(value)
    if match:
        return value.lower()
    return None


_KST = timezone(timedelta(hours=9))


def _parse_chzzk_datetime(raw: str | None) -> datetime | None:
    """Convert Chzzk's "2026-05-20 02:12:18" KST string to an aware UTC datetime."""
    if not raw:
        return None
    try:
        naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        _LOGGER.debug("Unrecognized Chzzk datetime: %r", raw)
        return None
    return naive.replace(tzinfo=_KST).astimezone(timezone.utc)


class ChzzkClient:
    """Minimal async wrapper. The websession is owned by the caller (HA)."""

    def __init__(
        self,
        session: ClientSession,
        *,
        timeout: float = 10.0,
        cookies: dict[str, str] | None = None,
    ) -> None:
        self._session = session
        self._timeout = ClientTimeout(total=timeout)
        # Per-request Cookie header so we don't mutate HA's shared cookie jar.
        self._cookies = {k: v for k, v in (cookies or {}).items() if v}

    @property
    def authenticated(self) -> bool:
        return "NID_AUT" in self._cookies and "NID_SES" in self._cookies

    async def _get_json(self, url: str, *, unwrap: bool = True) -> dict:
        headers = dict(_HEADERS)
        if self._cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        try:
            async with self._session.get(
                url, headers=headers, timeout=self._timeout
            ) as resp:
                if resp.status == 404:
                    raise ChzzkChannelNotFound(f"404 from {url}")
                resp.raise_for_status()
                payload = await resp.json(content_type=None)
        except ClientError as exc:
            raise ChzzkApiError(f"HTTP error from {url}: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise ChzzkApiError(f"Unexpected error from {url}: {exc}") from exc

        if not isinstance(payload, dict):
            raise ChzzkApiError(f"Non-object payload from {url}")
        if not unwrap:
            return payload
        if payload.get("code") not in (None, 200):
            raise ChzzkApiError(
                f"{url}: code={payload.get('code')} message={payload.get('message')}"
            )
        content = payload.get("content")
        if content is None:
            raise ChzzkChannelNotFound(f"Empty content from {url}")
        return content

    async def get_channel(self, channel_id: str) -> ChannelInfo:
        data = await self._get_json(CHANNEL_URL.format(channel_id=channel_id))
        return ChannelInfo(
            channel_id=channel_id,
            channel_name=str(data.get("channelName") or ""),
            channel_image_url=data.get("channelImageUrl") or None,
            channel_description=data.get("channelDescription") or None,
            follower_count=_int_or_none(data.get("followerCount")),
            open_live=bool(data.get("openLive", False)),
            verified_mark=bool(data.get("verifiedMark", False)),
        )

    async def get_live_status(self, channel_id: str) -> LiveStatus:
        # NOTE: the /polling/v2/.../live-status endpoint is the cheap polling
        # feed — it does *not* include ``liveImageUrl``. Fetch the live
        # thumbnail separately with :meth:`get_live_thumbnail` when needed.
        data = await self._get_json(LIVE_STATUS_URL.format(channel_id=channel_id))
        status = (data.get("status") or "").upper()
        return LiveStatus(
            is_live=status == "OPEN",
            title=data.get("liveTitle") or None,
            category_type=data.get("categoryType") or None,
            category_value=data.get("liveCategoryValue") or None,
            concurrent_user_count=_int_or_none(data.get("concurrentUserCount")),
            accumulate_count=_int_or_none(data.get("accumulateCount")),
            open_date=_parse_chzzk_datetime(data.get("openDate")),
            live_image_url=None,  # filled in by get_live_thumbnail when live
            adult=bool(data.get("adult", False)),
            chat_channel_id=data.get("chatChannelId") or None,
        )

    async def get_live_thumbnail(self, channel_id: str) -> str | None:
        """Return the resolved live thumbnail URL (720p) or ``None`` if offline.

        ``/service/v2/.../live-detail`` returns the templated ``liveImageUrl``
        only while the channel is broadcasting. Offline channels return
        ``content=null`` which surfaces as :class:`ChzzkChannelNotFound`.
        """
        try:
            data = await self._get_json(LIVE_DETAIL_URL.format(channel_id=channel_id))
        except ChzzkChannelNotFound:
            return None
        return _resolve_thumbnail(data.get("liveImageUrl"))

    async def get_live_playlist_url(self, channel_id: str) -> str | None:
        """Return the HLS master playlist URL, or ``None`` if not playable.

        The URL lives inside ``livePlaybackJson`` (a JSON *string*) on the
        live-detail endpoint and carries a signed token valid for hours, so
        fetch it on demand rather than caching it. Adult-only channels omit
        the playback JSON unless the NID cookies are set.
        """
        try:
            data = await self._get_json(LIVE_DETAIL_URL.format(channel_id=channel_id))
        except ChzzkChannelNotFound:
            return None
        return _hls_path(data.get("livePlaybackJson"))

    async def get_videos(self, channel_id: str, size: int = 20) -> list[VideoInfo]:
        """Return the channel's latest videos (replays and uploads), newest first."""
        data = await self._get_json(
            VIDEOS_URL.format(channel_id=channel_id, size=size)
        )
        return [
            VideoInfo(
                video_no=int(v["videoNo"]),
                title=str(v.get("videoTitle") or ""),
                thumbnail_url=v.get("thumbnailImageUrl") or None,
                publish_date=_parse_chzzk_datetime(v.get("publishDate")),
                duration=_int_or_none(v.get("duration")),
                adult=bool(v.get("adult", False)),
            )
            for v in data.get("data") or []
            if v.get("videoNo") is not None
        ]

    async def get_video_playback(self, video_no: int) -> tuple[str, str] | None:
        """Return ``(url, mime_type)`` for a video, or ``None`` if not playable.

        Encoded videos expose ``videoId`` + ``inKey`` for Naver's VOD player
        API, whose response carries a progressive MP4 per quality. Those MP4s
        are self-contained signed URLs, unlike its HLS playlists whose relative
        segment URIs lose the auth query. Replays still being encoded expose
        ``liveRewindPlaybackJson`` instead, in the same shape as a live
        stream. Adult / paid videos the session can't watch have neither.
        """
        try:
            data = await self._get_json(VIDEO_URL.format(video_no=video_no))
        except ChzzkChannelNotFound:
            return None
        if data.get("videoId") and data.get("inKey"):
            playback = await self._get_json(
                VOD_PLAYBACK_URL.format(
                    video_id=data["videoId"], in_key=data["inKey"]
                ),
                unwrap=False,
            )
            if url := _best_mp4(playback):
                return url, "video/mp4"
        if url := _hls_path(data.get("liveRewindPlaybackJson")):
            return url, "application/vnd.apple.mpegurl"
        return None


def _int_or_none(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hls_path(playback_json: str | None) -> str | None:
    """Pull the HLS master playlist URL out of a ``*PlaybackJson`` string."""
    try:
        playback = json.loads(playback_json or "null")
    except ValueError:
        _LOGGER.debug("Unparseable playback JSON: %r", playback_json)
        return None
    for media in (playback or {}).get("media") or []:
        if media.get("mediaId") == "HLS" and media.get("path"):
            return media["path"]
    return None


def _best_mp4(playback: dict) -> str | None:
    """Pick the highest-resolution progressive MP4 from a VOD playback MPD."""
    best: tuple[int, str] | None = None
    for period in playback.get("period") or []:
        for adaptation in period.get("adaptationSet") or []:
            if adaptation.get("mimeType") != "video/mp4":
                continue
            for rep in adaptation.get("representation") or []:
                urls = rep.get("baseURL") or []
                if not urls or not urls[0].get("value"):
                    continue
                height = _int_or_none(rep.get("height")) or 0
                if best is None or height > best[0]:
                    best = (height, urls[0]["value"])
    return best[1] if best else None


def _resolve_thumbnail(url: str | None, size: int = 720) -> str | None:
    """Chzzk's ``liveImageUrl`` arrives with a ``{type}`` placeholder for the
    resolution. Substitute it server-side so consumers (Glance, the LLM tool,
    binary_sensor entity_picture, …) all get a real URL.
    """
    if not url:
        return None
    return url.replace("{type}", str(size))
