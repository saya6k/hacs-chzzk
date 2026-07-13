# Chzzk for Home Assistant

A custom integration that surfaces [Chzzk (치지직)](https://chzzk.naver.com) streaming channels in Home Assistant, modelled on the official Twitch integration. Bonus: an **LLM API** that lets conversation agents (OpenAI, Anthropic, Google Generative AI, Ollama, …) answer "is X streaming?" by calling tools, with visual feedback rendered by [`voice-satellite-card-integration`](https://github.com/jxlarrea/voice-satellite-card-integration).

## Entities (per channel)

| Entity | Type | Notes |
| --- | --- | --- |
| Streaming | binary_sensor | `on` while the channel is live, `entity_picture` = live thumbnail / avatar |
| Title | sensor | Current broadcast title |
| Category | sensor | `liveCategoryValue` (game / talk / etc.) |
| Viewers | sensor | `concurrentUserCount`, `state_class: measurement` |
| Started at | sensor | `openDate`, `device_class: timestamp` |
| Followers | sensor | Channel follower count |

## LLM API

Once installed, an **"Chzzk"** entry shows up under **Settings → Voice assistants → [agent] → Selected LLM APIs**. Enable it to expose two tools:

- `chzzk_list_channels()` — every configured channel
- `chzzk_channel_status(channel)` — single channel by display name or 32-hex id

Tool results follow the convention used by [`voice-satellite-card-llm-tools`](https://github.com/jxlarrea/voice-satellite-card-llm-tools): `source`, `auto_display`, `instruction`, `results[]` with each item carrying `image_url` / `thumbnail_url` / `title` / `source_url`. The matching satellite Lovelace card auto-renders an image grid; the LLM uses the extra per-item fields (`is_streaming`, `stream_title`, `category`, `viewer_count`, …) to narrate.

The LLM tools require **Home Assistant 2026.8 or later** — they're provided through HA's `llm` platform, loaded lazily on first use. Once enabled, they're also reachable over MCP at `/api/mcp/chzzk` (admin token) if you run the MCP Server integration.

## Install

### HACS

1. **HACS → ⋮ → Custom repositories** → add `https://github.com/saya6k/hacs-chzzk` (category *Integration*)
2. Install **Chzzk**, restart Home Assistant
3. **Settings → Devices & Services → Add Integration → Chzzk**
4. Paste the channel URL (`https://chzzk.naver.com/<channel_id>`) or the 32-char channel ID
5. (Optional) On the next screen, paste `NID_AUT` and `NID_SES` cookies from chzzk.naver.com — only needed for adult-only channels or future authenticated features. Leave blank to skip.

### Manual

Copy `custom_components/chzzk/` into your Home Assistant config's `custom_components/` directory and restart.

## How it works

Two Chzzk endpoints, polled on **different cadences** to keep the per-session call rate low (Chzzk has been known to revoke NID cookies under sustained traffic):

```
# every 60 s  — minute-to-minute state: live flag, viewers, title, thumbnail URL
GET https://api.chzzk.naver.com/polling/v2/channels/<channel_id>/live-status

# every 10 min — slow-changing metadata: channel name, avatar, follower count
GET https://api.chzzk.naver.com/service/v1/channels/<channel_id>
```

That works out to **~1.1 API calls per channel per minute** — about a 72 % drop versus the naive "both endpoints every 30 s" pattern. Thumbnail images themselves (`livecloud-thumb.akamaized.net/.../snapshot_720.jpg`) come from Chzzk's CDN, which doesn't read NID cookies, so however many times your browser or Glance widget redraws them is irrelevant for rate-limiting purposes.

If you supplied cookies, they're sent as the `Cookie: NID_AUT=...; NID_SES=...` header on every API request. Refresh the cookies via the integration's **Configure** options when they expire.

## Why cookies and not Naver OAuth

Chzzk's internal APIs authenticate via session cookies, not OAuth access tokens. Even with Naver Application Credentials, the token can't be exchanged for a Chzzk session — so cookies it is.

## Glance widget

The integration exposes an authenticated REST endpoint that aggregates every configured channel — drop the URL into a [Glance](https://github.com/glanceapp/glance) `custom-api` widget and you get a dashboard tile without Glance having to talk to Chzzk's undocumented API directly.

```
GET http://homeassistant.local:8123/api/chzzk/channels
Authorization: Bearer <Home Assistant long-lived access token>
```

Response (abridged):

```json
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
      "live_url": "https://chzzk.naver.com/live/abc...",
      "avatar_url": "https://...",
      "live_thumbnail_url": "https://...",
      "follower_count": 5678,
      "available": true
    }
  ]
}
```

### Glance YAML example

Create a long-lived access token under **HA profile → Security → Create token**, store it as `HA_TOKEN` in Glance's environment (e.g. in `docker-compose.yml`), and reference it from the widget:

```yaml
- type: custom-api
  title: Chzzk
  cache: 30s
  url: http://homeassistant.local:8123/api/chzzk/channels
  headers:
    Authorization: Bearer ${HA_TOKEN}
  template: |
    <ul class="list list-gap-10 collapsible-container">
      {{ range .JSON.Array "channels" }}
        <li>
          <a class="size-h4 color-primary-if-not-visited"
             href='{{ if .Bool "is_live" }}{{ .String "live_url" }}{{ else }}{{ .String "channel_url" }}{{ end }}'
             target="_blank">
            {{ .String "name" }}
            {{ if .Bool "is_live" }}<span class="color-positive">● LIVE</span>{{ else }}<span class="color-base-muted">offline</span>{{ end }}
          </a>
          {{ if .Bool "is_live" }}
            <div class="size-h6 color-base">{{ .String "title" }}</div>
            <div class="size-h6 color-base-muted">
              {{ .String "category" }} · {{ .Int "viewers" | formatNumber }} viewers
            </div>
          {{ end }}
        </li>
      {{ end }}
    </ul>
```

Anything Glance's `custom-api` template supports works — image grid, charts, color rules — because the JSON exposes the raw numbers and thumbnail URLs.

## Limitations

- The API is undocumented. Endpoints, fields, or rate limits may change without notice.
- Adult-only channels (18+) require login; provide cookies in the optional auth step.
- The Twitch integration's *Clips* and *Subscribers* features have no Chzzk equivalent.

## License

Apache 2.0.
