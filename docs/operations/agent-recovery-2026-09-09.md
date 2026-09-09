# Magneto and Hermes recovery — 2026-09-09

Host: `swissnode` (`evo-nexus-vps`).

## Causes and changes

- Magneto ignored the configured active provider when `fallback_providers`
  was empty (or contained no recognized provider). It used a hardcoded NVIDIA
  chain instead. Live requests returned HTTP 410 for retired GLM 5.2 and
  DeepSeek V4 Flash endpoints. The resolver now respects configured providers,
  including a single provider with no fallbacks.
- OpenClaude put the provider error in its JSON result on stdout. The runner
  reported only `exit code 1`. It now reads `is_error` and the actual diagnostic,
  including when the subprocess exits zero with an error envelope.
- Telegram capped an entire reasoning/tool run at 45 seconds. Its attempt
  budget is now 900 seconds, with an 1800-second total fallback budget.
- OmniRoute was stopped after disk-full failures four days earlier. Space was
  available during this repair, but Swarm had exhausted its five restart
  attempts. The service was recovered and its restart policy now retries
  indefinitely (`condition: any`, `delay: 10s`, `max_attempts: 0`).
- Hermes was updated from v0.20.5 (upstream `93a29d11`) to v0.21.1
  (upstream `48465c39`, 2026.9.7). All four profiles share the updated image.
- The default Hermes profile's Nemotron route returned 503 and timed out.
  Its primary is now `auto/best-chat`, with `auto/reasoning` and `auto/fast`
  fallbacks. Its endpoint now uses internal `http://omniroute:20128/v1`.
  Excarplex, iron and stoic retain their Claude Sonnet primary and existing
  fallback configuration.

## Deployment and recovery

Production images:

- Telegram and scheduler: `evo-nexus-runtime:agent-fix-20260909`
- Dashboard: `evo-nexus-dashboard:agent-fix-20260909`
- Hermes: `nousresearch/hermes-agent@sha256:4a8b2b1940ff4370b910dce1c327c52f6abcc5ed1c1eb1748611ab967bb3e624`

The EvoNexus recovery tags are local images on the single-node VPS. Service
specifications reference them persistently. For stack redeployment before
these code changes are included in registry images, merge
`agent-recovery.override.yml` after the main stack file. A copy is at
`/root/agent-recovery.override.yml` on the VPS. Redeploying only the old main
stack's `latest` images would restore the old code.

Historical rebuild command (the old base must now be restored first):

```sh
docker build -f scripts/Dockerfile.agent-recovery \
  --build-arg BASE_IMAGE=evo-nexus-runtime:before-agent-fix-20260909 \
  -t evo-nexus-runtime:agent-fix-20260909 .
```

Use the analogous dashboard base/tag for the dashboard image. The subsequent
user-authorized `docker system prune -a` removed unused rollback images,
including the old local `before-agent-fix-20260909` tags. They are no longer
available as local rebuild bases. The previous Hermes image can be pulled as
`nousresearch/hermes-agent@sha256:b2c76e926229834e2598cac54a330d10800a82ab795ecbf22b1e4cc9584d829e`.

Hermes backups are at `/mnt/docker-volumes/hermes-unified/backups/pre-update-20260909/`:
per-profile configs, credentials, cron, pairing, memories and consistent SQLite
backups. Sessions and other user data remain on the original persistent bind
mount. No user data was deleted. Original EvoNexus code and the deployment
build context are at `/root/agent-fix-20260909/`.

The Docker image update follows the
[official Hermes update guidance](https://nousresearch.github.io/hermes-agent/docs/getting-started/updating/).

## Validation

- 22 targeted regression tests passed, covering provider selection, error
  envelopes, caller workspace behavior, provider pinning and Telegram.
- Live Magneto request used `omnirouter:auto/best-chat` and returned `OK`.
- Magneto with effort high completed an 86-second run (including a controlled
  50-second tool wait), returning `MAGNETO_OK` and the correct sum `234168`.
  This exceeds the old 45-second cap and finished without an error.
- All four Hermes profiles returned `OK` using their configured credentials
  and model routes after the default profile repair.
- Stoic and iron's actual Hermes CLI with reasoning high returned the correct sum
  `234168` for integers 1–1000 divisible by 3 or 5.
- All four gateways reported v0.21.1, running, Telegram connected and no
  Telegram error. Swarm updates completed for all changed services.

At initial recovery the disk had approximately 20 GiB free (92% occupied).
The subsequent [storage and performance work](vps-optimization-2026-09-09.md)
reduced usage to 52% and added backup retention.
