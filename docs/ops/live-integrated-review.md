# Integrated Live candidate review

Local branch `review/live-transport-integrated`, based on release candidate `2d397cf`.
Integrated PR39 commits `16e4894` and `7defeed`, and PR40 frontend commit `eed305f`.
No deployment, credential read/configuration, Google request or real microphone test.

## Independent review and fixes

- Verified actual `app.py` registers the Live blueprint and its HTTP/WebSocket rules. The new wiring test compiles the real auth functions and real import/registration statements against an isolated Flask app, avoiding production boot migrations/plugins. This is not a full image boot test.
- Found bearer-to-cookie authentication leakage: `login_user` persisted a service user's session despite the comment promising request-only login. Restored the original Flask session after resolving an API token, retaining `current_user` only for that request. Live additionally rejects bearer authentication before it runs. Tests confirm an API token works for a normal authenticated request but cannot mint a cookie usable for Live on the next request.
- Fixed watchdog deadline to include time spent opening the provider connection.
- Frontend now handles `reconnect_required` explicitly, releases microphone/playback/socket, and requires a fresh click.
- Both supported hosts tested with actual localhost WebSocket connections, existing fixture login cookies and production-equivalent ProxyFix. Cross-host Origin remains rejected. This does not validate the live reverse proxy or a user's actual cookie.
- Reviewed SQLite transactions: 1 active session/user, 4 globally, 10 seconds between starts, lease expiry after 140 seconds; persistent data path shared by the single dashboard replica. Provider/client cleanup on disconnect, protocol failure, deadline and goAway. Input PCM16k and output PCM24k contract agrees with frontend.
- Image dependency path: `Dockerfile.swarm.dashboard` copies pyproject/uv.lock and runs `uv sync --no-dev`; flask-sock and websockets are production dependencies. Existing start-dashboard starts Flask app.run (threaded by default), compatible with Flask-Sock. Image not rebuilt/booted during this review.
- PR40 applies without conflict: native dialog top layer avoids transformed-sidebar stacking; labels, cancel-first delete confirmation, focus restoration, 44px controls and landscape scroll bounds retained. Its screenshot/viewport evidence is worker-provided with intercepted APIs, not independent production QA.

## Verification results

- Broad CI-equivalent backend regression: **1019 passed, 2 skipped**. Existing SQLAlchemy deprecation/FK fixture warnings remain.
- Final focused suite after review fixes: **35 passed**, including both real loopback host cases and lease release after disconnect.
- Integrated TypeScript/Vite production build passed; existing large-chunk warning remains.
- Focused ESLint passed after documenting two pre-existing empty storage catch fallbacks in Sidebar; behavior unchanged.
- Offline `uv lock --check` passed. Existing Node bridge mock test passed.
- AST-only graphify update completed; generated graph files remain local/uncommitted. Optional SQL parser missing warning retained; no semantic model/Google call performed.
- No full Docker image boot, production browser/mic test or actual Gemini session was performed.

Official contract references: [Gemini Live API](https://ai.google.dev/api/live), [Flask-Sock API](https://flask-sock.readthedocs.io/en/latest/api.html).

## Release and activation checklist

1. Obtain direct production rollout authorization. Previous rollout was rejected by automatic review; do not retry through indirect execution.
2. Build an image from this integrated candidate, record revision/digest; snapshot DB and current service configuration, keep rollback image and existing session volume mount.
3. Deploy with Live opt-in flags absent/false. Verify dashboard health, all services, unchanged auth/session mounts and Telegram mute; GET status with a real browser cookie must be disabled, anonymous 401, bearer 403, disabled socket 503 before upgrade.
4. In the already authenticated old-domain browser, open `/live` on `nexus.workflowapi.com.br`. Verify no mic request in disabled mode. Do not move/reset the user's cookie or password. Repeat independently on the new domain after personal login there.
5. Operator personally confirms actual Google project/tier, selected model availability and quota. Flags are operator attestation, not proof of free billing. Configure the key privately plus exact model and authorize both opt-ins; no model default or fallback.
6. Only after authorized activation, test real PT-BR speech, audible 24k output, interruption, permission denial, explicit stop, navigation cleanup, disconnect and manual reconnect. Test old and new hosts with their own cookies. Confirm provider cleanup after stop/deadline and limits across workers.
7. If smoke fails, disable flags and roll back the image while preserving current data/configuration. No publication, company deletion, credential reset or billing changes are part of this candidate.

Remaining compatibility limits: ScriptProcessorNode capture; browsers unable to create a 16kHz context are rejected. Provider send can delay normal disconnect handling until bounded socket watchdog cleanup; the 120-second wall watchdog caps that path. Separate replicas with unshared lease files need a truly shared limiter before scaling. Existing API-token-issued cookies created before this fix cannot be distinguished from browser cookies; no existing sessions were revoked by this change.

## ADMIN password and lockout (read-only code findings)

Users live in the application database; password hashes use bcrypt. In the existing authenticated ADMIN session, `/users` -> edit own `admin` -> Password -> Save calls permission-gated PUT `/api/users/<id>` without requiring the forgotten old password. The user must type and submit privately. This UI has a single password field, not a confirmation pair. POST `/api/auth/change-password` requires the old password and is unsuitable when forgotten. No password, hash, env, service or session was changed.

“Too many login attempts” does not establish that the most recent password is wrong. Code uses username and IP buckets: 5 failures lock 5 minutes, 10 lock 30 minutes; failure counter reset window is 15 minutes since last failure. Respect the returned unlock time; preserve the old logged-in session, stop attempts and do not clear/bypass the throttle.

## Local image build/boot blocker

The local Docker client is installed, but daemon access reports permission denied at `/var/run/docker.sock`. Local filesystem check reports 99% used and only 3.8 GB available (219 GB filesystem); swap is effectively full. The production Dockerfile builds frontend/native terminal dependencies and installs Node, multiple agent CLIs, Python packages, MemPalace and system media tools. Starting that build here risks exhausting the user's filesystem. No image build, image pull or container boot was attempted; no daemon permissions were changed. The production VPS was not used as a fallback.

To close this gate, provide an isolated builder with sufficient free disk and bounded resources, build `Dockerfile.swarm.dashboard` from the integrated commit, and boot that exact image with fixture-only environment, no production mounts/network/credentials and feature off. Exercise status/upgrade authentication and provider-injected loopback tests before proposing production rollout. Existing successful Python/frontend/loopback evidence remains valid but is not image boot evidence.
