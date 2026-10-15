# Gemini Live transport — activation handoff

Branch `feat/gemini-live-transport`, based exactly on PR 37 head `5b3e79e`.
No production deploy, rollout modification, real credential read or Gemini call was performed while developing/testing this change.

## Implemented path

Authenticated `/live` -> GET `/api/live/status` -> same-origin WSS `/api/live/ws` -> server-side Google Gemini BidiGenerateContent TLS WebSocket. The route is already registered by PR 37; this change adds the actual Flask-Sock transport. No terminal-server changes or shell changes are required.

Provider configuration is exclusively server-side. The browser cannot supply a provider URL, model, key, setup, tools or system prompt. Incoming audio is PCM16LE mono 16kHz, output PCM16LE mono 24kHz. Provider setup uses `generationConfig.responseModalities` per the API reference. PT-BR system instruction, input/output transcription and speech interruption are enabled. No production tools, retries, persistence or automatic reconnect.

The frontend contract additionally emits `status:listening` on turnComplete; the component now displays that state. GoAway closes both sockets and asks for a new click/new session. There is no resumption of conversation history.

## Disabled by default

All of the following must be configured deliberately by the operator **after** project free-tier/cota evidence and authorized activation:

| Server environment | Requirement |
| --- | --- |
| `GEMINI_LIVE_ENABLED` | Exactly `true`; absent/other values disable Live |
| `GEMINI_FREE_TIER_VERIFIED` | Exactly `true`, operator attestation after verifying the actual project; code does not infer free tier |
| `GEMINI_LIVE_MODEL` | Exact verified model identifier, without `models/`; no default or paid fallback |
| `GEMINI_API_KEY` | Configured personally through the authorized server environment mechanism; never browser/repo/log |

This change does not source `~/.config/omninexus/gemini.env`, provision secrets, modify billing or configure a real credential. No inference of key validity is made from its length/prefix; auth key formats can differ. Disabled mode does not read the key from the environment or open the provider.

A boolean flag is not evidence that a project is free. Capture project/tier/model quota in AI Studio before setting the attestation; paid projects can incur charges even for models that have a public free-tier table. Limits below cap usage but do not establish zero cost.

## Guards and limits

- Browser login cookie required. Agent API tokens cannot substitute. Strict known-domain Origin allowlist AND exact current host match are checked before upgrade and again in the handler. No wildcard origin.
- Shared SQLite lease store at `dashboard/data/live-limits.sqlite3` (same persistent data filesystem across workers); configurable by Flask `LIVE_LIMITS_PATH` for tests. At most 1 active session/user and 4 total, with 10s between starts. Database failures fail closed.
- All replicas must share the lease database, or keep a single dashboard replica. Separate filesystems enforce independent limits; use a shared limiter before scaling that way.
- Duration 120s, setup deadline 10s, provider open timeout 5s and close timeout 1s; wall-clock watchdog interrupts blocked socket I/O. Crash leases expire after 140s.
- Client frames limited to 32KB, audio payload 16KB/chunk, validated base64/even PCM byte count. Input token bucket refills at 40KB/s with 64KB burst. Provider messages limited to 256KB with 8-frame queue and strict 24kHz audio validation.
- Fixed Google TLS endpoint with certificate validation; sync connector does not follow HTTP redirects. System proxy disabled for this credential-bearing connection. A private disabled logger is passed to the provider library so global debug logging cannot print its key-bearing handshake URL. Errors exposed only as fixed enums; audio/transcripts are not logged.
- WebSocket needs a threaded Flask-Sock-compatible server and reverse-proxy upgrade support (same requirement as existing terminal proxy). Application HTTP/status keeps no-store headers. No deployment changes included.

## Tests and evidence

`tests/backend/test_live_transport.py`: configuration gates, fixed connector options, exact setup schema, audio/transcription/interruption, invalid input, rate limits, timeouts, provider errors, cleanup and shared-worker leases.
`tests/backend/test_live_socket_integration.py`: actual TCP/WebSocket loopback with Flask cookie session, anonymous/cross-origin rejection before provider construction, duplicate session denial, audio round-trip, interrupted event and browser-disconnect cleanup. Upstream is a queue-backed fake; no external network or real key involved.
`tests/backend/test_live_disabled_routes.py`: previous disabled/authentication regressions remain in the suite.

Run: `.venv/bin/python -m pytest -q tests/backend/test_live_transport.py tests/backend/test_live_socket_integration.py tests/backend/test_live_disabled_routes.py`.

Still required before claiming a working real conversation: confirm project free tier and model quota, personally configure credential/activation, coordinated integration/release, authenticated smoke on current domain, browser mic permission/denial/start/stop/navigation, real PT-BR audio heard, speech barge-in, disconnect/reconnect. No UI browser was available in this execution. Prototype capture still uses ScriptProcessorNode and rejects browsers that cannot provide 16kHz; AudioWorklet/resampling remain future compatibility work.

## Official references consulted 2026-10-15

- https://ai.google.dev/api/live — authoritative setup schema, activity interruption and transcriptions.
- https://ai.google.dev/gemini-api/docs/live-api/get-started-websocket — raw WebSocket endpoint and streaming audio.
- https://ai.google.dev/gemini-api/docs/api-key — server environment and confidentiality; supports evolving key types.
