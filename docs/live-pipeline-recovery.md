# Live autonomy and pipeline recovery

## Scope and defaults

This package strengthens the existing Live GitHub job executor. It does not
enable rollout, grant token permissions, add an unattended correction loop,
restart the scheduler, migrate historical queue tasks, or contact providers.
`config/live-self-healing.json` remains unchanged with `rollout.enabled: false`.
Existing GitHub, workspace, company, user, and agent authorization remains
required. Mutating adapters still need exact human approval even in YOLO mode.
Only Bolt and Hawk can use the commit adapter, only on non-protected work
branches. Protected files, deletion and force pushes remain prohibited.

The adapter catalog now describes these application gates separately from
credential health. A configured credential or eligible agent is not proof that
an operation is authorized or that production rollout is ready.

## Execution boundaries

An approved job is stored encrypted and claimed once with a SQLite transaction.
Before execution, its persisted principal must match the thread's principal.
The worker then reruns the complete proposal validation: agent, repository,
branch, files, exact base SHA, workflow and policy proof. Every outbound operation
rechecks the active user, company, agent, repository allowlist, and the approved
workspace/GitHub/pipeline policy digests. A change fails closed instead of
silently applying the old approval to a new scope.

An existing request ID cannot silently adopt a different agent or proposal.
Concurrent workers cannot claim the same pending job twice. A worker's final
write cannot overwrite terminal evidence already recorded by a status reader.
These guarantees do not imply a distributed transaction with GitHub.

CI still dispatches by branch ref. The branch can move between the head check
and GitHub admitting the run. The existing CI workflow does not enforce an
`expected_sha` at runner admission, so this package does not guarantee exact-SHA
dispatch: its observer rejects a mismatched run afterward. A future stronger
CI dispatch protocol needs separate review before autonomy activation. The
existing rollout workflow's `expected_sha` enforcement is preserved, with
rollout still OFF.

## Observation-only recovery

`github/status` is the recovery entry point. It never sends a GitHub mutation
and never starts or restarts a worker.

- Commit jobs checkpoint the returned commit SHA before updating a branch ref.
  A lost response or interrupted worker can be reconciled only when that branch
  now points to the exact checkpointed SHA. A changed branch or missing checkpoint
  stays unresolved. Remote objects created before a failed ref update may remain
  orphaned; this package does not delete them.
- CI/rollout jobs checkpoint dispatch intent before the dispatch call. A status
  read requires an exact correlation ID, commit SHA, branch, workflow file,
  repository and `workflow_dispatch` event. A successful dispatch is not reported
  as a successful workflow.
- A stored run ID is fetched directly. Otherwise the scan is limited to three
  pages of 50 runs from the specific workflow. Multiple matches, an incomplete
  scan, a missing conclusion, or missing evidence remain inconclusive.
- Rollout reconciliation requires a run ID returned by the dispatch itself.
  Workflow run listings do not prove the image/rollback/CI input values. If
  GitHub returns 204 without a run ID, or the receipt is lost, title matching is
  insufficient and rollout status needs operator review. CI may use the bounded
  exact-evidence scan because its only input is the correlation ID.
- Old dispatched CI jobs can be observed using their immutable workflow argument.
  Old commit jobs without a candidate-SHA checkpoint and old rollout jobs without
  a persisted workflow name remain manual-review cases. No synthetic checkpoint
  is backfilled from a guess.
- Pending jobs are reported as awaiting a worker, not automatically retried.
  Uncertain jobs never become retryable merely because time elapsed or a search
  returned no results. Read failure remains an error, not evidence of absence.

The response includes `recovery.mode: observation_only`,
`automaticReplayAllowed: false` and an evidence reason. This recovers truthful
job state where remote evidence exists; it is not a full autonomous self-healing
system or a remedy for every historical task.

## Deployment and later validation

Preparation and local tests do not change the live service. Deployment remains a
separate operator decision. Before any later production activation:

1. Review the exact integrated commit and check the current service image/config.
2. Back up the job database. The schema change only adds nullable `checkpoint`
   and `updated_at` columns; no rows, approvals or existing states are rewritten.
3. Keep rollout OFF while validating isolated fixture jobs and existing gates.
4. With separately approved repository/branch operations, validate lost-response
   and stopped-worker cases on a disposable work branch and approved CI workflow.
   Verify duplicate polls never create a commit, dispatch or deployment.
5. Review live rollout's workflow, digest-pinned images, CI evidence, environment
   protection and rollback procedure before asking for its distinct activation.
   Any new persistent access or credential permission needs separate approval.

No live GitHub writes, workflow dispatch, VPS/SSH, provider calls, deployment, or
queue migration are part of the local test suite.

## Local verification

Use the frozen development dependencies and the repository's safety fixtures:

```sh
UV_CACHE_DIR=/tmp/omni-uv-cache uv sync --frozen --dev
.venv/bin/python -m pytest tests/backend/test_live_self_healing.py \
  tests/backend/test_live_adapters.py tests/backend/test_live_github.py \
  tests/backend/test_live_handoff_access.py -q
```

Tests cover gate preservation, stale policy and repository scope, encrypted job
storage, exact and inconclusive reconciliation, bounded scans, ownership,
duplicate submissions and concurrent terminal-state preservation. GitHub
operations are synthetic mocks; this does not prove real VPS integration or
end-to-end execution against production.
