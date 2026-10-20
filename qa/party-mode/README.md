# Party Mode text preview

## Implemented scope

- Separate opt-in mode next to Individual in the existing Live page. The default is still Individual.
- User selects two or three members of the active twelve-agent roster. Existing authorized presentation groups can contain agents from different sectors. No forced Hera lineup, no fabricated department map.
- Selection order is the reply order. One user message starts one finite round, with a separately admitted restricted text invocation for each participant. Responses retain their agent identity.
- Server-owned conversation history is scoped to the authenticated personal Live user and company. The latest conversation can be recovered without executing anything. Participants cannot be changed inside a conversation; start a new conversation instead.
- Only that conversation's bounded recent messages and the current agent's curated Live Identity enter the prompt. No private memory, legacy chat, microphone, ElevenLabs, voice synthesis, tools, task creation, publishing or deploy path.

This is the text-first implementation stage. It does not claim the user's eventual multi-voice Party Mode, coordinated audio interruption, general agent tools, or production validation is complete.

## Safety/eligibility

NEXUS_PARTY_MODE_ENABLED defaults to false and only exact `true` in the environment enables it. Existing NEXUS_EXECUTION_ROUTING_ENABLED and NEXUS_LIVE_COST_APPROVED must also be enabled by an authorized operator. No flags were enabled by this change.

The existing execution_runtime adapter still requires a current model/provider capability policy, budget eligibility and an attested restricted OpenCode binary. There is no fallback to unrestricted execution. `party_turn` is a descriptor, not a permission grant.

Every participant must remain active in operational-squad.json, have a valid agent document and pass company/agent ACL. Scope, user eligibility and feature/consumption gates are rechecked before execution and before delivery. Tools are denied for all participants, never unioned into a combined permission set. A fresh temporary directory avoids importing repository configuration or private memory.

Each request advances only its expected speaker index. The durable claim is committed before the external adapter starts. Duplicate start requests with the same text return the original round; conflicting text is rejected. Concurrent or stale next requests never repeat the same speaker or silently advance another. A crash leaves the round running/unconfirmed for manual inspection or cancellation, never automatic replay.

Cancellation stops later turns and suppresses late results. It cannot guarantee immediate termination or refund of an already-started provider call. The UI states this. There are at most three participants and eight user rounds per conversation. The existing adapter may use bounded fallback attempts within a claimed turn, only as allowed by its approved policy. Party Mode itself never replays a claimed turn or starts another round. Existing policy bounds attempts and per-attempt/model budgets; these are not a newly enforced aggregate account/monthly spending cap.

## API and persistence

- GET /api/live/party/options: non-executing readiness flags.
- POST /api/live/party/sessions: companyId + agents; creates an owned empty conversation only.
- GET /api/live/party/sessions?companyId=N: recover latest owned conversation, no auto-resume.
- GET /api/live/party/sessions/ID: owned history and round states.
- POST /api/live/party/sessions/ID/rounds: requestId + text; stores one user round.
- POST /api/live/party/sessions/ID/rounds/ROUND/next: expectedIndex; invokes at most one speaker after durable claim.
- POST /api/live/party/sessions/ID/rounds/ROUND/cancel: empty object; cancellation also works when the feature flag is disabled.

Tables live_party_sessions, live_party_rounds and live_party_messages share the existing owned Live context SQLite database. The existing database backup procedure therefore covers them. No destructive migration is required. Disabling the Party flag preserves history and cancellation.

## Verification commands (offline mocks only)

- python -m pytest tests/backend/test_live_party.py -q
- node qa/party-mode/session-tests.cjs
- cd dashboard/frontend && npm run build
- cd dashboard/frontend && npx --no-install eslint src/live/PartyMode.tsx src/live/party-session.ts src/live/ManagedNexusLive.tsx src/live/LiveChat.tsx

Backend fixtures mock all provider execution. The adapter integration case uses real execution_runtime with a fully mocked low-level CLI. Client tests reject network by default. None of these tests needs API credentials or real provider calls. Do not run broad unrelated suites without reviewing their external-call isolation.

Before enabling in production: independent code review, local browser QA, confirm running image/backup and approved policy/cost bounds, then authorize a small text-only canary. Multi-voice validation is a separate stage. Rollout remains held until the user explicitly releases it.
