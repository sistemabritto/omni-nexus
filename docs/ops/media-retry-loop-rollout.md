# Media retry loop hotfix

A worker could immediately reclaim a permanently broken job millions of times.
Input scaffolding also happened after committing a queued row, leaving orphaned
jobs when the dashboard's media volume was read-only.

## Behavior

- Dashboard owns a persisted `next_retry_at`, eligibility and an atomic claim.
- At most five attempts. Backoff starts at 60 seconds, doubles per attempt and
  adds positive jitter (up to 25%); the delay is capped at one hour.
- Missing/invalid manifests and configuration/auth failures are terminal.
  Unknown failures remain recoverable but bounded. This does not eliminate 429.
- Startup adds one nullable column and terminalizes already exhausted, unlocked
  legacy `retryable_failure` rows, preserving attempts and error text.
- Watchdog releases stale claims with the same retry ceiling and due date.
- Scaffold failure returns HTTP 503 without committing a queued job. Existing
  read-only mounts stay unchanged: this hotfix does not enable video creation on
  a read-only dashboard volume, nor bridge approval to publishing/scheduling.

## Rollout

1. Build the branch using `docker-publish-britto.yml`, manual input
   `media_only=true`. Branch builds do not write `latest`; use SHA-tagged images
   and pin the resolved digests. Do not merge solely to obtain an image.
2. Record the exact service image digests and replica counts. Pause only the
   media worker; inspect current claims before proceeding. Snapshot the SQLite
   database through SQLite's backup API; keep the backup private on the VPS.
3. Replace the dashboard image first, retaining environment, mounts, networks
   and secrets. Verify health and the additive migration. Quarantine exhausted
   orphan retries; do not reset attempt counters or create new media jobs.
4. Replace the worker image by digest while paused. Before restoring its prior
   replica count, verify there are no eligible jobs that would generate content
   without authorization. If there are, retain the pause and report them.
5. Restore the prior worker replica count only after that check. Observe across
   at least two polling intervals: legacy counters remain stable, failed jobs
   are not reclaimed, health remains good, no new output or publication occurs.
   Confirm image digest and patched file hash in both running containers.

## Rollback

Pause the worker, restore both recorded image digests, then inspect queue state
before resuming. Keep the additive column; old code ignores it. Keep exhausted
rows terminal so rollback does not restore the loop. Restore the DB snapshot
only after review, because wholesale restoration would overwrite concurrent
non-media activity. No content publication or credential changes are required.

## Validation

Tests cover missing/invalid input before provider invocation, terminal failures,
transient 429/timeouts, maximum attempts, persisted wait across requests, atomic
claim guards, another job advancing, startup migration, watchdog reap, worker
429 backoff, and read-only/full-volume creation without a queued orphan.
