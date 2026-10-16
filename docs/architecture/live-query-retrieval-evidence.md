# Live retrieval follow-up: bounded matching excerpts

Base a8ad2c8 (profile fix), itself based on production 8b7e054. Separate branch
fix/live-query-matching-excerpts; no deployment, grants or external/model calls.

## 1. What the two calls prove

Context 9's two read_current_omni_session calls reached response and sent_to_sdk,
without an observed error stage. Audit stores metadata only. It cannot recover
historical output bodies or establish model consumption. See
live-profile-context-evidence.md for sanitized stage times in UTC.

The zero-argument tool is not query-free: `/read` derives up to 200 characters
from the latest persisted user transcript in the bound logical conversation.
The frontend waits for bootstrap and continuity.flush before executing tools.
This orders already queued writes; it cannot prove that a provider transcript
event arrived before a historical tool request. No arguments or company IDs are
accepted from the model by read_current_omni_session.

## 2. Actual source and budget contract

| Response field | Source and selection | Limit |
| --- | --- | --- |
| continuity.current | Same bound logical conversation; current revisions, recent turns | snapshot last 30, selected within 6,000 JSON characters, 600 characters per event |
| continuity.summary | Structured verified/unverified notes among those selected events | not an automatic summary of transcript prose |
| previousWork | Canonical ticket list ACL, exact company; matching descriptions/comments | 3 tickets, 2 matching comments each, 600 characters per excerpt |
| queryResult.memory | SQL ownership user+company before selection, current non-retracted revisions across logical conversations | lexical OR, first 4 terms, 5 results, 600 characters each |
| queryResult.documents | Canonical Recording ACL, current revision and SHA256 | 3 scripts, 600 characters each |

`queryResult.work` is deliberately empty in `/read`: ticket results are already
in previousWork. Explicit `/query` includes work. With no usable terms,
queryResult says query_too_broad; previousWork can show a labelled completed-work
sample. Ticket tokenization uses minimum length 4, memory minimum length 3 and
slightly different stopwords. There is no semantic retrieval, plural expansion,
or guarantee that the first four tokens represent the requested subject.

queryResult is reduced to 4,000 serialized characters by dropping memory first,
then documents. `/read` further trims queryResult memory/documents against a
23,500-character combined budget; if still too large it labels
context_budget_exhausted. These are code limits, not proof truncation occurred
in either historical call. Current continuity marks truncated; intermediate
queryResult trimming does not persist telemetry counts. No result bodies were
logged by this investigation.

## 3. Read-only production findings

The authorized user/company has 51 transcript events in 2 logical conversations,
zero structured notes. Company 1 has 549 tickets. Script references are present
outside the empty Recording/RecordingScript tables:

* 9 ticket title/description matches for roteiro; 37 matching comments.
* 1 description and 2 comments first match roteiro after character 600.
* 2 of those 9 ticket descriptions have at least 1,000 characters. Six have
  external URL references; none has an explicit workspace/ API reference.
* 12 workspace files have roteiro in their name. Only filename metadata was
  inspected; file contents were not read. The one nonempty company project folder
  did not resolve under tested container repository/workspace roots. No canonical
  company link was established for these files. All 549 company tickets have
  null workspace_path and memory_md_path. No file source is added.

References do not prove complete approved scripts. External links remain unopened.
Ticket/company linkage and the existing ticket permission gate authorize ticket
text retrieval; workspace folder-role ACL alone is not a company ownership map.

A current-state replay of lexical matching over the seven most recent user turns
found the question itself among top-five matches in every case. This is a
retrieval-quality limitation, not evidence of historic result emptiness. Events
have sequence numbers but no per-event timestamps. The replay did not print
questions, tokens, personal transcript text or ticket content.

## 4. Proven defect and correction

SQL searched full authorized ticket descriptions/comments and memory event text,
but return serialization always took the first 600 characters. A match after
that boundary could therefore be found and then omitted from the delivered text.
The new pure matching_excerpt helper selects a bounded 600-character window
around the earliest literal case-insensitive query match (up to 120 characters
of preceding context). No-match/title-only matches retain the prefix behavior.
No ACL, source selection, revision, reference, retrieval order, task activation,
media, network fetching or persistence behavior is changed.

Tests put distinct evidence after character 800 in a ticket description, comment
and current memory revision; explicit query and zero-argument read now retain it.
They also assert bounds, original comment reference, exclusion of other tenant/
user data, obsolete and retracted revisions. Literal punctuation, Unicode,
empty/missing text are covered. Validation: 28 passed (2 socket tests deselected)
and the actual loopback HTTP/TypeScript dispatcher test passed separately.
Existing SQLAlchemy Subquery warning remains. No paid calls.

## 5. What remains necessary to prove historical model use

Obtain an authorized read-only provider trace for the exact two tool-call IDs in
conversation conv_6801m51v9vrkf0m885tnyd4hsd3m: chronological user transcript event,
tool request (name/arguments), tool response status/body, and subsequent assistant
utterance. Inspect privately and report only source labels, result counts,
truncation indicators and whether the assistant used the references. Local
metadata audit and timestamp-free SQLite events cannot reconstruct this mapping.
No provider transcript was fetched in this increment.

Next safe check after integrator review: use the local HTTP fixture with long
known source text (already tested); after publication inspect the next naturally
initiated call without starting a paid conversation. Consider separate aggregate
result-count/truncation telemetry and question-self exclusion with ACL tests.
Do not connect the unowned workspace/legacy MemPalace corpus as a shortcut.
