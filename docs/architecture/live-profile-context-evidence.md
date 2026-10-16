# Authenticated profile context and voice-call evidence

Base: 8b7e054. Isolated branch: fix/live-authenticated-profile-context.

## Proven omission and correction

`read_context` returned company, runtime, tasks and optional continuity, but no
profile name. Read-only production SQL identified active user 1 with display_name
Felipe (username admin). The response now adds only `authenticatedUser` with
`displayName` (trimmed, capped at 120 characters), `nameAvailable` and
`source: authenticated_profile`, taken from Flask-Login current_user after the
existing ownership and company guards. Blank names remain unavailable; usernames
are not inferred as personal names. This works with continuity disabled too.
No email, role, password, requested user selector or global memory is serialized.

## Sanitized observation: 2026-10-16 07:54–07:58 UTC

Read-only production inspection on revision 8b7e054: context 9, user 1,
company 1. Two read_current_omni_session calls completed these audit stages:

| Tool-call suffix | received | response | sent_to_sdk |
| --- | --- | --- | --- |
| 944c3803 | 07:55:27.022 | 07:55:30.146 | 07:55:30.565 |
| e9819f71 | 07:56:19.342 | 07:56:21.479 | 07:56:21.867 |

Both also have dispatch and send_attempt; no error/cancel stage was observed.
Access logs in 07:54–07:59 show 11 audit POSTs HTTP 200 and 3 context read POSTs
HTTP 200. sent_to_sdk records local SDK submission, not provider acknowledgement
or proof the model used the result. Audit intentionally contains no payload, so
historical result emptiness/content cannot be reconstructed from these rows.

## Source coverage, not an inferred failure cause

At inspection, production had zero recordings and zero recording_scripts.
The connected current-revision/hash recording-script source therefore had no
scripts to return. This does not establish that no scripts exist in files or
other systems. The authorized user/company continuity store had 2 logical
conversations and 51 transcript events, with zero structured fact/decision/
preference/pending notes. Company 1 had 549 tickets. Thus absence of all history
or work data is false; these inventory counts do not prove a particular query
matched or was delivered during either call.

Workspace files are not a connected query source. Knowledge connections have no
proven company mapping. Legacy MemPalace corpus lacks the necessary ownership
scope and remains excluded. Do not infer company-to-Knowledge access or import a
global corpus. Existing history retrieval is bounded lexical retrieval, not a
semantic guarantee. Profile repair does not add those missing sources.

## Validation and next verification

Tests exercise the actual Flask read route with authenticated sessions and a
stub runtime: correct profile, unavailable blank name, no username fallback,
no sensitive profile fields, rejected user override and denied other user.
Existing continuity, recording ACL/revision and metadata audit tests are run as
regressions. No provider/model/voice call, deployment, remote configuration,
grant, data migration or task activation is part of this change.

After integrator review and software publication, verify an authenticated read
returns Felipe, then inspect the next naturally initiated call's tool audit.
To determine result emptiness prospectively, design bounded aggregate result
counts per tool phase separately; do not log query text or retrieved content.
A future file source needs an explicit canonical company/user ACL before wiring.

Validation result: regression run 30 passed / 1 timed out in the existing
HTTP audit rejection harness; that exact case passed alone (1 passed, 6.40s).
Two new profile tests passed. Initial sandbox run lacked the existing TypeScript
module path and loopback permission; the subsequent run supplied both without
installing dependencies. Existing SQLAlchemy Subquery warning remains.


## Independent integration review

Integrated separately after squad revision 4985996, together with the authorized
matching-excerpt correction 06f6285. No remote prompt, model, voice, audio,
grants, task flags or company ownership changes are included.

The original 31-test profile/continuity/audit regression passed (62.15s); the
previously timed-out reject-received case also passed alone (4.31s), without
increasing timeouts. The expanded 37-test union initially had 3 tool-timeout
failures in the local HTTP fixture. That fixture used a serial Werkzeug server
while browser bootstrap/events/audit/source fetches are concurrent. Both HTTP
fixtures now use threaded=True; all tool/subprocess limits remain unchanged.
The expanded suite then passed all 37 cases in 30.77s. This is a fixture change,
not a relaxation of production audit timeouts or a claim of provider reliability.

The real loopback HTTP/Flask/SQLite/TypeScript dispatcher scenario also asserts
the isolated authenticated profile reaches the simulated SDK tool result. It
uses fixture data, no production cookies, provider or microphone. Production
software packaging and protected-route checks do not replace a natural signed-in
user call or prove the model used the new field.

A subsequent repeated run exposed a second fixture issue: SQLite InterfaceError
in a concurrent scope lookup. The fixture used sqlite:// (one shared in-memory
StaticPool connection). The ephemeral dashboard fixture now uses a per-test
SQLite file, matching production's connection model; HTTP server concurrency
and original timeouts are retained. No production DB/config change is made.

Final file-backed fixture validation: 37 passed, 12 existing SQLAlchemy warnings,
95.79s under local load. The authenticated fixture name was asserted in the SDK
result through real loopback HTTP and the TypeScript dispatcher. The earlier
failed repeats remain documented; they are not counted as successful runs.


## Final authorized Live union

This release additionally includes f8b78ed (shared lexical policy, ranking before
the candidate cap and exclusion of the exact current-question event), plus
f94700c/231815d evidence/test clarifications. User/company SQL ownership, current
revision, revocation checks and result budgets remain in place. The last saved
assistant announcement is not used as the user query. This is lexical retrieval,
not semantic search or proof that the requested complete script exists.

Independent final validation: 50 passed, 14 existing SQLAlchemy warnings, 74.90s,
covering context, continuity, recording ACL, audit outage/timeout, query and
conversation-store isolation/ranking. One earlier 49-pass/1-fail run lacked the
local terminal express dependency after the integrator removed its symlink;
the link to already installed packages was restored (no installation), then the
full 50-case suite passed. No failing run is represented as passing.

Raw managed-session.ts, audio.ts and tool-dispatch-audit.ts are byte-for-byte
unchanged from 4985996. No remote configuration or real provider call is needed
to validate this software release. Production model consumption remains a
separate, naturally initiated user-call verification.
