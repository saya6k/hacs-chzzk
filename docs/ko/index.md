# Chzzk for Home Assistant

[치지직(Chzzk)](https://chzzk.naver.com) 스트리밍 채널을 Home Assistant에 노출하는 커스텀 통합으로, 공식 Twitch 통합과 동일한 모델로 설계됐습니다. 추가로 **LLM API**를 제공하여 대화 에이전트(OpenAI, Anthropic, Google Generative AI, Ollama 등)가 "X 지금 방송해?" 같은 질문에 도구 호출로 답할 수 있고, 시각적 피드백은 [`voice-satellite-card-integration`](https://github.com/jxlarrea/voice-satellite-card-integration)으로 렌더링됩니다.

## 엔티티 (채널당)

| 엔티티 | 타입 | 비고 |
| --- | --- | --- |
| Streaming | binary_sensor | 방송 중이면 `on`, `entity_picture` = 라이브 썸네일 / 아바타 |
| Title | sensor | 현재 방송 제목 |
| Category | sensor | `liveCategoryValue` (게임 / 토크 등) |
| Viewers | sensor | `concurrentUserCount`, `state_class: measurement` |
| Started at | sensor | `openDate`, `device_class: timestamp` |
| Followers | sensor | 채널 팔로워 수 |

## LLM API

설치 후 **설정 → 음성 비서 → [에이전트] → 선택된 LLM API**에 **"Chzzk"** 항목이 표시됩니다. 활성화하면 두 도구가 노출됩니다:

- `chzzk_list_channels()` — 구성된 모든 채널
- `chzzk_channel_status(channel)` — 표시명 또는 32자 hex ID로 단일 채널 조회

도구 결과는 [`voice-satellite-card-llm-tools`](https://github.com/jxlarrea/voice-satellite-card-llm-tools) 컨벤션을 따릅니다: `source`, `auto_display`, `instruction`, `results[]` (각 항목에 `image_url` / `thumbnail_url` / `title` / `source_url`). 매칭되는 satellite Lovelace 카드가 이미지 그리드를 자동 렌더링하고, LLM은 항목별 부가 필드(`is_streaming`, `stream_title`, `category`, `viewer_count` 등)로 설명합니다.

LLM 도구는 **Home Assistant 2026.8 이상**이 필요합니다 — HA의 `llm` 플랫폼을 통해 최초 사용 시점에 지연 로딩됩니다. 활성화하면 MCP Server 통합을 사용 중일 경우 `/api/mcp/chzzk` (관리자 토큰)로도 접근할 수 있습니다.

## 설치

### HACS

1. **HACS → ⋮ → Custom repositories** → `https://github.com/saya6k/hacs-chzzk` 추가 (카테고리 *Integration*)
2. **Chzzk** 설치 후 Home Assistant 재시작
3. **설정 → 기기 및 서비스 → 통합 추가 → Chzzk**
4. 채널 URL(`https://chzzk.naver.com/<channel_id>`) 또는 32자 채널 ID 입력
5. (선택) 다음 화면에서 chzzk.naver.com의 `NID_AUT`, `NID_SES` 쿠키 입력 — 성인 전용 채널이나 향후 인증 기능에만 필요. 비워두면 건너뜀.

### 수동

`custom_components/chzzk/`를 Home Assistant config의 `custom_components/`에 복사 후 재시작.

## 동작 원리

두 개의 Chzzk 엔드포인트를 **다른 주기**로 폴링해 세션당 호출 비율을 낮춥니다 (지속적 트래픽 시 Chzzk가 NID 쿠키를 무효화한 사례가 있음):

```
# 60초마다 — 분단위 상태: 라이브 플래그, 시청자, 제목, 썸네일 URL
GET https://api.chzzk.naver.com/polling/v2/channels/<channel_id>/live-status

# 10분마다 — 천천히 바뀌는 메타데이터: 채널명, 아바타, 팔로워 수
GET https://api.chzzk.naver.com/service/v1/channels/<channel_id>
```

결과적으로 **채널당 분당 ~1.1회의 API 호출** — 단순한 "양쪽 모두 30초마다" 패턴 대비 약 72% 감소. 썸네일 이미지 자체(`livecloud-thumb.akamaized.net/.../snapshot_720.jpg`)는 NID 쿠키를 읽지 않는 Chzzk CDN에서 오므로, 브라우저나 Glance 위젯이 몇 번 다시 그리든 레이트 리밋과 무관합니다.

쿠키를 입력한 경우, 모든 API 요청에 `Cookie: NID_AUT=...; NID_SES=...` 헤더로 전송됩니다. 만료 시 통합의 **구성** 옵션에서 쿠키를 갱신하세요.

## 왜 OAuth가 아닌 쿠키인가

Chzzk의 내부 API는 OAuth 액세스 토큰이 아닌 세션 쿠키로 인증합니다. 네이버 Application Credentials가 있어도 그 토큰을 Chzzk 세션으로 교환할 수 없습니다 — 그래서 쿠키 방식입니다.

## Glance 위젯

이 통합은 구성된 모든 채널을 집계하는 인증된 REST 엔드포인트를 노출합니다 — URL을 [Glance](https://github.com/glanceapp/glance) `custom-api` 위젯에 넣으면 Glance가 Chzzk의 비공개 API와 직접 통신하지 않고도 대시보드 타일을 얻을 수 있습니다.

```
GET http://homeassistant.local:8123/api/chzzk/channels
Authorization: Bearer <Home Assistant long-lived access token>
```

응답 (축약):

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

### Glance YAML 예시

**HA 프로필 → 보안 → 토큰 만들기**에서 long-lived access token을 만들어 Glance 환경(예: `docker-compose.yml`)에 `HA_TOKEN`으로 저장 후 위젯에서 참조:

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

Glance `custom-api` 템플릿이 지원하는 모든 것(이미지 그리드, 차트, 컬러 규칙 등)이 가능합니다 — JSON에 원시 숫자와 썸네일 URL이 그대로 노출되기 때문입니다.

## 제한사항

- API가 비공개 문서임. 엔드포인트·필드·레이트 리밋이 예고 없이 변경될 수 있음.
- 성인 전용(18+) 채널은 로그인이 필요 — 선택적 인증 단계에서 쿠키를 제공하세요.
- Twitch 통합의 *Clips*, *Subscribers* 기능에 해당하는 Chzzk 등가물은 없음.

## 라이선스

Apache 2.0.
