# VPS storage and runtime optimization — 2026-09-09

Host: swissnode, SSH alias `evo-nexus-vps`. 8 vCPU, approximately 17.6 GiB RAM,
4 GiB swap, 236 GiB root filesystem. This is a single-node deployment, not HA.

## Measured outcome

Root filesystem went from approximately 206 GiB used / 20 GiB available (92%)
to 117 GiB used / 110 GiB available (52%), after asynchronous containerd GC.
Available RAM at final check was 8.5 GiB, load approximately 1.5, and sampled
CPU idle 95%. Swap remained allocated but there was no sustained swap-out;
no disruptive swapoff or speculative kernel tuning was performed.

## Storage causes and corrective actions

- Ran the requested `docker system prune -a -f`, without `--volumes`.
  Docker reported 3.694 GB reclaimed. Unused images, stopped containers and
  build cache are disposable; removed local rollback tags require restoration
  or a registry pull before reuse. Active application volumes were preserved.
- Local EvoNexus backup ZIPs occupied approximately 58 GiB. Retention was
  unset; the host retention script also exited on an unmatched tarball glob.
  The new retention policy keeps the newest three automatic backups, preserves
  manual/pre-update snapshots and only removes eligible files older than 24h.
  Validated retained ZIP manifests and tested the newest ZIP's complete CRC.
  Removed 35 old backup artifacts totaling 52,604,723,634 bytes. Removed ZIPs
  were also present in the pre-existing R2 backup from September 9; recovery
  there is limited by the existing three-day remote retention policy.
- containerd retained approximately 42 GiB outside Docker's classic overlay2
  image store. Validated all running containers use Docker overlay2, not these
  snapshots, before removing 34 unused image references and 837 stale leases
  through containerd's API. Preserved recent leases and OmniRoute references.
  Garbage collection reclaimed additional space without deleting live tasks.
  Inventory: `/root/vps-tuning-20260909/containerd-legacy-inventory.json`.

## Backup pipeline

Installed `scripts/vps-backup.sh` as `/usr/local/bin/vps-backup.sh`, preserving
the daily schedule and existing notifications. Notification credentials now
reside in root-only `/etc/vps-backup-notify.env`, not the public script.

- Prevent overlapping runs with flock; low CPU/I/O priority; 10 GiB free guard.
- Upload each archive separately, verify remote size, then remove local staging.
  One transfer, two checkers, 12 MiB/s bandwidth cap; no full-backup staging pile.
- Exclude nested automatic backups, caches and reproducible dependencies.
  Preserve sessions and application data. Include previously missed Plausible
  bind data and the CRM controller patch.
- Logical dumps cover all discovered PostgreSQL containers and Ghost MySQL.
  Online SQLite snapshots cover OmniRoute and Hermes profile databases, with
  integrity checks. Raw volume archives are supplementary to logical snapshots.
- A COMPLETE.json marker is written only after full success. Remote retention
  remains three days; manual snapshots are not part of automatic deletion.
- Installed `scripts/vps-backup-retention.py` and the locking wrapper under
  `/usr/local/lib` and `/usr/local/bin`; existing 03:30 cron retained.
  Dashboard and scheduler now explicitly set BACKUP_RETAIN_LOCAL=3. Source
  `backup.py` also defaults to three for future image builds.

Validation: shell syntax passed; actual R2 smoke upload, download and checksum
comparison passed with notifications disabled; live OmniRoute SQLite online
snapshot and quick_check passed; retention second dry-run proposed zero files;
backup-default regression test passed. A complete new production backup and
full application restore have NOT been run end-to-end in this maintenance.
Original host scripts are retained in `/root/vps-tuning-20260909/`.

## Central OmniRoute

Retained version 3.8.49 and pinned the original base image in
`scripts/Dockerfile.omniroute-runtime`. Fixed missing ioredis runtime files by
installing ioredis 5.11.1. Deployed local image `omniroute:vps-tuned-20260909`.

Persistent overlay: `agent-recovery.override.yml`, also copied to
`/root/agent-recovery.override.yml`. Always merge it after the main stack until
these changes are incorporated into registry images. Local image tags need
rebuilding or publishing before migration to another host.

- Redis uses existing central Redis database 1; live authenticated PING passed.
- 3 CPU / 4 GiB limit, 0.5 CPU / 1 GiB reservation; Node heap 2560 MiB leaves
  headroom for native allocations. No blind increase in provider concurrency.
- Provider request budget 300s, queue depth 32, readiness/idle 180s, maximum
  readiness 600s and SSE heartbeat 15s accommodate slower reasoning requests.
- Early stream recovery enabled; midstream replay disabled to avoid duplicate
  tool operations. Provider quotas and outages remain external constraints.
- Correct image healthcheck, 90s startup window, 300s shutdown grace,
  automatic update rollback and unlimited task restart attempts.
- Four concurrent streaming probes (best-chat, coding, reasoning, fast) passed
  on the final image in approximately 1.95–2.52s. This is a functional smoke
  test, not a sustained-load benchmark or a zero-failure guarantee.

## Other resources and monitoring

ClickHouse system logs consumed approximately 4.5 GiB, with trace-level logging
and frequent profiling generating unnecessary writes. Installed Docker config
`clickhouse-vps-logging-20260909` from `config/clickhouse-vps-logging.xml`:
warning logging, bounded log files, seven-day text/query TTL and disabled
continuous profiling logs. Set 1 CPU / 1536 MiB limit and 256 MiB reservation.
Existing historical tables were not manually purged; all 48 analytics events
were preserved. Running configuration reports logger level warning.

Recovered CRM Redis and Auth tasks that had remained down after disk-full
failures. Their startup health windows were increased and exhausted restart
limits removed. Both now have 1/1 replicas, without deleting queues.

Installed weekly/size-bounded host maintenance log rotation. Existing Docker
20 MiB × 3 container log rotation was retained; no daemon restart was needed.

`vps-healthcheck.timer` checks every five minutes and records local status at
`/var/lib/vps-maintenance/health.json`. It warns on disk >=85% and RAM <1 GiB,
and only forces recovery of a stranded OmniRoute service after three checks,
with a 30-minute cooldown. It does not restart an initializing task or react
to upstream provider failures. Docker healthchecks handle unhealthy tasks.
This is local monitoring, not an external alerting/HA service.

Final service inventory: application services 1/1; Postiz database bootstrap
is 0/1 because its one-shot task completed seven weeks ago, not a new failure.
Core monitor returned no warnings. Previous Magneto/Hermes validation is in
the companion agent recovery report.
