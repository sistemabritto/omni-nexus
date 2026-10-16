# Local voice lookup to private file link in the same chat

Base 96f735f; isolated branch feat/live-file-chat-receipts. This request authorizes
local implementation/tests only: no push, deployment, remote tool/prompt edit,
token/grant change, productive source binding or execution of the rejected
publication action.

## Behavior and boundary

The admin panel is retained for missing source authorization, but is no longer
the result-delivery flow. A final USER transcript containing a file/document/
script/report lookup request queues the existing authenticated local search.
Already-authorized files are searched without asking the owner to bind them
again. No assistant transcript can trigger this path. This deterministic lexical
trigger does not cover all possible natural-language requests; the existing
read_current_omni_session({}) and search_omni_context({query}) paths also create
receipts for matching files. No remote registration is necessary for the local
voice-triggered route and no extra provider/model message is sent.

The client waits for bootstrap and queued transcript persistence, preserves
company/session generation fences, runs scoped HTTP retrieval, and refreshes the
existing saved-event stream. “Resultados e materiais” in the same conversation
then contains an excerpt and “Abrir arquivo”. This link opens a new tab so the
voice session is not navigated away. It is not a public share or bearer token.
No claim is made that a remote model spoke or used the file contents.

## Authorized sources and ambiguity

* Current explicit Workspace bindings for this authenticated user/company,
  intersected with current folder/path permission and reviewed digest/revision.
* Current RecordingScript revisions through the existing user/company Recording
  ACL, without requiring a redundant Workspace confirmation. No media or external
  references are opened. A common conservative text/credential/size filter also
  protects receipt-readable script content.
* Generic “quais arquivos/documentos?” lists only current authorized Workspace
  sources (bounded to three), without prompting when one source is sufficient.
  Named/subject queries remain lexical; multiple matching results have distinct
  source titles/links instead of an arbitrary selection. No-match status asks for
  a name/subject; no authorized source directs to the existing minimal ownership
  confirmation panel. No unowned filename, path, corpus or folder is discovered
  to guess its company.

No project-folder/share pointer becomes an ownership grant. No other user's or
company's files, private global memory, secret-like source content or public share
is added. The existing source caps and context budgets remain; receipts expose at
most three stable result references. File lookup never activates a task or queue.

## Persistence, authorization and revision

One additive lazy table live_file_receipts in the existing private context SQLite
stores ID, user/company, logical conversation, source kind/ID/revision/digest,
bounded search terms and creation time. No body/excerpt is cached there. A unique
source/version/conversation key makes retries return the same receipt. A result
event persists only receipt metadata and generic text; its excerpt/link are
reconstructed through current source authorization when events/context are read.
Source confidentiality is therefore not frozen into a stale event snapshot.

GET /api/live/file-results/{receiptId} requires the existing active configured
personal administrator cookie, active company, source user/company ownership,
current source ACL and exact current digest/revision. It remains valid across
reconnects to the owned logical conversation and does not depend on an expiring
provider URL. Unknown/revoked/moved/changed sources return unavailable. A changed
or revoked source also hides its cached chat event/link on rehydration. Original
source identity and SHA256/source revision remain in the receipt/tool result.
The response is text/plain, no-store, nosniff, with a sandbox CSP; HTML is never
executed. Raw Workspace paths cannot be supplied to this receipt reader.

## Verification

Authenticated temporary SQLite and real Flask/HTTP fixtures exercise:
voice user_transcript -> saved user turn -> local search -> metadata receipt ->
persistent result event -> actual TS ManagedSession state -> same-origin private
GET. No provider tool request is injected to make this succeed. The fixture
asserts bootstrap is the only contextual_update, no extra model invocation,
assistant lookup wording does not trigger search, and an unbound file is absent.

Other cases cover retry/dedup, fresh-context rehydration, absence of cached source
body, changed digest, binding revocation, foreign company/user, anonymous link,
existing Recording ACL without new confirmation and Recording company movement.
A generic-file request lists only authorized current sources. The real React chat
component is rendered with safeWorkLink to prove the result anchor, new-tab
behavior and rejection of an external link. No new browser/UI design or build is
needed for this small change to the existing result component.

Validation results and any transient failures are appended below after completion.
Graphify AST update is local only; generated graph artifacts are not software
changes. All receipts and source bindings made by tests use temporary fixtures.
Productive activation/publication is explicitly outside this request.

Validation: the broad run had 70 passed / 3 failures because the pre-existing
continuity-provider harness rejected the new PURE file-lookup module import.
The allowlist now permits that local module while retaining the provider-SDK
prohibition. Continuity endpoints + receipt tests then passed together (15).
The real chat render and playback regression tests passed (2 tests, including
all 12 audio/order/interruption/lifecycle checks). No-emit TypeScript passed.
The secret-like recording test passed without returning body/receipt. Existing
SQLAlchemy Subquery warning remains. These counts overlap; they are not claimed
as a single full green CI run. The CI test list now includes the receipt module;
no CI push/run or publication was initiated.

The raw audio event_id, interruption watermark and SDK drain listener were not
edited. Result-panel refresh failure is best-effort after a successful tool
result and cannot discard that result. Opening a result is a private new-tab
text response; no remote execution, public share or media fetch is involved.
