# Local integration review and rollout plan

Status: local preparation only, 15 October2026. Branch review/execution-recordings-local. No push, CI dispatch, publication, image build, VPS mutation or routing activation.

## Contents and provenance

Base published050a8b5:
-29d78da: read-only harness/provider/model catalog, templates and preview.
-17f3d3c: opt-in existing Live queue execution plan, restricted adapter reuse and private attempt/result trace.
-1607e27: cherry-pick of authorized video commit2a86fc9, manual per-source trims and immutable version snapshots.
-8d472dc: cherry-pick of video evidence/tests3a0dd92, based on the single synthetic render already performed by that front.
-Integration fix: Dockerfile.media-worker must copy recording_edits.py because recording_render.py imports it. Regression imports the render from the actual COPY allowlist in a separate isolated Python process, without repository PYTHONPATH. Unit edit/packaging tests added to CI.

No conflicts occurred. No Live frontend simplification has been integrated. Existing Providers frontend WIP remains in its separate worktree and is excluded. No PR86 handoff or material has been retransmitted or imported by this integration.

## Dependencies and validation

npm ci --ignore-scripts from both existing lockfiles, caches under /tmp; package manifests/lockfiles unchanged. node-pty required its usual native rebuild; npm_config_jobs=1/MAKEFLAGS=-j1 limited compilation. No installation of a new product CLI, provider SDK upgrade, credentials or permissions/config changes.

Initial HTTP attempts failed on sandbox loopback socket restriction and missing native pty.node. After lockfile installation/native rebuild, the same two tests ran with authorized loopback permission and passed:
-actual TypeScript controller→real Flask HTTP→existing queue/worker→mock provider→result in chat, idempotent retry.
-real terminal HTTP handlers and persistent SessionStore, no terminal constructor/SDK turn/provider.

Command:
```
python -m pytest tests/backend/test_live_task_dispatch.py tests/backend/test_managed_live_context.py -q -k 'real_http_ui or actual_terminal_http'
```
Result2passed,32deselected. No provider/model/harness or paid conversation started.

Integrated media regression:
```
python -m pytest tests/media/test_recording_edits.py tests/media/test_recording_worker_packaging.py tests/media/test_recordings.py tests/media/test_recording_render.py tests/media/test_media_release.py -q
```
Result62passed (291existing warnings),66.11s. This includes the repository's short synthetic FFmpeg render regression, not a render of user content; Postiz is mocked. It does not repeat the new trim-smoke test/render from the video front. Existing provided MP4/evidence remain provenance from that front, not relabeled as a second integrated render.

Backend branch evidence:106combined tests passed before final focused guards; final runtime35passed plus pending-cancel1passed. Catalog45combined tests passed. Counts overlap; do not add them as a unique aggregate.

Global frontend TypeScript check (tsc -b --pretty false) passed with the lockfile dependencies, including existing Live SDK imports and the integrated RecordingsQueue change. No Vite/app/image build or screenshot acceptance is claimed here. Separate UI front owns Live simplification. No real social delivery, voice call or provider test.

## Regression assessment

-Feature OFF retains old caller selection and does not install policy or switch active provider. A saved opt-in plan never silently falls back to a legacy/unrestricted call when disabled.
-One job/binding/decision per request; permissions, company/agent/resource revision and gates revalidated at claim/attempt/delivery; no arbitrary tool input.
-Unknown model capability, price/budget, credentials or wrong OpenCode proof binary block. Hermes/Codex unavailable, not advertised as actual adapters.
-Intent/adapter response is not independent upstream-model evidence; realized remains null without it. Nonempty provider text differs from persisted internal draft delivery.
-Additive execution_route_decisions via existing create_all; existing columns and data remain.
-Recordings trims persist in the closed snapshot; changes invalidate old QA/release and need fresh human review. Not automatic editorial feedback application, transcription, captions or posting.
-Worker packaging gap corrected. Dashboard/runtime already copy backend modules normally.
-Live remote prompt update remains independent of images. It replaced only the stale pilot sentence; no service restart or paid test occurred.

## Single-package review still pending

1. Wait for the UI front's completed commit and applicable authorization before incorporating it. Reconcile only authorized files; preserve the approved menu and current provider configuration/voice/auth.
2. Review this local diff and the separate Live manual result. A working conversation memory does not accept company context/tool invocation or actual task execution.
3. Run combined regression and UI build/visual checks after UI integration in one serialized window. CI currently contains new backend/media unit tests; no remote run dispatched.
4. Produce one final reviewed SHA, exact three image digests, CI/image smoke evidence and required publication/deployment authorization. This document is not authorization to run it.
5. Actual route-model evidence/policy attestation and monetary gateway are absent; **keep NEXUS_EXECUTION_ROUTING_ENABLED=false and NEXUS_LIVE_TASKS_ENABLED=false**. No operator policy is installed by this package.

## Proposed rollout — DO NOT EXECUTE YET

-Inspect current VPS images, service Specs/ENV/mounts, compose source and idleness. Defer for an active harness/recording/render/job; do not cancel work. Confirm no unintended source drift and adequate space.
-Private backup all service Specs/source, SQLite backup+quick_check, sessions and persistent config/media metadata. Preserve secrets as private data; never print/export keys. Record old dashboard/runtime/worker digests.
-Publish only the reviewed final SHA through the approved GitHub Actions workflow after explicit authorization. Verify each OCI revision/digest and offline image smoke. Worker image includes recording_edits.py.
-Coordinate code/images with work initially disabled. Preserve ENV/data/voice/auth and continuity ON. Keep both new execution routing and Live tasks OFF; no automatic conversation, provider call, post or queue reactivation.
-Update compatible media worker first, then scheduler/Telegram runtime and dashboard in a controlled sequence, verifying health/Spec preservation. New worker is backward compatible with old snapshots. Do not blindly redeploy a stale stack over the persistent configuration.
-Read back service/app flags, image revision, served asset hashes, authenticated/anonymous behavior and DB/session preservation. No business task/campaign/provider generation is part of smoke verification.
-Felipe initiates manual Live acceptance; media content/destination/approval checks remain independent.

### Rollback constraints

Keep exact previous images/Specs and a tested rollback command plan; do not automatically restore the database. Both routing/task gates OFF on failure. If a new closed snapshot contains trim decisions, **do not let the old renderer consume it**, since old code may ignore trim fields. Prefer retaining the backward-compatible new worker while rolling back dashboard/runtime; otherwise stop/quarantine that queued work with specific operational authorization before worker rollback. Preserve versioned assets/QA/release records and investigate, never replay uploads/posts automatically. A rollback must not overwrite concurrent remote-agent or service changes.
