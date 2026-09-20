# Settings

The **Settings** page (`/settings`) is the central configuration hub for the workspace. It is reached from the gear icon in the sidebar footer (next to your name and the logout button) and provides six tabs:

- **Workspace** — edit `config/workspace.yaml` fields (below)
- **Backups** — create/restore workspace backups, download ZIPs, S3 status, plus an in-place `.env` editor for integration keys
- **Docs** — this documentation, embedded in-page
- **Users** — user management (admin)
- **Roles** — custom roles and permission matrix (admin)
- **Audit** — audit trail (admin)

## Workspace Tab

Edit `config/workspace.yaml` fields:

| Field | Description |
|-------|-------------|
| **Workspace Name** | Display name for the workspace |
| **Owner** | Workspace owner name |
| **Company** | Organization name |
| **Language** | Response language (20 options: pt-BR, en-US, es, fr, de, ja, ko, zh-CN, etc.) |
| **Timezone** | Schedule timezone (default: America/Sao_Paulo) |
| **Dashboard Port** | Port the dashboard runs on (default: 8080) |

Changes are saved to `config/workspace.yaml` using a read-merge-write pattern that preserves other YAML keys.

Routine management lives on the dedicated **Routines** page (Inteligência section): per-routine metrics (runs, success rate, duration, tokens, cost), execution history, and a **Run Now** button. Schedules themselves are edited in `config/routines.yaml`; routine creation and deletion are handled by agents (via the `create-routine` skill), not the UI.

## API Reference

### Workspace
```
GET  /api/settings/workspace                          — read workspace config
PUT  /api/settings/workspace                          — update workspace fields
```

### Environment (.env editor, used by Backups tab)
```
GET  /api/config/env                                  — read current .env entries
PUT  /api/config/env                                  — write .env entries
```

### Chat / Trust mode
```
GET   /api/settings/chat                              — read chat settings (trustMode)
PATCH /api/settings/chat                              — update trustMode (see providers.md#trust-mode)
```

All write endpoints require authentication and `config:manage` permission; the Users, Roles and Audit tabs additionally require their respective `users`, `roles`/`audit` permissions.
