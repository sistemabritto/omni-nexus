"""Bounded, model-free editorial heartbeat. Never publishes or messages leads."""
from __future__ import annotations

import fcntl
import html
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRT = timezone(timedelta(hours=-3))
START = datetime(2026, 9, 11, tzinfo=BRT)
END = START + timedelta(days=30)
REPORTS = ROOT / "workspace/reports/reels"
GROWTH = ROOT / "workspace/reports/growth/latest.json"
DB = ROOT / "dashboard/data/evonexus.db"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def publication_counts(data, now):
    """Only confirmed REELS, unique media IDs. Missing taxonomy is UNKNOWN."""
    source = data.get("sources", {}).get("instagram", {})
    media = source.get("data", {}).get("media")
    stamp = data.get("collected_at")
    if not isinstance(stamp, str):
        return None
    try:
        collected = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        age = (now - collected).total_seconds()
        if age < -300 or age > 2 * 3600 or source.get("status") != "ok":
            return None
        if source.get("data", {}).get("pagination_truncated") or not isinstance(media, list) or any(not r.get("media_product_type") for r in media):
            return None
        seen = {}
        for row in media:
            if row.get("media_product_type") != "REELS" or not row.get("id"):
                continue
            published = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).astimezone(BRT)
            if START <= published < min(END, now):
                seen[row["id"]] = published
        # A rolling 30-day collector cannot prove the entire cycle after it ends.
        covered_from = datetime.fromisoformat(data["start_inclusive"].replace("Z", "+00:00"))
        if now >= START and covered_from > START:
            return None
        return {"cycle": len(seen), "today": sum(t.date() == now.date() for t in seen.values()),
                "as_of": stamp, "coverage_end": data.get("end_exclusive")}
    except (ValueError, TypeError, KeyError):
        return None


def inspect(now):
    evidence = read_json(REPORTS / "published.json") or read_json(GROWTH)
    counts = publication_counts(evidence, now)
    issues = []
    try:
        with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as conn:
            rows = conn.execute("""SELECT h.id, h.interval_seconds,
                r.status, r.started_at FROM heartbeats h LEFT JOIN heartbeat_runs r
                ON r.run_id=(SELECT run_id FROM heartbeat_runs WHERE heartbeat_id=h.id
                ORDER BY started_at DESC LIMIT 1)
                WHERE h.enabled=1 AND h.id!='reels-producer'""").fetchall()
            for hid, interval, status, stamp in rows:
                if status in ("fail", "timeout", "error"):
                    issues.append(f"Heartbeat {hid}: {status}")
            approvals = conn.execute("SELECT COUNT(*) FROM pending_approvals WHERE status='pending'").fetchone()[0]
    except sqlite3.Error:
        issues.append("Banco operacional indisponível")
        approvals = None
    if counts is None:
        issues.append("Contagem de Reels não verificável: atualizar coleta/classificação; não assumir zero")
    days = max(0, min(30, (now.date() - START.date()).days))
    return {"checked_at": now.isoformat(), "cycle_start": START.date().isoformat(),
            "cycle_end_exclusive": END.date().isoformat(), "minimum": 120, "stretch": 150,
            "daily_minimum": 4, "expected_before_today": days * 4,
            "published": counts, "pending_approvals_all_workflows": approvals, "issues": sorted(issues)}


def render(report):
    counts = report["published"]
    progress = (f"{counts['cycle']}/120 Reels confirmados no ciclo; {counts['today']} hoje. "
                f"Coleta: {counts['as_of']} (não é leitura em tempo real).") if counts else "Publicações: INDISPONÍVEL, não zero."
    lines = ["🎬 Magneto · Coprodução Reels", "Ciclo: 11/09–10/10 · mínimo 4/dia · 120; estendida 150.",
             progress, f"Meta até ontem: {report['expected_before_today']}. Aprovações gerais pendentes: {report['pending_approvals_all_workflows']}.",
             "Hoje: 1 diagnóstico; 1 demonstração; 1 caso/objeção; 1 resposta a decisor.",
             "Próxima ação: escolha um tema comigo → gancho visual/falado + headline + estrutura de linguagem + prompt OpenReply.",
             "Antes do post: recompensa/link testados; campanha preparada; vincular media_id e confirmar ativação.",
             "Reserva proposta: 8 roteiros aprovados. Rascunhos NÃO contam como publicados."]
    lines.extend("⚠ " + item for item in report["issues"])
    return "\n".join(lines)


def tick():
    now = datetime.now(BRT)
    if now >= END + timedelta(days=1):
        return {"sent": False, "reason": "cycle ended; preserve final evidence and await next cycle"}
    REPORTS.mkdir(parents=True, exist_ok=True)
    with (REPORTS / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        report = inspect(now)
        body = render(report)
        state_path = REPORTS / "notification-state.json"
        state = read_json(state_path)
        # Persistent slot keys; restart does not resend. No healthy overnight pings.
        slot = f"{now.date()}-" + ("evening" if now.hour >= 20 else "morning")
        brief_due = 7 <= now.hour < 23 and state.get("slot") != slot
        issues_key = "|".join(report["issues"])
        alert_due = bool(issues_key) and issues_key != state.get("issues") and 7 <= now.hour < 23
        sent = False
        if brief_due or alert_due:
            from notifications import send_telegram_alert
            sent = send_telegram_alert(html.escape(body))
            if not sent:
                raise RuntimeError("Telegram recusou relatório editorial; retentar no próximo tick")
            state.update(slot=slot, issues=issues_key)
            state_path.write_text(json.dumps(state), encoding="utf-8")
        elif not issues_key and state.get("issues"):
            state["issues"] = ""
            state_path.write_text(json.dumps(state), encoding="utf-8")
        for filename, value in (("latest.json", json.dumps(report, ensure_ascii=False, indent=2)), ("latest.md", body)):
            pending = REPORTS / (filename + ".tmp")
            pending.write_text(value, encoding="utf-8")
            pending.replace(REPORTS / filename)
        return {"sent": sent, "issues": len(report["issues"]), "published": report["published"], "report": "workspace/reports/reels/latest.md"}
