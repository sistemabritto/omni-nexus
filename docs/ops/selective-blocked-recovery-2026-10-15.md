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

## Read-only follow-up: isca15 and sweep

Follow-up probes used the dashboard runtime's own `/workspace/.venv/bin/python`, authenticated GET and a psycopg2 session with readonly=True. No resources were created or modified and no public tracking URL was visited.

Isca15 material `workspace/social/[C]isca15-publicar-validacao.html` exists (5966 bytes); its execution checklist also exists. GET `/api/shares/by-path` returns 200 for that exact path, enabled=true and expires_at=null. API token configuration, PostgreSQL configuration and psycopg2 are present; SELECT 1 succeeds. The historical claim that only Felipe has the token/access is obsolete in the currently probed dashboard runtime. This validates the PR43 preflight direction, not a causal claim that PR43 created those resources.

Exactly one Automation matches keyword 15: active=true, pendingNextReel=false, matchAnyPost=false, postId present. It has no associated TrackedLink, and its dmMessage does not contain the existing isca15 share token. Thus keyword existence does not satisfy the ticket's requested destination/tracking contract. Do not INSERT a duplicate campaign or mark the ticket complete. Next executable step is a read-only comparison of the existing campaign's workspace/account/post identity and intended approved isca15 campaign identity against the checklist, producing a proposed reconciliation diff for human/integrator review. Changing an already active campaign would affect a real external flow and remains unauthorized in this investigation.

The 50 sweep-marked tickets are 40 pixel-social-media, 2 bolt-executor, 2 hawk-debugger, 1 dex-data, 1 nex-sales and 4 unassigned. Sweep events span multiple dates, not one single outage. Runtime threshold is 60 minutes. Since Oct 1, pixel has 414 successful runs, 12 timeouts, 16 busy; bolt 1388 successful, hawk 694 successful, nex 89 successful/1 busy. These are agent-level correlations only: success can mean skip, and a timeout does not prove loss of any particular ticket's work. The marker records an inactivity classification; it neither deletes artifacts nor establishes a common root cause for all 50.

Concrete false-inactivity evidence: ticket df371ba3-567d-4dd7-bbae-9bf8783c946c has an admin comment at 2026-09-24T06:15:03.621412Z and sweep_to_blocked at 06:30:59.092030Z (about 16 minutes later). The comment endpoint did not refresh tickets.updated_at, contrary to the sweep's documented last-touch semantics. Patch makes comments refresh updated_at; a regression test posts a comment and verifies the ticket no longer qualifies for the 60-minute sweep. No historical rows are changed.

A separate code-level race is reproducible: after selecting an old unlocked in_progress ticket, another worker can touch it, lock it or move it to review; the old UPDATE checked status only and still blocked touched/locked tickets, or logged phantom events after status changed. Patch atomically rechecks selected updated_at and locked_at IS NULL and records/counts only successful transitions. Four local regression cases cover touch, lock, review transition and a genuine stale ticket. Historical occurrence of this race has not been proven.

OpenCode/Adrael/Drael and Claude Code were not invoked; no model review is claimed and no global model configuration was changed.

Follow-up validation: 57 tests passed (ticket API suite, sweep race regression, blocked metadata, publication gate and runtime preflight); only existing SQLAlchemy legacy API warnings.
