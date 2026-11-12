# Ticket event wiring v1 — local review delta

Baseline: `0af9f4a149db3695ba8f8852d5f1aa395714f27e`. Branch `fix/ticket-event-wiring`. No production activation, migration, replay, provider calls or canaries were performed by this work. EDIT07 original and editorial-v2 are excluded by the existing restricted-ticket guard; neither is read or overwritten by this feature.

## Existing behavior and reproduced gaps

- Ticket create/update/comment, checkout token/release and Kanban outcomes already exist. Mentions already insert heartbeat triggers; a 15-second dispatcher poller passes their payload to the runner. This is not a missing agent installation.
- The old drain submits disabled heartbeats and ignores configured wake types. Simulated executor rejection consumes the event and leaks its in-memory slot. Existing four dispatcher tests passed despite both reproductions.
- The old comment path commits before enqueue, trusts caller-provided author labels, has random event IDs, no company-bound context or retry/loop bound. New-task hook has no callers in create/assignment routes.
- Generic runner acquires a chosen ticket **after** inference. Its mention prompt contains a token-printing troubleshooting instruction. Generic review can call another model and resolve work automatically. v1 event runs use a separate, evidence-bound result path and never invoke that review pipeline.

## Implemented interface

`ticket_wake_contract.py` is the source for envelope creation, revalidation, work leases and observed receipts. Existing tables only; no new actor IDs/personas, tables, grants, owners or credentials.

Envelope `schema=ticket-wake-v1`: `event_id` (deterministic UUID), `kind` (`mention` or `new_task`), `source_id` (comment or change), `actor_user_id` (authenticated principal), `recipient` (stable persona slug), `company_id`, `ticket_id`, `ticket_version` (`tickets.updated_at`), `owner`, `mission_id`, `project_id`, `goal_id`, `task_id` (legacy reference only), `status`, `depth=0`, `max_depth=0`, `requires_ack=true`, `ownership_changed=false`, `evidence=[]`, `publication_approved=false`.

Actual hierarchy is Mission → GoalProject (`projects`) → Goal → Ticket. Missions have no `company_id`; company isolation is checked on ticket and project, with goal→project and project→mission consistency. No goal_tasks creation or decomposition is introduced.

- Gate `TICKET_EVENT_WAKES_ENABLED=1` is **absent/off by default**; pending mention/new-task rows are preserved while off. Do not enable as a consequence of merging. No configuration was changed here.
- v1 origin requires a browser-authenticated, active admin. This matches the existing global admin ACL; there is no per-company membership ACL in the application. Recipient must be a known persona with exactly one enabled, non-handler heartbeat explicitly accepting that wake type. Approved aliases (Dante/Íris/Argos etc.) map to existing stable IDs, with max three unique mentions and email/partial-match exclusion.
- Shared bearer token requests can still post authorized comments, but cannot originate automatic wakes or claim an agent identity. The displayed author becomes the authenticated human/service principal; declared author is diagnostic metadata. Agent→agent chaining is deliberately unsupported (`max_depth=0`). The shared token does not prove which agent is calling; prompts cannot repair that boundary.
- Create and real assignment/status changes queue new-task events; no-op patches do not. Comment and trigger enqueue share one transaction. `Idempotency-Key` on comments gives replay of the same comment (200), conflict on changed body (409). `X-Ticket-Version` rejects a new stale response (409); an already committed idempotent replay still succeeds. Event identity is per source event, not fuzzy deduplication of separate human requests.
- Dispatcher rechecks enabled/wake types, current admin status, active company, relationship IDs/version, owner and human approval gates. Legacy mention/new-task events without authenticated envelope are consumed with an explicit rejection diagnostic, never upgraded to trusted authorization. There is no bulk replay facility.
- Admission reserves a deterministic run row plus trigger in a SQLite write transaction. One running event per **agent** across heartbeat IDs, at most four durable running rows globally. Existing stale running rows count as capacity; no silent deletion. Legacy/manual/interval admission is not rewritten here, so its independent admissions can still consume capacity outside this event limit.
- Executor submission failure before invocation releases the reservation and retries after 30/60 seconds, max three admission attempts (third failure is terminal). A reservation not started in 60 seconds can be reconciled through that same bounded path. Callback CAS prevents duplicate invocation. After invocation, uncertain state is retained for reconciliation, never automatically replayed. Existing provider fallback semantics remain; there is no claim of exactly-once external effects.
- New-task event gets a controller-owned, token-bound ticket lease **before** inference, with owner/company/version/status/gate CAS. Release matches the exact token; it cannot release a replacement lease. Mention feedback does not acquire the producer's lock or transfer ownership.
- Event runner sees only the event ticket in its inbox, the real goal chain and the bound IDs/version. No outer inference retry. Outcome may move its leased ticket to in_progress/review/blocked; no resolved/closed, human approval or publication. Work status CAS also requires the original ticket version; a mid-run edit invalidates the transition. Work requires 1–10 local files under workspace, actual SHA256 and bounded size; mismatched/absent evidence causes failure without a Kanban transition. Mentions require an actually persisted, idempotency-correlated reply comment. Returned receipts carry event/run/ticket/version/evidence, owner unchanged, independent acknowledgement not recorded. These facts are not an Argos/Oath verdict.

## Operational boundaries and remaining rollout blockers

This delta is not a general queue enablement. Runtime tools still inherit the shared dashboard service credential and existing globally scoped ticket routes. The event context and result CAS prevent controller-side cross-ticket moves, but **do not sandbox all tool-initiated writes**. Before general automated agent edits/pulls/chaining, add authenticated run-bound capabilities at the API boundary, protect all create/update/checkout/bulk/comment paths, and verify revocation/tenant isolation with hostile tool requests. Do not label this v1 as complete per-agent ACL enforcement.

Routines remain the existing configured interval/manual heartbeats. This work reconciles only abandoned pre-invocation event reservations; it does not schedule every open ticket, repair uncertain running processes blindly or add unrelated external heartbeats. Fully replacing legacy routine admission, autonomous task creation/pulling, reviewer-pool selection/excluding contributors, and two correction cycles then human escalation belong to subsequent reviewed deltas. The Squad policy may describe those requirements, but must not claim them already executed by this dispatcher.

A later E2E can use exactly one existing authorized ticket after Squad completion and integrator review, with fresh version/ACL/capacity CAS and explicit inference authorization. Do not reuse protected EDIT07 or create a copy merely to demonstrate execution. No canary is authorized by this document.

## Local validation

- Baseline dispatcher suite: 4 passed; two additional temporary-DB reproductions demonstrated disabled dispatch and event/slot loss on submit failure.
- Regression group (ticket API, runner, dispatcher and event wiring): 82 passed.
- Latest focused event-wiring pass: 28 passed; two additional targeted checks passed for handler replacement and actor revocation before result. These exercise real Flask routes, SQLite transactions and actual local evidence files with the provider/executor mocked. No claim of a real model run or production delivery.
- AST-only `graphify update .` was run; generated graph files remain outside the change. Existing SQL parser dependency warning is unrelated; no dependency installation or semantic/LLM labeling was performed.
