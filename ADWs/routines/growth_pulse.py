#!/usr/bin/env python3
"""
ADWs/routines/growth_pulse.py — Pulse de Growth & Presence 2x/dia.

Substitui o hourly_report.py (que falhava por falta de DB/Telegram no
scheduler e mandava 12 mensagens/dia com baixa densidade). Este roda às
08:30 e 18:30 BRT, é 100% determinístico (zero chamadas a modelo) e
foca em sinais de captação de clientes e presença digital.

Coleta:
  - Heartbeats hoje (ok/fail/running, taxa de sucesso)
  - Tickets abertos/atribuídos (workload do time)
  - Aprovações pendentes (gargalo humano)
  - Rotinas hoje (quantas rodaram, quantas falharam)
  - Integrações críticas (Telegram, Evolution, Ghost, Postiz)
  - Custo de tokens hoje (se métricas disponíveis)

Envia via Telegram apenas 2x/dia + alertas críticos imediatos
(quando há falha persistente ou integração indisponível).

Usage:
    python3 growth_pulse.py                # gera e envia
    python3 growth_pulse.py --dry-run      # só imprime, não envia
    python3 growth_pulse.py --alert        # modo alerta (weet só se houver problema)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE / "dashboard" / "backend"))

DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"
METRICS_PATH = WORKSPACE / "ADWs" / "logs" / "metrics.json"
BRT_OFFSET = timedelta(hours=-3)


def _now_brt() -> datetime:
    return datetime.now(timezone(BRT_OFFSET))


def _get_db():
    import sqlite3
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _has_table(conn, table: str) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _safe_query(conn, sql, params=(), fallback=None):
    """Run a query; return fallback if table is missing or error."""
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return fallback or []


def _safe_scalar(conn, sql, params=(), fallback=0):
    try:
        return conn.execute(sql, params).fetchone()[0]
    except Exception:
        return fallback


def _load_metrics() -> dict:
    """Load metrics.json for cost data."""
    try:
        if METRICS_PATH.exists():
            return json.loads(METRICS_PATH.read_text())
    except Exception:
        pass
    return {}


def _load_env() -> None:
    """Load the shared config env when the scheduler has no process env."""
    env_path = WORKSPACE / "config" / ".env"
    if not env_path.is_file():
        env_path = WORKSPACE / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _cost_today(metrics: dict) -> float:
    """Sum cost of all entries from today."""
    if not metrics:
        return 0.0
    today = _now_brt().strftime("%Y-%m-%d")
    total = 0.0
    for key, val in metrics.items():
        if isinstance(val, dict):
            runs = val.get("runs_by_date", {})
            if isinstance(runs, dict):
                total += runs.get(today, {}).get("cost_usd", 0)
            else:
                # fallback: if last_run is today, use last_cost
                last = val.get("last_run", "")
                if last and last.startswith(today):
                    total += val.get("last_cost_usd", 0)
    return round(total, 4)


def generate_pulse() -> tuple[str, bool]:
    """Generate the pulse report. Returns (text, has_critical)."""
    conn = _get_db()
    now_brt = _now_brt()
    today_str = now_brt.strftime("%Y-%m-%d")
    today_utc = now_brt.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    has_critical = False

    lines = [
        f"📊 <b>Pulse Growth & Presence</b>",
        f"🕐 {now_brt.strftime('%d/%m %H:%M')} BRT",
        "",
    ]

    if conn is None:
        lines.append("⚠️ Banco do dashboard não montado no scheduler")
        lines.append("   → volume evonexus_dashboard_data ausente")
        has_critical = True
        conn and conn.close()
        return ("\n".join(lines), has_critical)

    # ── Heartbeats hoje, separado por infra vs. agente ──
    # Um 98% agregado esconde o que importa: heartbeats de sistema
    # (integrations-health, nexus-orchestrator, confirmar-publicacoes,
    # reels-producer — handler in-process, zero LLM, quase nunca falham)
    # rodam de 15 em 15 / 30 em 30 min e dominam a contagem. Um heartbeat
    # de agente (goal-planner, pixel-growth-6h, nex-sales-4h) que falhou a
    # ÚNICA execução do dia pesa 1 em ~150 no agregado — vira ruído
    # estatístico quando devia ser a manchete. Confirmado ao vivo em
    # 10-11/09/2026: goal-planner ficou 24h com sua única execução em
    # 'fail' e o Pulse agregado seguiu mostrando 98%/100% o tempo todo.
    if _has_table(conn, "heartbeat_runs") and _has_table(conn, "heartbeats"):
        hb_stats = _safe_query(
            conn,
            """SELECT
                   CASE WHEN h.agent = 'system' OR h.handler IS NOT NULL
                        THEN 'infra' ELSE 'agente' END AS bucket,
                   r.status, COUNT(*) as cnt
               FROM heartbeat_runs r
               JOIN heartbeats h ON h.id = r.heartbeat_id
               WHERE r.started_at > ?
               GROUP BY bucket, r.status""",
            (today_utc,),
        )
        buckets = {"infra": {}, "agente": {}}
        for r in hb_stats:
            buckets[r["bucket"]][r["status"]] = r["cnt"]

        def _fmt(bucket: dict) -> tuple[str, int, int]:
            ok = bucket.get("success", 0)
            fail = sum(bucket.get(s, 0) for s in ("fail", "timeout", "error"))
            running = bucket.get("running", 0)
            rate = f"{(ok / max(1, ok + fail) * 100):.0f}%" if (ok + fail) > 0 else "—"
            return f"{ok} ok / {fail} fail / {running} run | {rate}", ok, fail

        infra_line, _, infra_fail = _fmt(buckets["infra"])
        agente_line, agente_ok, agente_fail = _fmt(buckets["agente"])
        lines.append(f"🐍 Heartbeats infra: {infra_line}")
        lines.append(f"❤️ Heartbeats agente: <b>{agente_line}</b>")
        # Um agente é a manchete: qualquer falha aqui é crítica, mesmo 1
        # em 1 — é o oposto do critério de infra (só alerta em >=3), porque
        # infra roda dezenas de vezes ao dia e um blip isolado é ruído,
        # enquanto um heartbeat de agente pode rodar só 1x/dia.
        if agente_fail >= 1:
            has_critical = True
        if infra_fail >= 3:
            has_critical = True
    else:
        lines.append("❤️ Heartbeats: tabela não existe")
        has_critical = True

    # ── Tickets abertos ──
    if _has_table(conn, "tickets"):
        open_tickets = _safe_scalar(
            conn,
            "SELECT COUNT(*) FROM tickets WHERE status IN ('open','in_progress','review')",
        )
        urgent = _safe_scalar(
            conn,
            "SELECT COUNT(*) FROM tickets WHERE priority='urgent' AND status IN ('open','in_progress')",
        )
        lines.append(f"📝 Tickets abertos: <b>{open_tickets}</b>" + (f" ({urgent} urgentes)" if urgent else ""))
    else:
        lines.append("📝 Tickets: tabela não existe")

    # ── Goals ativos ──
    # Antes desta seção o Pulse nunca mencionava Goals — dava pra passar
    # meses com uma meta parada e o único jeito de saber era abrir /goals
    # na mão. Conta simples e determinística: quantas ativas, quantas
    # vencidas (due_date no passado, sem heartbeat próprio pra isso — o
    # deadline-check já alerta em tempo real, aqui é só o resumo do dia).
    if _has_table(conn, "goals"):
        active_goals = _safe_scalar(conn, "SELECT COUNT(*) FROM goals WHERE status='active'")
        overdue_goals = _safe_scalar(
            conn,
            "SELECT COUNT(*) FROM goals WHERE status='active' AND due_date IS NOT NULL AND due_date < date('now')",
        )
        if active_goals > 0:
            suffix = f" (<b>{overdue_goals} vencida(s)</b>)" if overdue_goals > 0 else ""
            lines.append(f"🎯 Goals ativos: <b>{active_goals}</b>{suffix}")
            if overdue_goals > 0:
                has_critical = True
        else:
            lines.append("🎯 Goals: nenhum ativo")

    # ── Aprovações pendentes ──
    if _has_table(conn, "approvals"):
        pending = _safe_scalar(conn, "SELECT COUNT(*) FROM approvals WHERE status='pending'")
        if pending > 0:
            lines.append(f"⏳ Aprovações pendentes: <b>{pending}</b>")
            has_critical = has_critical or pending > 5
        else:
            lines.append("✅ Aprovações: nenhuma pendente")

    # ── Heartbeats zumbis (rodando há mais de 2h) ──
    if _has_table(conn, "heartbeat_runs"):
        zombies = _safe_scalar(
            conn,
            "SELECT COUNT(*) FROM heartbeat_runs WHERE status='running' AND started_at < ?",
            ((now_brt - timedelta(hours=2)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),),
        )
        if zombies > 0:
            lines.append(f"🧟 Zumbis: <b>{zombies}</b> heartbeat(s) travados há 2h+")
            has_critical = True

    # ── Custo de tokens hoje ──
    metrics = _load_metrics()
    cost = _cost_today(metrics)
    if cost > 0:
        lines.append(f"💰 Tokens hoje: <b>US$ {cost:.2f}</b>")
    else:
        lines.append("💰 Custo: sem valor positivo registrado (não comprova custo zero)")

    # ── Integrações críticas ──
    # Verifica via env vars se as credenciais estão presentes
    integrations = []
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        integrations.append("✅ TG")
    else:
        integrations.append("❌ TG")
        has_critical = True
    if os.environ.get("EVOLUTION_GO_URL"):
        integrations.append("✅ WA")
    else:
        integrations.append("❌ WA")
        has_critical = True
    # Ghost e Postiz via config/providers ou env
    ghost_url = os.environ.get("GHOST_URL") or os.environ.get("GHOST_ADMIN_API_URL")
    integrations.append("✅ Ghost" if ghost_url else "— Ghost")
    postiz = os.environ.get("POSTIZ_URL")
    integrations.append("✅ Postiz" if postiz else "— Postiz")
    lines.append(f"🔌 Configuração presente (não teste de saúde): {' '.join(integrations)}")

    conn.close()

    # ── Próxima ação sugerida (determinística) ──
    lines.append("")
    if has_critical:
        lines.append("🚨 <b>Ação recomendada:</b> verificar itens críticos acima")
    else:
        lines.append("✅ Sem alerta nos sinais consultados; isto não valida todas as integrações")

    return ("\n".join(lines), has_critical)


def main():
    parser = argparse.ArgumentParser(description="Growth & Presence Pulse")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't send")
    parser.add_argument("--alert", action="store_true", help="Only send if critical")
    args = parser.parse_args()

    _load_env()

    text, has_critical = generate_pulse()

    if args.dry_run:
        print(text)
        print(f"\n[has_critical={has_critical}]")
        return 0

    # `notify_info()` escapa o corpo como texto literal, o que quebraria as
    # tags HTML que formatam este relatório. A rotina já monta conteúdo seguro
    # (contagens e valores próprios), então entrega pelo canal de alerta bruto.
    from notifications import send_telegram_alert
    if args.alert:
        # Modo alerta: só envia se houver problema.
        if has_critical:
            if not send_telegram_alert(text):
                return 1
            print("[growth_pulse] alert sent (critical)")
        else:
            print("[growth_pulse] no critical issues, skipping alert")
    else:
        # Pulse completo (2x/dia).
        if not send_telegram_alert(text):
            return 1
        print("[growth_pulse] pulse sent")

    return 0


if __name__ == "__main__":
    sys.exit(main())
