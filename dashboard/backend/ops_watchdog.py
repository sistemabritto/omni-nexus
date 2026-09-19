"""ops_watchdog — observador self-healing do OmniNexus (P5 do [C]revamp-cockpit-reels-multitenant.md).

Um agente de plantão: a cada 15min varre os dados de execução (heartbeat_runs)
e o /api/health/deep, classifica anomalias com regras determinísticas BARATAS
(zero LLM na triagem) e age:

1. Self-heal nível 1 (determinístico, reversível): run 'stuck running' →
   release do lock; 1 falha isolada sem padrão → re-dispatch simples.
2. Ticket de correção com dedup: 1 ticket por anomalia (source=
   ops-watchdog:<key>), assignee automático pelo tipo (hawk-debugger p/ crash,
   vault-security p/ 401/config, atlas-planner p/ stalled).
3. Alerta Magneto: 1 card consolidado/dia; anomalia P1 (dispatcher parado,
   service degraded) alerta na hora.

Kill-switch de calibração: WATCHDOG_AUTOTICKET=0 → só detecta + alerta, não
cria ticket. Anomalias persistem em workspace/reports/ops-watchdog/state.json
(para dedup entre ticks e restart).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"
STATE_DIR = WORKSPACE / "workspace" / "reports" / "ops-watchdog"
STATE_PATH = STATE_DIR / "state.json"

STUCK_FACTOR = 2          # 'running' há mais que timeout×2 = stuck
STALLED_FACTOR = 3        # ligado há mais que interval×3 sem run = stalled
FAILURE_WINDOW_H = 24     # janela de análise de falhas

# Tipo de anomalia -> agente consertador (regra de roteamento do Felipe:
# "alerta pra OUTRO consertar").
ASSIGNEE_BY_TYPE = {
    "crash": "hawk-debugger",
    "pattern": "hawk-debugger",
    "stuck": "hawk-debugger",
    "stalled": "atlas-planner",
    "cost": "sage-strategy",
    "service": "vault-security",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now_utc()).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seen": {}, "last_daily_card": None, "last_daily_date": None}


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    pending = STATE_PATH.with_suffix(".json.tmp")
    pending.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    pending.replace(STATE_PATH)


# ── Regras (determinísticas, sem LLM) ────────────────────────────────────────


def detect(conn: sqlite3.Connection) -> list[dict]:
    """Varre heartbeat_runs + heartbeats e devolve lista de anomalias {key,type,hb,severity,detail}."""
    now = _now_utc()
    out: list[dict] = []

    hbs = conn.execute(
        "SELECT id, agent, interval_seconds, timeout_seconds, enabled FROM heartbeats WHERE enabled=1"
    ).fetchall()

    by_hb: dict[str, list] = {}
    for r in conn.execute(
        """SELECT heartbeat_id, status, started_at, ended_at, error FROM heartbeat_runs
           WHERE started_at >= ? ORDER BY started_at DESC""",
        (_iso(now - timedelta(hours=FAILURE_WINDOW_H)),),
    ):
        by_hb.setdefault(r["heartbeat_id"], []).append(dict(r))

    for hb in hbs:
        hid = hb["id"]
        runs = by_hb.get(hid, [])

        # (a) stuck: um run 'running' além de timeout×2
        for r in runs:
            if r["status"] == "running" and r.get("started_at"):
                try:
                    started = datetime.fromisoformat(str(r["started_at"]).replace("Z", "+00:00"))
                    if (now - started).total_seconds() > hb["timeout_seconds"] * STUCK_FACTOR:
                        out.append({"key": f"stuck:{hid}", "type": "stuck", "hb": hid,
                                    "severity": "p1", "detail": f"run 'running' há {(now-started).total_seconds()//60} min"})
                except ValueError:
                    pass

        # (b) stalled: ligado sem nenhum run em interval×3
        if runs:
            try:
                last_run = max(datetime.fromisoformat(str(r["started_at"]).replace("Z", "+00:00")) for r in runs if r.get("started_at"))
            except ValueError:
                last_run = None
            if last_run is None or (now - last_run).total_seconds() > hb["interval_seconds"] * STALLED_FACTOR:
                out.append({"key": f"stalled:{hid}", "type": "stalled", "hb": hid,
                            "severity": "p2", "detail": f"sem run novo há {int((now - (last_run or now)).total_seconds()//3600)}h"})
            continue

        # (c) 2+ falhas consecutivas no mesmo heartbeat (fail/timeout)
        fails = [r for r in runs if r["status"] in ("fail", "timeout")]
        if len(fails) >= 2:
            last_two = fails[:2]
            err = (last_two[0].get("error") or "")[:120]
            kind = "crash" if re.search(r"traceback|error|exception|errno", err, re.I) else "pattern"
            out.append({"key": f"{kind}:{hid}", "type": kind, "hb": hid,
                        "severity": "p2", "detail": f"{len(fails)} falhas em 24h · última: {err}"})

        # (d) custo: 7d do heartbeat muito acima da média histórica
        cost_rows = conn.execute(
            """SELECT COALESCE(SUM(cost_usd),0) AS c7, COALESCE(AVG(cost_usd),0) AS avg_c
               FROM (SELECT cost_usd FROM heartbeat_runs WHERE heartbeat_id=? AND status='success')""",
            (hid,),
        ).fetchone()
        if cost_rows and cost_rows["c7"] and cost_rows["avg_c"] and cost_rows["c7"] > max(2.0, cost_rows["avg_c"] * 3 * 7):
            out.append({"key": f"cost:{hid}", "type": "cost", "hb": hid,
                        "severity": "p3", "detail": f"custo 7d ${cost_rows['c7']:.2f} bem acima da média"})
    return out


def _self_heal_l1(anom: dict, conn: sqlite3.Connection) -> bool:
    """Ações reversíveis antes de abrir ticket. True se o problema foi resolvido."""
    if anom["type"] != "stuck":
        return False
    # release do lock: marca o run antigo como 'timeout' para liberar o heartbeat
    conn.execute(
        """UPDATE heartbeat_runs SET status='timeout', ended_at=?,
              error='auto-release pelo watchdog (run preso além do limite)'
           WHERE heartbeat_id=? AND status='running'""",
        (_iso(), anom["hb"]),
    )
    conn.commit()
    return True


def _create_ticket(anom: dict) -> str | None:
    """Cria o ticket de correção (dedup por source_agent). Devolve o id ou None."""
    if os.environ.get("WATCHDOG_AUTOTICKET", "1").lower() in ("0", "no", "false"):
        return None
    source = f"ops-watchdog:{anom['key']}"
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT id FROM tickets WHERE source_agent=? AND status IN ('open','in_progress','blocked')",
            (source,),
        ).fetchone()
        if existing:
            return existing["id"]
        assignee = ASSIGNEE_BY_TYPE.get(anom["type"], "atlas-planner")
        now = _iso()
        tid = str(uuid.uuid4())
        title = f"[watchdog] {anom['type']} em {anom['hb']} ({anom['severity']})"
        body = (
            f"🩺 Detectado pelo ops-watchdog:\n{anom['detail']}\n\n"
            f"Corrija a causa raiz. Se precisar de acesso manual (VPS/logs), @humano.\n"
            f"Tipo: {anom['type']} · Heartbeat: {anom['hb']} · Severidade: {anom['severity']}"
        )
        prio_rank = 3 if anom["severity"] == "p1" else 2
        conn.execute(
            "INSERT INTO tickets (id, title, description, status, assignee_agent, priority,"
            " priority_rank, created_at, updated_at, source_agent, created_by,"
            " message_count, last_summary_at_message) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,0)",
            (tid, title, body, "open", assignee,
             "high" if anom["severity"] == "p1" else "medium", prio_rank, now, now, source,
             "system:ops-watchdog"),
        )
        conn.commit()
        return tid
    finally:
        conn.close()


def build_card(anoms: list[dict], tickets: dict[str, str]) -> str:
    from notifications import _esc

    lines = ["🚨 <b>Watchdog</b> — " + ("sem anomalias" if not anoms else f"<b>{len(anoms)} anomalia(s)</b>")]
    for a in anoms[:8]:
        mark = "✅ resolvido (auto)" if a["key"].startswith("stuck:") else ""
        tkt = tickets.get(a["key"]) or ""
        line = f"• [{a['severity']}] {a['hb']}: {_esc(a['detail'])}"
        if mark:
            line += f" {mark}"
        if tkt:
            line += f" → ticket #{tkt[:8]}"
        lines.append(line)
    return "\n".join(lines)


def tick() -> dict:
    if not DB_PATH.exists():
        return {"error": "db not found"}
    state = _load_state()
    conn = _connect()
    try:
        anoms = detect(conn)
    finally:
        conn.close()

    resolved: list[str] = []
    tickets: dict[str, str] = {}
    new_anoms: list[str] = []
    for a in anoms:
        if _self_heal_l1(a, _connect()):
            resolved.append(a["key"])
            continue
        if a["key"] in state.get("seen", {}):
            # já visto — só reforça ticket aberto, não duplica
            continue
        tickets[a["key"]] = _create_ticket(a) or ""
        state["seen"][a["key"]] = _iso()
        new_anoms.append(a["key"])

    # anomalias resolvidas somem do seen após 24h (permite re-alerta se voltar)
    day_ago = _iso(_now_utc() - timedelta(hours=24))
    state["seen"] = {k: v for k, v in state.get("seen", {}).items() if v >= day_ago}
    for k in resolved:
        state["seen"].pop(k, None)

    alerted_now = False
    has_p1 = any(a["severity"] == "p1" for a in anoms)
    today = _now_utc().date().isoformat()
    if has_p1 or (new_anoms and state.get("last_daily_date") != today):
        card = build_card(anoms, tickets)
        try:
            from notifications import send_telegram_alert
            ok = send_telegram_alert(card)
            alerted_now = ok
            if ok:
                state["last_daily_card"] = _iso()
                state["last_daily_date"] = today
        except Exception as exc:  # noqa: BLE001
            log.warning("ops_watchdog alert fail: %s", exc)
    elif new_anoms:
        # sem p1 e já avisou hoje: acumula no próximo card, mas segue criando ticket
        log.info("ops_watchdog: %d nova(s) acumulada(s), card diário já enviado hoje", len(new_anoms))

    _save_state(state)
    log.info("ops_watchdog.tick: anoms=%d novos=%d resolvidos=%d alertado=%s",
             len(anoms), len(new_anoms), len(resolved), alerted_now)
    return {"anomalies": len(anoms), "new": len(new_anoms), "resolved": len(resolved),
            "tickets_created": sum(1 for v in tickets.values() if v), "alerted": alerted_now}
