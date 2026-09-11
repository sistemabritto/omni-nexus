"""Panorama 2026-07-17, item 4 — in-process heartbeat handler that checks for
overdue Goals and Tickets and alerts via Telegram.

Called by heartbeat_runner when heartbeat config has
``handler: deadline_check.tick``. Zero Claude CLI invocations — pure SQL +
an HTTP POST to Telegram, same shape as plugin_integration_health.tick.

Before this, nothing proactively surfaced a Goal or Ticket past its
due_date — the human only found out by opening /goals or /kanban. Weekly
Review (scheduler.py) covers this once a week; this closes the gap between
runs with a cheap, LLM-free check every few hours.

Extended 2026-09-11 (auditoria heartbeats/goals): a `blocked` ticket
waiting on a human decision has NO due_date most of the time — it's an
auto-generated diagnostic ("Funil: X% de perda...") or an approval gate,
not a deadline. `_overdue_tickets` alone never re-surfaces those, so once
the one Telegram card that created them scrolls off, nothing nudges again.
Confirmed live: a funnel ticket sat 19 days untouched (created 2026-08-23,
only auto-flagged blocked on 2026-09-10 by an unrelated health check).
`_stale_blocked_tickets` closes that gap using the same re-alert-every-run
philosophy as the due_date check below — no dedup table, because a
repeated nudge for a still-unaddressed blocker is the point.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"

_MAX_ITEMS_PER_ALERT = 8
_STALE_BLOCKED_DAYS = 3


def _overdue_goals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, due_date FROM goals "
        "WHERE status = 'active' AND due_date IS NOT NULL AND due_date < date('now') "
        "ORDER BY due_date ASC"
    ).fetchall()


def _overdue_tickets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, due_date FROM tickets "
        "WHERE status IN ('open', 'in_progress', 'blocked') "
        "AND due_date IS NOT NULL AND due_date < date('now') "
        "ORDER BY due_date ASC"
    ).fetchall()


def _stale_blocked_tickets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """`blocked` tickets with no due_date fall outside `_overdue_tickets`
    entirely — this catches them by how long they've sat blocked instead.
    `updated_at` is the last status-change timestamp (see
    routes/tickets.py), so this is "days since last touched", not "days
    since created" — a ticket someone commented on recently isn't stale
    even if it's been open a while.
    """
    return conn.execute(
        "SELECT id, title, updated_at FROM tickets "
        "WHERE status = 'blocked' AND due_date IS NULL "
        "AND datetime(updated_at) < datetime('now', ?) "
        "ORDER BY updated_at ASC",
        (f"-{_STALE_BLOCKED_DAYS} days",),
    ).fetchall()


def _build_alert(goals: list[sqlite3.Row], tickets: list[sqlite3.Row],
                  stale_blocked: list[sqlite3.Row] | None = None) -> str:
    """Monta o alerta. Título é texto que o humano escreveu, então é escapado.

    A mensagem vai com parse_mode=HTML. Uma única Meta chamada
    `A/B de preço < R$100` fazia o Telegram devolver 400 e o alerta inteiro
    sumia — não só aquele item, todos os outros junto.
    """
    from notifications import _esc

    stale_blocked = stale_blocked or []
    lines = [f"⏰ <b>{len(goals)} Meta(s) e {len(tickets)} Ticket(s) vencidos</b>"]
    if goals:
        lines.append("\n🎯 Metas:")
        for g in goals[:_MAX_ITEMS_PER_ALERT]:
            lines.append(f"  • #{g['id']} {_esc(str(g['title']))} — venceu {_esc(str(g['due_date']))}")
        if len(goals) > _MAX_ITEMS_PER_ALERT:
            lines.append(f"  … e mais {len(goals) - _MAX_ITEMS_PER_ALERT}")
    if tickets:
        lines.append("\n🎫 Tickets:")
        for t in tickets[:_MAX_ITEMS_PER_ALERT]:
            lines.append(f"  • {_esc(str(t['title']))} — venceu {_esc(str(t['due_date']))}")
        if len(tickets) > _MAX_ITEMS_PER_ALERT:
            lines.append(f"  … e mais {len(tickets) - _MAX_ITEMS_PER_ALERT}")
    if stale_blocked:
        lines.append(f"\n🔒 Bloqueados há mais de {_STALE_BLOCKED_DAYS} dias, sem prazo, aguardando decisão:")
        for t in stale_blocked[:_MAX_ITEMS_PER_ALERT]:
            lines.append(f"  • {_esc(str(t['title']))} — desde {_esc(str(t['updated_at'])[:10])}")
        if len(stale_blocked) > _MAX_ITEMS_PER_ALERT:
            lines.append(f"  … e mais {len(stale_blocked) - _MAX_ITEMS_PER_ALERT}")
    return "\n".join(lines)


def tick() -> dict:
    """Main handler — checks for overdue Goals/Tickets, alerts if any exist.

    Returns a summary dict for logging purposes. Deliberately re-alerts every
    run while something stays overdue (no dedup table) — an in-process check
    every few hours is cheap, and a repeated nudge is the point, not a bug.
    """
    if not DB_PATH.exists():
        return {"error": "db not found", "overdue_goals": 0, "overdue_tickets": 0, "alerted": False}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        goals = _overdue_goals(conn)
        tickets = _overdue_tickets(conn)
        stale_blocked = _stale_blocked_tickets(conn)
    finally:
        conn.close()

    alerted = False
    if goals or tickets or stale_blocked:
        from notifications import send_telegram_alert
        alerted = send_telegram_alert(_build_alert(goals, tickets, stale_blocked))

    log.info(
        "deadline_check.tick: overdue_goals=%d overdue_tickets=%d stale_blocked=%d alerted=%s",
        len(goals), len(tickets), len(stale_blocked), alerted,
    )
    return {
        "overdue_goals": len(goals), "overdue_tickets": len(tickets),
        "stale_blocked_tickets": len(stale_blocked), "alerted": alerted,
    }
