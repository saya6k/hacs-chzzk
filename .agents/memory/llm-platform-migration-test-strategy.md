---
name: llm-platform-migration-test-strategy
description: "When hacs-chzzk gets a test suite, use hacs-kakao-map's vendored-fixture pattern for testing llm.py/llm_api.py against HA dev-branch snapshots"
metadata: 
  node_type: memory
  type: project
  originSessionId: 1f558932-5de4-4d06-8762-df41b717d1c2
---

When adding tests to hacs-chzzk (no test suite exists yet as of 2026-07-13), port the vendored-fixture
testing pattern from `~/Projects/hacs-kakao-map` for exercising `custom_components/chzzk/llm.py` and
`llm_api.py` against unreleased HA versions, instead of relying only on manual/container-based
verification.

**Why:** `pytest-homeassistant-custom-component` (phacc) is version-pinned to a specific released HA
version (`Requires: homeassistant==<exact>`) and is structurally incompatible with HA's `dev` branch —
any core refactor between the pinned release and the dev commit you need can break phacc's autouse
fixtures for the entire test session, not just the affected tests. This bit hacs-kakao-map directly
during its own HA 2026.8 `llm` platform migration (see [[llm-platform-migration]] in this file's
sibling notes and the source-of-truth at `~/Projects/hacs-kakao-map/.agents/memory/
ha-core-dev-snapshot-testing.md`).

kakao-map's resolution (HACS-integration-style, matches how `hacs/integration` itself handles
supporting both a min and a dev HA target): vendor a minimal `async_test_home_assistant` (hand-copied
from HA core's own `tests/common.py`, refreshed periodically) plus a trimmed `MockConfigEntry` and
`AiohttpClientMocker` into `tests/vendor/`, define local `hass`/`aioclient_mock`/
`enable_custom_integrations` fixtures in `conftest.py` (local fixtures shadow same-named phacc plugin
fixtures), and disable phacc's *other* autouse fixtures for the dev-branch run via
`pytest -p no:homeassistant` (phacc's pytest11 entry-point name is `homeassistant`, not
`pytest_homeassistant_custom_component` — check via
`importlib.metadata.entry_points(group="pytest11")` if it drifts). Wired up as a separate
`scripts/test-dev` that installs a pinned dev-branch commit, runs pytest with phacc's plugin disabled,
then restores the stable pin on exit — kept alongside the normal `scripts/test` (stable track, uses
phacc normally).

**How to apply:** once hacs-chzzk has `tests/` and a `scripts/test`, and a future HA core migration
needs dev-branch verification again (this repo's HA-2026.8 `llm.py` migration was verified instead via
a one-off Apple `container` CLI real-HA-boot script — see the 2026-07-13 session — which works but
isn't repeatable/CI-friendly), copy `tests/vendor/`, `conftest.py` fixture overrides, and
`scripts/test-dev` from `~/Projects/hacs-kakao-map` as the starting point rather than reinventing it.
Also worth carrying over: kakao-map's test explicitly asserts the aggregated API instance includes
HA's own `GetDateTime` tool alongside the integration's tools (HA's `llm` integration's own `llm/llm.py`
platform contributes `GetDateTime` to every `api_id` unconditionally, by design — not something to
filter out). chzzk's own llm.py should get the same-shaped assertion when tests land.
