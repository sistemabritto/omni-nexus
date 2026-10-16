# Queue revalidation: proposal only

No ticket mutation is authorized or implemented by this tool. `scripts/queue_revalidation_dryrun.py` opens SQLite with mode=ro and query_only=ON, has NO --apply option and emits deterministic proposals for ten individually audited historical cases. It never invokes an agent, scheduler, publication, network sender or model. Repeating it does not change timestamps/events/ownership/state.

The production dry-run is retained at `evidence/queue-revalidation-dryrun-2026-10-16.json`. This is evidence and a plan requiring review, not an approved migration. If the user later authorizes changes, a separate implementation must recheck the full expected state and evidence; this file is not an execution token.

|IDs|Observed|Proposed diagnostic only|Unchanged|
|---|---|---|---|
|de0fac29,8aa7bb62,c9ce0445,6651faa4,689037b5|Latest comment says Nex offline, enabled nex-sales-4h exists; no deliverable proven|needs_current_funnel_evidence|blocked, Nex owner, approvals, jobs|
|c6851c4a,e16320ff,8717ebe0|Goals11/12/9 decomposition rejected; local site code exists but task deployment/acceptance unproven|scope_review_required|blocked, Bolt owner, rejected decomposition|
|e63b4871|Internal annual model artifact exists; explicitly depends on Sprint5 evidence, Felipe and Lex|commercial_decision_required|blocked, Mako owner, commercial decisions|
|5de37020|Previously moved to human review, no automated owner|NO proposal; explicit decision only|all fields|

Ownership is evidence, not automatically repaired: no assignment is proposed. Unknown or ambiguous ticket identity, changed status, lock or human gate yields no proposal. A disabled Nex heartbeat cannot produce an obsolete-offline recommendation. No campaign/isca21/Instagram draft, CRM403, ACL/grant or credential is in this manifest.

## Future runtime diagnostic correction

The invalid-publication-target path in heartbeat_outcome now records `publish_context_missing` instead of generic `agent_blocked`, and explains that internal work needs an explicit publish_intent=false while external publication needs valid context and human approval. The fail-closed branch is otherwise unchanged: blocked status, no approval dispatch for invalid target, no publication. Missing intent is NOT inferred false. Existing blocked rows are not backfilled. This diagnostic patch is local until the sole integrator reviews/deploys it.

No change or rollback of the earlier5de37020 administrative transition is attempted. Review is not completion; its sources/baseline/keyword split remain for human decision.

Validation:37 tests passed across dry-run/read-only/idempotency, invalid owner-state/gates, unsupported --apply, publication/decomposition fail-closed tests, publish-gate reachability and blocked-reason preservation. Existing SQLAlchemy deprecation warnings only. Real dry-run returned nine diagnostic proposals and one protected case; zero changes were applied.


## Independent integration review

The initial independent reproduction passed 23 tests (dry-run + decomposition);
the author's 37-test count also includes publish-gate and reason-persistence
suites. Review found that locked_by without locked_at could still emit a
proposal. The generator now treats either lock field as a stop condition and
records both in expected state; regression covers a worker lock with missing
timestamp. This does not implement any apply path or change tickets. The new
read-only suite is explicitly included in CI.

The included initial JSON snapshot predates that expected-state enhancement;
it is historical evidence, never an execution token. A refreshed read-only
manifest must carry both lock fields before review of any future change.
Only the dashboard heartbeat runner executes heartbeat_outcome in the
currently deployed service topology; scheduler/Telegram/worker images and all
Live fields/flags are preserved by this independent diagnostic rollout.

Independent final suite: 38 passed across the four suites above, including the
new lock-owner regression, with existing SQLAlchemy deprecation warnings only.
The 23-test initial reproduction was a subset, not a contradiction of the
author's 37-case run. No production ticket changes are part of the release.
