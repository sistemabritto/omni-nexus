# EvoNexus — Routines & Scheduled Tasks

Routines are automated workflows that run on a schedule via the ADW Runner.

## Core vs Custom

| Type | Location | Tracked | Description |
|------|----------|---------|-------------|
| **Core** | `ADWs/routines/` | Yes | Essential system routines shipped with the repo |
| **Custom** | `ADWs/routines/custom/` | No (gitignored) | User-created, workspace-specific routines |

## Core Routines

| Routine | Script | Agent | Schedule |
|---------|--------|-------|----------|
| Good Morning | `good_morning.py` | @clawdia | Daily 07:00 |
| End of Day | `end_of_day.py` | @clawdia | Daily 21:00 |
| Memory Sync | `memory_sync.py` | @clawdia | Daily 21:15 |
| Weekly Review | `weekly_review.py` | @clawdia | Friday 08:00 |
| Memory Lint | `memory_lint.py` | @clawdia | Sunday 09:00 |

> **Memory Sync** follows the LLM Wiki pattern: extracts knowledge from daily logs, meetings, and git changes, then **propagates updates** across related memory files (e.g., a role change updates people/, glossary.md, and CLAUDE.md). Updates `memory/index.md` (catalog) and `memory/log.md` (operation log) after each run.

## Custom Routines

Custom routines live in `ADWs/routines/custom/` (gitignored) and are scheduled via `config/routines.yaml` (also gitignored).

To create a custom routine, say **"create a routine"** and the `create-routine` skill will guide you.

### config/routines.yaml

```yaml
daily:
  - name: "My Routine"
    script: my_routine.py
    time: "19:00"
    enabled: true

weekly:
  - name: "Weekly Report"
    script: weekly_report.py
    day: friday
    time: "09:00"
    enabled: true

monthly:
  - name: "Monthly Close"
    script: monthly_close.py
    day: 1
    time: "08:00"
    enabled: true
```

## Scheduled Tasks (One-Off)

Scheduled tasks are **non-recurrent actions** that execute once at a specified date/time. Unlike routines (which repeat on cron), a scheduled task runs once and is done.

Use cases:
- "Post no LinkedIn sexta 10h"
- "Roda o financial pulse amanha 8h"
- "Envia resumo pro Telegram as 14h"

### Creating Scheduled Tasks

**Via CLI:** Say "schedule this for" or use the `schedule-task` skill.

**Via Dashboard:** Go to `/tasks` → click "New Task" → fill the form.

**Via API:**
```bash
POST /api/tasks
{
  "name": "Post LinkedIn — Summit",
  "type": "skill",           # skill | prompt | script
  "payload": "social-post-writer LinkedIn post about Summit",
  "agent": "pixel-social-media",
  "scheduled_at": "2026-04-11T16:00:00Z"
}
```

### Task Lifecycle

```
pending → running → completed
                  → failed (can retry)
pending → cancelled
```

The scheduler checks for pending tasks every 30 seconds and executes them in background threads.

### Dashboard

Tasks are managed at `/tasks` in the dashboard with:
- Filter by status (pending, running, completed, failed)
- Create/edit/cancel/delete actions
- "Run Now" for immediate execution
- View result/error output

## Triggers (Reactive)

Triggers are event-driven actions that execute in response to external events — unlike routines (cron-based) and tasks (one-off scheduled).

### Types

| Type | Description |
|------|-------------|
| **Webhook** | Receives HTTP POST from external services, validates HMAC signature, executes action |
| **Event** | Reacts to integration events (configured in YAML or Dashboard UI) |

### Supported Sources

| Source | Signature | Example Events |
|--------|-----------|----------------|
| GitHub | `X-Hub-Signature-256` | push, pull_request, issues, release |
| Stripe | `Stripe-Signature` | charge.succeeded, subscription.created, invoice.paid |
| Linear | `X-Linear-Signature` | Issue (create/update), Comment |
| Telegram | Token-based | message, callback_query |
| Discord | Ed25519 | message_create |
| Custom | `X-Webhook-Signature` | Any user-defined |

### Configuration

Triggers are defined in `config/triggers.yaml` (synced to DB on startup) or created via Dashboard UI / Skill CLI.

```yaml
webhooks:
  - name: "Deploy Notification"
    source: github
    event_filter:
      event: push
      branch: main
      repo: "EvolutionAPI/evolution-api"
    action_type: skill
    action_payload: "discord-send-message Deploy da evolution-api na main"
    agent: pulse-community
    enabled: true
```

### API Endpoints

| Method | Endpoint | Action |
|--------|----------|--------|
| GET | `/api/triggers` | List triggers |
| POST | `/api/triggers` | Create trigger |
| PUT | `/api/triggers/<id>` | Update trigger |
| DELETE | `/api/triggers/<id>` | Delete trigger |
| POST | `/api/triggers/<id>/test` | Test trigger |
| POST | `/api/triggers/webhook/<id>` | **Webhook receiver** (public, HMAC-validated) |

### Webhook URL Format

After creating a webhook trigger, configure the external service to POST to:
```
https://your-dashboard.example.com/api/triggers/webhook/<trigger_id>
```

Use the secret (shown on creation) to configure HMAC signing in the source service.

### Dashboard

Triggers are managed at `/triggers` in the dashboard with:
- Filter by type (webhook/event), source, enabled/disabled
- Create/edit/delete/test actions
- Toggle enable/disable
- View execution history
- Copy webhook URL
- Regenerate webhook secret

## Dynamic Routine Discovery

Routines are discovered dynamically from script files. The system:

1. Scans `ADWs/routines/*.py` (core) and `ADWs/routines/custom/*.py` (custom)
2. Extracts agent from docstring (`via AgentName` pattern)
3. Builds make-IDs automatically (e.g. `financial_pulse.py` → `fin-pulse`)

No hardcoded mappings needed — add a new script and it's automatically available.

## How It Works

1. Scheduler runs embedded in the dashboard (`make dashboard-app`)
2. Core routines are hardcoded in `scheduler.py`
3. Custom routines are loaded from `config/routines.yaml`
4. Scheduled tasks are stored in SQLite and checked every 30 seconds
5. Each routine/task invokes Claude Code CLI via the ADW Runner (`ADWs/runner.py`)
6. Runner logs to `ADWs/logs/` (JSONL + metrics)
7. Reports saved to workspace folders

## Manual Execution

```bash
# Core routines (dedicated targets)
make morning      # Good Morning
make eod          # End of Day
make memory       # Memory Sync
make memory-lint  # Memory Lint
make weekly       # Weekly Review
make backup-daily # Daily Backup (manual só — não é mais agendado; ver .claude/rules/routines.md §Backup)

# Any routine (core or custom) via dynamic runner
make run R=fin-pulse        # Financial Pulse
make run R=community-week   # Community Weekly
make run R=licensing        # Licensing Daily

# List all available routines
make list-routines

# All commands
make help
```

## Agent Teams (Experimental, Opt-in)

Parallel multi-agent versions of consolidation routines. Instead of one agent collecting data sequentially, Agent Teams spawn domain-specific teammates that work in parallel.

**Trade-off:** ~3-5x higher token cost, but faster execution and each agent uses its own domain expertise.

| Target | Normal equivalent | Lead | Teammates |
|--------|------------------|------|-----------|
| `make team-strategy` | `make run R=strategy-digest` | @sage | @atlas, @flux, @pulse, @pixel |
| `make team-dashboard` | `make run R=dashboard` | @clawdia | @atlas, @flux, @pulse, @dex |
| `make team-weekly` | `make run R=weekly-review` | @clawdia | @atlas, @flux, @pulse |

Scripts live in `ADWs/routines/teams/`. These are never scheduled — run manually when you want speed or richer cross-domain analysis.

Requires Claude Code v2.1.32+ and the experimental flag (already enabled in `.claude/settings.json`):
```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```
