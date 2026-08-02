"""Data retention — janitor de crescimento da base.

O `heartbeat_runs` cresce sem limite (12k+ linhas em ~60 dias) e o `audit_log`
idem. Cada run/heartbeat serve para o painel e o Growth Pulse; histórico mais
velho que a janela não acrescenta e só incha o SQLite (315MB na VPS em 02/08).

Rodar a cada 6h, em thread daemon, in-process no dashboard (que é dono do DB).
Nunca apagar pendente/recente: só o que passou da retenção.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

RETENCAO_HEARTBEATS_DIAS = int(os.environ.get("RETENCAO_HEARTBEATS_DIAS", "90"))
RETENCAO_AUDIT_DIAS = int(os.environ.get("RETENCAO_AUDIT_DIAS", "180"))
INTERVALO_SEG = 6 * 3600

DB_PATH = Path(__file__).resolve().parents[2] / "dashboard" / "data" / "evonexus.db"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def limpar(conn: sqlite3.Connection) -> tuple[int, int]:
    """Apaga heartbeat_runs e audit_log fora da retenção. Devolve (runs, audit).

    Usa sqlite direto (como heartbeat_dispatcher), não db.engine: o janitor
    roda em thread sem app context do Flask, e o scheduler não monta o volume.
    """
    corte_hb = (datetime.now(timezone.utc) - timedelta(days=RETENCAO_HEARTBEATS_DIAS)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    corte_audit = (datetime.now(timezone.utc) - timedelta(days=RETENCAO_AUDIT_DIAS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    # Nunca apagar run pendente/running — encerrar um zumbi seria mascarar o
    # problema, e apagar um run em andamento perde o custo em aberto.
    runs = conn.execute(
        "DELETE FROM heartbeat_runs WHERE started_at < ? AND status NOT IN ('running', 'busy')",
        (corte_hb,),
    ).rowcount
    audit = 0
    try:
        audit = conn.execute(
            "DELETE FROM audit_log WHERE created_at < ?", (corte_audit,)
        ).rowcount
    except Exception as exc:  # noqa: BLE001 — coluna pode ter outro nome
        log.warning("audit_log purge falhou (não-bloqueante): %s", exc)
    conn.commit()
    return runs, audit


def run_once() -> tuple[int, int] | None:
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        try:
            return limpar(conn)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("data_retention falhou: %s", exc)
        return None


def start_janitor_thread() -> threading.Thread:
    def _loop() -> None:
        while True:
            try:
                runs, audit = run_once() or (0, 0)
                if runs or audit:
                    log.info("data_retention: purgei %d heartbeat_runs, %d audit_log", runs, audit)
            except Exception:  # noqa: BLE001
                log.exception("data_retention ciclagem falhou")
            time.sleep(INTERVALO_SEG)

    t = threading.Thread(target=_loop, name="data-retention", daemon=True)
    t.start()
    log.info("data_retention janitor started (hb=%dd, audit=%dd)", RETENCAO_HEARTBEATS_DIAS, RETENCAO_AUDIT_DIAS)
    return t
