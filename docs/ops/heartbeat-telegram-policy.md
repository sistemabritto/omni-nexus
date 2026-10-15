# Heartbeat Telegram delivery policy

Heartbeat results, blocks and technical failures no longer notify Telegram by default. They still update the kanban, comments, activities and approval gates. The same policy applies to direct runner reports and the operational heartbeat handlers deadline_check, stale_ticket_sweep and ops_watchdog; their database work remains active.

One setting controls this transport: `HEARTBEAT_TELEGRAM_ENABLED`, default off. Only `1`, `true`, `yes`, `on` (case-insensitive) opt in. An absent or misspelled value stays off. No equivalent existing switch was found in backend/config/env examples before introducing this setting. The setting is read after notifications.py's existing .env loading. An explicit process environment value takes precedence over .env through its existing setdefault behavior. Tokens remain unchanged and cannot opt a heartbeat into delivery.

Generic send_telegram_alert, publication confirmations, pending approvals (including those created during a heartbeat outcome), and the interactive bot transport are unchanged. “Magneto” is not configured as a replacement destination. No global mute is introduced and no other project is reconfigured.

Tests replace transport with mocks; no external messages are sent. Cases cover default/false/invalid values, explicit opt-in, runner success/failure, all three outcome notification categories, a real SQLite blocked-ticket state/comment/activity write, and preservation of approval/publication/generic transport.

Base: production integration ce94a41. No production environment, heartbeat schedule, deployment or token was changed in this branch. The specific notification reported by the user has not been attributed to this emitter; the patch enforces the requested policy independently of that unproven attribution.
