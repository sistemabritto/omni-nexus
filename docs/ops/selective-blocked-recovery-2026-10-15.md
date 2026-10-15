# Selective blocked-ticket recovery audit

Read-only production snapshot: 2026-10-15 12:17 UTC, SQLite URI mode=ro and PRAGMA query_only=ON. No task, approval, credential, publication or deployment was changed.

## Counts

91 blocked; 3 review; 411 resolved; 44 closed. Ticket 677838b4-09f2-43d7-a8b3-ea79e5ca74b0 remains review, not completed.

Blocked metadata: 37 NULL reasons; 50 `Sem avanço desde in_progress (zumbi detectado pelo sweep)`; 3 `agent_blocked`; 1 `review_exhausted`. All 91 currently have requires_human_approval=0. This flag is not evidence of authorization: comments and associated goal decisions still matter. Approval status counts: 74 approved, 128 expired, 268 published, 23 rejected; no pending rows in this snapshot.

Overlapping keyword signals in the latest three comments per blocked ticket: 2 Cloudflare/403, 61 approval/decision/authorization, 20 runtime/credential terms, 41 material/link/file/destination, 5 repository/checkout terms. These are search signals, not mutually exclusive causal diagnoses or authorization decisions.

## Correctable defect

`apply_outcome(action=blocked)` persisted status and explanatory comment but omitted machine-readable blocked_reason. Other blocking paths persist agent_blocked, pending_human_approval or review_exhausted. New ordinary blocked outcomes now receive agent_blocked only when no reason exists. Existing reasons and human-approval fields remain untouched. No historical backfill: NULL does not imply agent failure or eligibility for recovery.

Validation: 20 tests passed across blocked-reason persistence, publication gate reachability and runtime preflight. Six regression cases cover NULL/empty/whitespace and preservation of approval, exhausted-review and external-dependency reasons, comment evidence and approval fields.

## Separation of blockers and next safe case

- Cloudflare 403 remains an external access boundary. Do not bypass it or mark its tickets recovered.
- `review_exhausted` requires inspection of review evidence. No automatic reset.
- 50 sweep markers describe inactivity, not the underlying cause; inspect each history before reopening.
- Ticket 8717ebe0 (quiz): latest history reports missing source checkout; prior history records rejected decomposition and asks for a human scope decision. Do not infer permission from its zero approval flag.
- Best next bounded recovery investigation: c954817e-f399-44f3-b669-8316cf257622 (isca 15). Its history alleges absent SSH, DB credentials and Nexus admin token. PR43 preflight addresses these runtime assumptions. Recheck configuration booleans using the actual runtime interpreter and authorized read-only API/SELECT 1. Then verify that the requested source material and destination exist. Do not create a share, insert/activate a campaign, mint a token or publish during this probe. Only consider one-ticket recovery after evidence resolves every dependency and the integrator checks scope.
- First close the evidence loop on 677838b4 through review; review is not completion.

Patch base is production branch deploy/recovery-safe-drafts at 4001bf6, not origin/main (which lacks PR43). Integration/deploy belongs exclusively to executive thread 01a13c9a-dd49-73a0-a0fc-87b82fb29016. No OpenCode or Claude Code invocation was needed; no model alias/global configuration was modified.
