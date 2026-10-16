# Live experience integration

Production base: 74d993d1da8498f8eeddde1781a47c266cb887f5.
Included increments only: c34823554610b137582c883f95632e7852456ebc and
0be5e1588b90975092df54846ba367308151491e. CI conflict resolved by retaining both
the OpenCode model regression and new receipt tests. PR90 and PR91 are excluded.
Only dashboard needs a new image; no worker/scheduler transport is introduced.

Final user transcript lookup searches existing authorized sources through local
HTTP, persists a metadata receipt/result and refreshes the same chat. It adds no
provider input/tool registration or model call. Private links revalidate current
user/company/source ACL/revision/hash; source changes/revocation hide old events.
Voice UI prioritizes controls/composer/results, with context, transcript, sources,
voice preferences and administrative file configuration disclosed on demand.

## Executed verification

- 49 targeted Python tests passed: receipts, file source ACL/hash/revocation,
  Recording source ACL, continuity endpoints, playback regressions and OpenCode
  model configuration. Includes real temporary Flask/SQLite/HTTP with TS
  dispatcher, synthetic final user transcript and SDK/audio simulated. No paid
  call or production binding is used; this does not prove a real voice conversation.
- Presenter SSR, host SSR (admin/viewer), integrated controller bindings,
  session/continuity and private receipt anchor render passed. External links
  rejected; private link opens a new tab with noopener/noreferrer.
- Full application TypeScript noEmit and scoped ESLint passed using existing
  dependencies; no local installation or heavy production build.
- CI includes the new backend receipt test and SSR/integrated UI fixtures.

## Visual QA remains NOT TESTED

Read project UI UX Pro Max and design-quality/UX heuristics, plus installed
UI/UX Pro Max. Search results were not treated as a new brand/design system.
Current Chrome launch again failed before any page: crashpad socket.cc:45,
setsockopt Operation not permitted, SIGTRAP. No screenshot, browser interaction,
computed contrast, keyboard traversal, zoom or physical overflow measurement was
produced for 360x800, 375x800 or 1440x900. The earlier in-app file:// refusal was
not retried via another surface or permissions. SSR/CSS is not browser QA.
The user's publication request explicitly followed disclosure of that earlier
block; publication does not turn these missing checks into PASS. The prepared
browser script still needs a permitted environment and visual review.

## Production and rollback safeguards

Publish/build exact integration SHA and immutable digest via GitHub Actions,
require CI and isolated image smoke. Stage only dashboard, then check no active
Live/agent sessions/jobs/locks/executors before backup/update. Preserve current
providers.json URL/key/models and ENV byte hashes, roles, heartbeat enablement,
ticket state, sessions and data. Continuity stays on, Live tasks stay off.
No OmniRoute, ElevenLabs agent, credentials or global harness defaults change.
Rollback changes dashboard image to 74d993d, retaining current ENV/config/data.
The additive lazy receipt table may remain; older UI hides unsupported links and
older backend reauthorizes/retracts unsupported event references. Do not restore
an old DB or erase receipts as a routine software rollback.

## User screenshot, separate from Live acceptance

A supplied PNG was materialized through Library into this executor and its pixels
inspected. It shows /agents/oracle with a reply, not Live or a connection error.
The visible reply includes English reasoning and claims simulated file inspection
before offering initial setup; it does not prove actual filesystem/tool execution.
Felipe confirmed the agent chat ping worked; Live acceptance remains outstanding.
The private screenshot and transfer URL are not included in the repository.
