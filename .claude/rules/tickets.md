# Tickets — Persistent Conversation & Work Threads

Persistent topics with state, assignable to agents, with atomic checkout. Primary inbox for heartbeat-driven agents.

## Model

| Field | Notes |
|---|---|
| `id` | UUID string |
| `title`, `description` | Text, description optional |
| `status` | `open` / `in_progress` / `blocked` / `review` / `resolved` / `closed` (CHECK enum) |
| `priority` | `urgent` / `high` / `medium` / `low` |
| `assignee_agent` | agent slug (`zara-cs`, `flux-finance`, ...) |
| `project_id`, `goal_id` | Optional links to Goals (F1.2) |
| `task_id` | Optional FK to a specific `goal_tasks.id` (not just the goal). **Set this whenever a ticket represents one specific goal_task** — e.g. tickets mirroring a task with a `[GOAL:N] <task title>` naming convention. Without it, resolving the ticket has no way to advance the task: title-matching is not read back by any code. When `task_id` is set, resolving/closing the ticket (via API, bulk action, or `heartbeat_outcome._move_ticket`) automatically marks the linked `goal_task` `done` and recalculates the goal's `current_value` — see `_sync_goal_task_from_ticket` in `dashboard/backend/heartbeat_outcome.py`. Confirmed live 2026-07-15: 24 tickets had been resolved for weeks with their goal_tasks still `open` because this link didn't exist yet. |
| `locked_at`, `locked_by` | Atomic checkout state |
| `lock_timeout_seconds` | Default 1800 — janitor releases after this |

Comments: `ticket_comments` (author = `human:x` or `agent:y`).
Activity log: `ticket_activity` (events: created, status_changed, checkout, release, force_release, assigned, comment_added, deleted).

## Atomic Checkout

```sql
UPDATE tickets
SET locked_at = now(), locked_by = ?, lock_timeout_seconds = ?, lock_token = ?
WHERE id = ? AND locked_at IS NULL
```

Row count = 1 → got the lock. Row count = 0 → already locked (409 Conflict returned).

Guarantees: exactly one process acts on a ticket at a time. Verified by concurrency test (10 parallel requests → 1 wins, 9 get 409).

### `lock_token` — quem prova a posse do lock

O checkout devolve **`lock_token`** no corpo da resposta, **uma única vez**. Ele
nunca aparece em `to_dict()`, nem na listagem, nem no 409 — expor o segredo
desfaria o ponto dele. **Guarde-o e mande de volta no release.**

```
POST /api/tickets/{id}/release   {"lock_token": "<o que o checkout devolveu>"}
```

Existe porque a autorização do release saía do **corpo da requisição**: ele
comparava `ticket.locked_by` com um `agent` que o próprio chamador mandava — e o
409 do checkout devolve `locked_by`, então nem era preciso adivinhar. Qualquer um
com `tickets:execute` soltava o lock de qualquer agente, e a garantia de
"exatamente um processo age sobre um ticket por vez" não valia.

**Identidade por agente não resolve isso, e a tentativa de usá-la falhou:** uma
primeira correção exigia `workspace:manage` para soltar em nome de outro. Não
barrava ninguém — `app.py::_try_api_token_auth` resolve TODO portador do
`DASHBOARD_API_TOKEN` para o mesmo usuário de serviço, que é **admin**, e admin
tem `workspace:manage`. O gate aprovava exatamente quem devia barrar.

**Forçar** (quebrar o lock de um agente travado) continua possível e continua
necessário, mas só por **humano em sessão de navegador com papel admin**:
chamada autenticada por API token é recusada com 403 mesmo sendo admin
(`g.auth_via_api_token`, a mesma porta estreita de
`approvals.py::decide_approval_via_dashboard`). A quebra entra no
`ticket_activity` como **`force_release`**, evento próprio, com
`previously_locked_by` — nunca confundida com um release normal.

Detalhes que valem lembrar:
- Release de ticket já livre é **no-op 200** (`already_free`), não erro: o
  janitor pode ter chegado antes e o agente não tem como saber.
- O token é limpo junto com o lock. Reusar um token velho no checkout seguinte
  daria a quem guardou o segredo antigo o poder de soltar o novo dono.
- `lock_timeout_seconds` é validado na faixa **60..86400**. Antes ia cru para
  `int()`: lixo dava 500 em vez de 400, e negativo fazia o janitor recuperar o
  lock no primeiro tick, anulando o checkout recém-dado.

Quem solta por **SQL direto** (`ticket_janitor`, `heartbeat_runner`,
`knowledge/classify_worker`) não passa por aqui e não precisa do token.

## Auto-Release (Janitor)

`dashboard/backend/ticket_janitor.py` runs every 5 minutes:
- `SELECT id FROM tickets WHERE locked_at IS NOT NULL AND datetime(locked_at, '+' || lock_timeout_seconds || ' seconds') < now()`
- For each, clear lock + log activity (`actor='system:janitor'`)

Prevents orphaned locks from crashed runs.

## Mentions

Comment body with `@agent-slug` (regex `@([a-z0-9-]+)`):
- Parser matches against known agent slugs (`.claude/agents/*.md`)
- For each mention with an enabled heartbeat: insert `heartbeat_triggers` row with `trigger_type='mention'`
- Dispatcher wakes the agent on next debounce window (30s)

## Tickets vs Sessions

| | Ticket | Session |
|---|---|---|
| Lifetime | Days / weeks | Single conversation |
| State | 6 workflow states | Open / closed |
| Persistence | DB-first | JSONL logs |
| Inbox | Yes (heartbeat step 3) | No |
| Use when | Recurring topic | Ephemeral exploration |

Sessions can attach to tickets via `sessions.ticket_id` (optional). Chat UI offers dropdown to attach on create.

## UI

- `/issues` — global list with filters (status, priority, assignee, project, goal, search)
- `/tickets/{id}` — detail view with merged timeline (comments + activity + status changes)

### Actions

- **List**: create new, bulk close / delete / reopen / reassign / relink goal
- **Detail**: edit title, change status, change priority, add comment, release lock, delete

## API

```
GET    /api/tickets                  # list with filters
GET    /api/tickets/{id}             # single with relations
GET    /api/tickets/{id}/timeline    # merged events
POST   /api/tickets                  # create
PATCH  /api/tickets/{id}             # update fields
DELETE /api/tickets/{id}             # delete (logs activity)
POST   /api/tickets/{id}/checkout    # atomic lock
POST   /api/tickets/{id}/release     # release lock (exige lock_token; ver acima)
POST   /api/tickets/{id}/comments    # add comment, parse mentions
POST   /api/tickets/bulk             # close/reopen/delete/reassign/relink_goal
GET    /api/tickets/export.csv       # CSV export
```

## Heartbeat Inbox Integration

```python
# dashboard/backend/ticket_inbox.py
def get_inbox_for_agent(agent_slug, limit=10):
    """Tickets assigned to agent, ordered by priority DESC, created_at ASC."""
    # Used by heartbeat_runner.py step 3
```

Query used by heartbeats:
```sql
SELECT * FROM tickets
WHERE assignee_agent = ?
  AND status IN ('open','in_progress')
  AND locked_at IS NULL
ORDER BY
  CASE priority WHEN 'urgent' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC,
  created_at ASC
LIMIT ?
```

## Retro-Tickets Script

`scripts/suggest_retro_tickets.py` scans existing chat sessions and proposes tickets to create from recurring topics. Output: `workspace/development/features/tickets/[C]retro-tickets-suggestions.csv`. Davidson reviews manually — no auto-creation.

## Related Rules

- `heartbeats.md` — tickets feed the inbox in step 3
- `goals.md` — tickets can link to goals via `goal_id`
