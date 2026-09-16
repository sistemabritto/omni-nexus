# Hermes VPS repair — 2026-09-12

Service: hermes_hermes on evo-nexus-vps.

## Repairs
- Replaced retired evonexus_omniroute DNS with omniroute_omniroute in all four profile configs. Authenticated model discovery passed in all profiles.
- Updated 0.21.1 to 0.21.2 (upstream 819988acb750836387fbb9d5d76203a9b3f530f4), retaining the Telegram Oga/Ogg upload patch.
- Native offline sessions repair rebuilt the malformed messages_fts_trigram index.
- Startup retention removed two old sessions; restored those 2 sessions and 38 messages from backup. Final doctor confirms 178 sessions and 3,918 messages. Disabled automatic pruning explicitly in every profile.
- Disabled platforms.api_server.enabled explicitly in secondary profiles. API_SERVER_ENABLED=false alone did not prevent activation from inherited credentials. Final startup has four Telegram connections and no API bind failures.
- Updated affected npm packages and Vitest 4.1.11. Root/browser and web audits are clean. Native doctor still notes two moderate ui-tui dependency advisories and optional unconfigured integrations.
- Final doctor confirms four supervised gateways, running dashboard, valid config schema 44, and healthy main session database. All four databases previously passed SQLite quick_check.

## Deployment
Image: hermes-agent:0.21.2-repaired-20260912
Image ID: sha256:f779c97910da71ae7d08575c15570f47b3d1fd1c0646d580a61fbfda7f6a318c
Build: scripts/Dockerfile.hermes-stt
This is a local image on the single-node VPS; build or publish it before migrating nodes.

Updated the service and /root/hermes2.yml, /root/hermes2-portainer.yml and applicable image references in /root/agent-recovery.override.yml. Portainer's stored stack definition was not independently updated via its API.

## Backups
- /root/hermes-repair-20260912T194016Z/ — initial configs.
- /root/hermes-update-20260912/ — original service specification, deployment files, final build source, additional configs.
- /mnt/docker-volumes/hermes-unified/state.db.malformed-backup-20260912_210849 — native repair backup.
- /mnt/docker-volumes/hermes-unified/state.db.before-history-restore-20260912 — snapshot before restoring the two old sessions.

No Telegram messages were sent to users as part of maintenance tests.

## Final functional probes
All three model aliases returned HTTP 200 with answers from the final container. Observed times: Heavy 47.0s, Fast 60.8s, Core 60.9s (earlier probes were 2.8–17.8s). Provider latency is variable; this is not a sustained-load benchmark. Dashboard returned its expected login redirect (302). A real maintenance conversation through the Hermes API returned HTTP 200 with an answer.
