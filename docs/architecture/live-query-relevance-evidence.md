# Derived query relevance and question-echo correction

Separate increment on 06f6285, branch fix/live-query-relevance. No remote tool,
prompt, greeting, grant, database schema or provider configuration change.

## 1. Evidence and causal boundary

Coordinator supplied the native ElevenLabs review for conversation
conv_6801m51v9vrkf0m885tnyd4hsd3m (2026-10-16 07:54:53–07:57:27 UTC): two
read_current_omni_session({}) results, 12,394 and 13,778 characters, no error or
global JSON truncation. On the script question, documents.results was empty;
queryResult.memory held the current question plus four assistant greetings/
limitations, and continuity held ten events with empty structured summary arrays.
Later helper/file questions made no fresh tool call despite consultation wording.
This is provider-side result evidence supplied by the reviewer, beyond the local
sent_to_sdk marker. No remote conversation was fetched by this increment.

Read-only scoped SQLite replay identified the script question at sequence 55.
Its 83-character text contains roteiro, but the released memory AND ticket term
extractors fill their four slots before reaching it. Question text and generic
scaffolding tokens were not printed. At sequence <=55, the old memory policy
reproduces exactly five hits: question itself plus four assistant transcripts;
only the question contains roteiro. The first-four-term cutoff and question echo
are therefore demonstrated retrieval defects, not an inference of model misuse.

## 2. Comparative read-only replay

Both policies operate only on user 1/company 1, current non-retracted revisions.
Memory replay bounds sequences at 55; ticket replay reads CURRENT rows because no
historical ticket/result snapshot exists. It must not be called the exact
historical previousWork payload.

| Aggregate | Released policy | Proposed policy |
| --- | --- | --- |
| Selected terms | 4 | 4 |
| Retains roteiro | no | yes |
| Memory results at sequence 55 | 5 | 0 |
| Includes current question | yes | no |
| Assistant transcript results | 4 | 0 |
| Current ticket results | 3 | 3 |
| Tickets with roteiro in title/description | 0 | 2 |
| Selected comment prefixes with roteiro | 0 | 4 |

The empty proposed memory is an honest absence of prior matching content at that
point, not a failed retrieval. Ticket references/comments are evidence about
scripts, not proof a complete current approved script exists for today. There
remain 9 ticket title/description and 37 comment matches for roteiro in company 1;
RecordingScript remains empty. No workspace file or external reference is opened.

The coordinator's final native JSON review confirmed previousWork.results had
3 resolved tickets and 4 comments about channel/offer planning, social publishing
routine and WhatsApp report diagnostics. None was the requested script. This is
observed historical payload evidence, separate from the CURRENT ticket replay.
queryResult.work.results was empty, as expected because /read places tickets in
previousWork; documents was available with empty results. Neither field alone
establishes absence of scripts across other authorized sources.

The provider payload contains neither the query nor derived terms, and the tool
request was {}. Exact term selection therefore comes from the local code/SQLite
reproduction, not an ElevenLabs query log. The native report confirms irrelevant
ticket delivery; the reproduction explains the demonstrated term-loss mechanism.

## 3. Implementation

* One pure deterministic query_terms policy now serves memory, tickets/comments
  and current recording scripts. It drops conversational/temporal scaffolding,
  gives explicit source nouns priority before the four-term cap, and normalizes
  a small documented set of source-noun plurals (including roteiros -> roteiro).
  This is bounded lexical retrieval, not semantic search or general stemming.
  Subject priority vocabulary lives in live_query_terms.py and can be reviewed.
* Only derived /read excludes the triggering question, using the exact logical
  conversation/event pair resolved by the server. No model-selected exclusion or
  tenant override is accepted. Explicit /query keeps its existing contract.
* Memory SQL ranks distinct matched-term count before the 100-candidate cutoff,
  then verified status, user transcript preference at ties, then sequence. Thus
  100 newer one-term assistant turns cannot hide an older two-term source.
  Assistant transcript content remains eligible (it may contain real scripts);
  ranking does not certify it as fact. Existing untrusted/verified labels remain.
* SQL still selects authenticated user/company and only current non-retracted
  revisions; per-conversation authorization is rechecked before return. Source
  references, excerpt limits, 5-result limit and context budgets stay unchanged.

No automatic query tool registration, remote alias, corpus import, tasks, file
ACL expansion, grants or source ownership migration occurs. The no-argument tool
still derives a query from the latest SAVED user turn; it cannot force a future
provider transcript event to arrive or force the model to call again. The later
false consultation wording is outside the proven backend retrieval correction.

## 4. Verification

Comparative fixture: old first-four extractor drops roteiro; new extractor keeps
roteiro/vídeo. A current approved revision outranks four generic assistant turns;
the triggering question, obsolete revision and retracted revision stay out.
Tickets use the same subject terms; empty RecordingScript stays explicitly empty.
A separate fixture proves no invented history when only the current question
matches. Store test covers >100 newer distractors, exact-pair exclusion, foreign
user isolation and revoked conversation ACL. Existing tests also cover company
isolation, bounds and long matching excerpts. No provider call is used.

Executed validation: 42 regression tests passed, including actual loopback HTTP /
TypeScript dispatcher, continuity reconnect and recording ACL/revision checks.
The additional no-prior-history test passed separately (1). Existing SQLAlchemy
Subquery warning remains. Initial read-only replay script had a quoting syntax
error before running SQL; corrected script produced the aggregates above.
Graphify AST-only update runs locally; generated graph artifacts stay outside
this software commit. No dependency installation or paid inference.

Follow-up role check: `_query_for_current_turn` and `_previous_work_for_context`
select only transcript events with server-persisted `browser:user:` sources.
The comparative test now saves an assistant lookup announcement AFTER the user
question and still retrieves the approved script-topic memory and ticket from
the user query, excluding the question itself. Focused rerun passed (1, 2.47s).
No functional code change was needed for this observation.
