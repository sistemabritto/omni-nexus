"""stale_ticket_sweep — in-process heartbeat que pega 'zumbis' de in_progress.

Cobre o gap A5 do [C]cascade-evergreen-plan.md: um ticket que um agente marcou
`in_progress` mas que não avança (timeout do run derrubou o worker antes de ele
responder; o agente virou "zumbi"). O `deadline_check` já cobre `due_date` vencido
e `blocked` estagnado; nada cobria `in_progress` SEM due_date preso há 45min sem
nada — exatamente os zumbis de `bolt-executor`/`hawk-debugger` vistos em produção.

Comportamento (barato, zero Claude):
- Marca `in_progress` com `locked_at IS NULL` e sem movimento há >=45min como
  `blocked` + comentário "presos N min sem avanço". Bloqueado = espera humano
  (Magneto), não fica ocupando o orquestrador pra sempre.
- Alerta compacto no Magneto quando houver zumbi novo nesta varredura.

`updated_at` é o timestamp da última mudança de status/comentário, então é
"tempo desde o último toque", não "desde criado" — ticket que tem vida recente
não é zumbi. Idempotente: ticket já marcado `blocked` sai da seleção.

O tempo de varredura (60min) vem de env STALE_TICKET_MINUTES (default 60) —
ajustável sem deploy. 60min > duração máxima de um run (timeout 480s + checkout)
garante que o agente que ainda está trabalhando no ticket não seja sinalizado.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"

_MAX_ITEMS = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _stale_in_progress(conn: sqlite3.Connection, minutes: int) -> list[sqlite3.Row]:
    """`in_progress` sem lock e sem movimento há >= minutes."""
    return conn.execute(
        """SELECT id, title, assignee_agent, updated_at FROM tickets
           WHERE status = 'in_progress'
             AND locked_at IS NULL
             AND (updated_at IS NULL
                  OR datetime(updated_at) < datetime('now', ?))
           ORDER BY COALESCE(updated_at, created_at) ASC""",
        (f"-{minutes} minutes",),
    ).fetchall()


def _flag_blocked(conn: sqlite3.Connection, t: sqlite3.Row) -> None:
    now = _now_iso()
    try:
        conn.execute(
            "UPDATE tickets SET status='blocked', updated_at=?, "
            "blocked_reason='Sem avanço desde in_progress (zumbi detectado pelo sweep)' "
            "WHERE id=? AND status='in_progress'",
            (now, t["id"]),
        )
        conn.execute(
            "INSERT INTO ticket_comments (id, ticket_id, author, body, created_at) "
            "VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), t["id"], "system:stale-sweep",
             f"🧹 Preso em in_progress há mais de {minutes_hint(t['updated_at'])} sem "
             f"movimento. Movido para blocked — @Felipe, dê um olhadinha no Magneto.",
             now),
        )
        conn.execute(
            "INSERT INTO ticket_activity (id, ticket_id, actor, action, payload, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), t["id"], "agent:stale-ticket-sweep", "sweep_to_blocked", "{}", now),
        )
    except Exception as exc:  # noqa: BLE001 — sweep nunca pode derrubar a run
        log.warning("stale_ticket_sweep flag failed for %s: %s", t["id"], exc)


def minutes_hint(updated_at) -> str:
    if not updated_at:
        return "muito tempo"
    try:
        last = datetime.strptime(str(updated_at), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return f"{int((datetime.now(timezone.utc) - last).total_seconds() // 60)} min"
    except Exception:
        return "algum tempo"


def _build_alert(flagged: list[dict]) -> str:
    from notifications import _esc
    lines = [f"🧹 <b>{len(flagged)} ticket(s) 'zumbi' movidos p/ blocked</b>",
             "\nPreso em in_progress sem avanço — precisa de você no Magneto:"]
    for t in flagged[:_MAX_ITEMS]:
        lines.append(f"  • {_esc(str(t['title']))} ({_esc(str(t['assignee_agent'] or '?'))})")
    if len(flagged) > _MAX_ITEMS:
        lines.append(f"  … e mais {len(flagged) - _MAX_ITEMS}")
    return "\n".join(lines)


def tick() -> dict:
    """Uma varredura. Marca zumbis de in_progress como blocked + alerta."""
    minutes = int(os.environ.get("STALE_TICKET_MINUTES", "60"))
    if not DB_PATH.exists():
        return {"error": "db not found", "flagged": 0, "alerted": False}

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        stale = _stale_in_progress(conn, minutes)
        flagged = []
        for t in stale:
            _flag_blocked(conn, t)
            flagged.append({"id": t["id"], "title": t["title"], "assignee_agent": t["assignee_agent"]})
        conn.commit()
    finally:
        conn.close()

    alerted = False
    if flagged:
        try:
            from notifications import send_telegram_alert
            alerted = send_telegram_alert(_build_alert(flagged))
        except Exception as exc:  # noqa: BLE001
            log.warning("stale_ticket_sweep alert failed: %s", exc)

    log.info("stale_ticket_sweep.tick: flagged=%d alerted=%s (threshold=%dmin)",
             len(flagged), alerted, minutes)
    return {"flagged": len(flagged), "alerted": alerted, "threshold_minutes": minutes}
