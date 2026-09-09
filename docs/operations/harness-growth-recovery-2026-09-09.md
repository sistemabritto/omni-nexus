# Harness alignment, media and growth evidence — 2026-09-09

## Canonical harness

The operator explicitly selected **OpenCode via OmniRoute**, shared between
browser and Telegram. `providers.json` is the shared source of truth:
`active_provider=omnirouter`, `cli_command=opencode`, primary `Britto-Core`,
then `Britto-Coding`, `Britto-Heavy`, `Britto-Fast`. No external provider fallback
is configured. `telegram_follow_dashboard=true` ignores stale Telegram-only
pins; a provider selection in Telegram updates the shared active provider.

Headless Python invocations now register the selected provider/model through
`OPENCODE_CONFIG_CONTENT`, matching the browser bridge's dynamic catalog
registration. Keys are referenced through environment substitution, not written
to inline JSON. OpenCode `--auto` is retained and project permissions are
`allow`, as explicitly authorized by the operator. Per-agent deny rules and
the Telegram sender allowlist remain intact. This does not grant public access
to the bot or remove application-level publication approval gates.

An independently confirmed OpenClaude defect was also addressed for future
compatibility: `--dangerously-skip-permissions` retains memory approval checks;
explicit `OPENCLAUDE_PERMISSION_MODE=fullAccess` now uses the fullAccess mode
without the conflicting bypass flag. **This is not the selected Magneto
harness and that environment override was removed from the deployed bot.**

## Media / Hermes

All four existing Britto combos already include Claude vision models. The
gateway Vision Bridge default pointed at an unconfigured OpenAI model; its
DB setting now uses the connected Claude Sonnet route. Settings were backed
up before the change. The installed gateway's transcription endpoint requires
a provider/model identifier; a chat combo is not a transcription model.

Magneto sends actual pixels for image analysis, explicitly requesting a
non-streaming JSON response. Previously it only supplied a local path and
the model could answer without reading the image. Audio uses
`/v1/audio/transcriptions` through OmniRoute, model
`groq/whisper-large-v3-turbo`, with Telegram `.oga` names normalized to `.ogg`.

Hermes default/excarplex/iron/stoic use `Britto-Core`, with Heavy/Fast fallbacks;
their auxiliary vision and STT also point to OmniRoute. The canonical Swarm
service hostname is `evonexus_omniroute`. Logs showed DNS failures during the
earlier single-gateway replacement; changing a combo cannot fix a gateway
that is temporarily unreachable. No HA claim is made.

Hermes approvals are `off` as authorized, preserving sender allowlists and
explicit deny rules. Its OpenAI-compatible STT upload required the same Ogg
filename normalization; `scripts/patch-hermes-stt.py` checks the exact upstream
source before applying it. Rebuild with `scripts/Dockerfile.hermes-stt`.

## Growth data access

`omni-growth.timer` runs daily at 05:10 America/Bahia. The collector uses
selected credentials in `/etc/omni-growth.env` (root-only), official API reads,
Supabase's read-only endpoint, read-only ClickHouse settings and PostgreSQL
read-only transactions. Only aggregate CRM data is exported: no contact
names, telephone numbers, message contents or payment payloads.

Outputs: `/workspace/workspace/reports/growth/latest.json` and `latest.md` on
the shared workspace volume. Authenticated API: `/api/metricas/acquisition`.
The response includes age and a >36h stale flag. Missing sources are explicitly
unavailable, not zero. No arbitrary SQL endpoint was exposed.

Magneto's relevant prompts receive a compact freshness-checked summary;
weekly editorial research also receives this context. Proposed actions are
evidence-based hypotheses, not autonomous outbound campaigns. The full private
business report is `workspace/reports/[C]aquisicao-conversao-30d-2026-09-09.md`.
It is intentionally excluded from the code push.

The routine is a baseline and proposal loop, not model-weight training or
proof of improved sales. Controlled lead/payment tests, attribution fixes,
consent reconciliation and commercial campaigns remain proposed work.

## Deployment / verification

Local VPS image tags:

- `evo-nexus-runtime:harness-fix-20260909` — Telegram and scheduler.
- `evo-nexus-dashboard:harness-fix-20260909` — dashboard/browser bridge.
- `hermes-agent:stt-fix-20260909` — Hermes shared runtime, upstream v0.21.1.

Use `agent-recovery.override.yml` after the main EvoNexus stack. Hermes is a
separate stack: its service image is persisted in Swarm; rebuild/reapply the
STT image on future upstream upgrades only after verifying patch compatibility.

Validation performed:

- Shared browser and Telegram configuration inspected live: OpenCode,
  `omnirouter`, `Britto-Core`.
- Exact Telegram orchestration function invoked without sending chat messages:
  wrote/read a fresh workspace file and returned `FINAL_OPENCODE_OK`.
- OpenCode provider registration, permission compatibility, image payload,
  synchronization, provider fallback and growth contracts tested.
- Iron high-reasoning tool execution wrote/read the inclusive sum test;
  explicit Python `range(1,1001)` returned `234168`. An earlier model-generated
  calculation omitted the inclusive upper bound; that was not a provider error.
- Live image and audio probes used existing authorized Telegram media; output
  logs contain success/length only, not the private transcript.
- Acquisition API returns fresh evidence, daily collection completed with all
  six sources, and the timer is enabled. No lead messages or payment tests sent.

Relevant contracts: [OpenCode permissions](https://opencode.ai/docs/permissions/),
[OpenCode configuration](https://opencode.ai/docs/config/),
[Supabase read-only queries](https://supabase.com/docs/reference/api/v1-read-only-query).
