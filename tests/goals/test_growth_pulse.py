"""
tests/goals/test_growth_pulse.py

Auditoria heartbeats/goals 2026-09-11: o Pulse agregava heartbeat de infra
(roda a cada 15-30min, quase nunca falha) com heartbeat de agente (roda
1x/dia, é o que de fato move trabalho) na mesma taxa de sucesso — um
goal-planner que falhou sua única execução do dia virava ruído estatístico
num "98% ok" dominado por infra. E o Pulse nunca mencionava Goals, então
uma meta vencida só era descoberta abrindo /goals na mão.

generate_pulse() agora separa os dois buckets de heartbeat e soma um bloco
de Goals ativos/vencidos.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTINES_DIR = REPO_ROOT / "ADWs" / "routines"
sys.path.insert(0, str(ROUTINES_DIR))

import growth_pulse  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_file = tmp_path / "growth_pulse_test.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(
        """
        CREATE TABLE heartbeats (id TEXT PRIMARY KEY, agent TEXT, handler TEXT);
        CREATE TABLE heartbeat_runs (
            run_id TEXT PRIMARY KEY, heartbeat_id TEXT, status TEXT, started_at TEXT
        );
        CREATE TABLE tickets (id TEXT PRIMARY KEY, status TEXT, priority TEXT);
        CREATE TABLE goals (id INTEGER PRIMARY KEY, status TEXT, due_date TEXT);
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(growth_pulse, "DB_PATH", db_file)
    # Sem essas envs a seção de integrações marca has_critical=True por
    # motivo alheio ao teste — fixa presentes pra isolar o que se testa.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("EVOLUTION_GO_URL", "x")
    monkeypatch.setattr(growth_pulse, "_load_metrics", lambda: {})
    return db_file


def _conn(db_file):
    c = sqlite3.connect(str(db_file))
    c.row_factory = sqlite3.Row
    return c


def _insert_heartbeat(conn, hb_id, agent, handler=None):
    conn.execute("INSERT INTO heartbeats (id, agent, handler) VALUES (?, ?, ?)", (hb_id, agent, handler))


def _insert_run(conn, hb_id, status, started_at=None):
    started_at = started_at or _iso(datetime.now(timezone.utc))
    conn.execute(
        "INSERT INTO heartbeat_runs (run_id, heartbeat_id, status, started_at) VALUES (?, ?, ?, ?)",
        (f"{hb_id}-{status}-{started_at}", hb_id, status, started_at),
    )


def test_infra_and_agent_heartbeats_reported_separately(db):
    conn = _conn(db)
    _insert_heartbeat(conn, "nexus-orchestrator", "system", "nexus_orchestrator.tick")
    for _ in range(20):
        _insert_run(conn, "nexus-orchestrator", "success")

    _insert_heartbeat(conn, "goal-planner", "goal-planner", None)
    _insert_run(conn, "goal-planner", "fail")
    conn.commit()
    conn.close()

    text, has_critical = growth_pulse.generate_pulse()

    assert "Heartbeats infra: 20 ok" in text
    assert "Heartbeats agente: <b>0 ok / 1 fail" in text
    # Um heartbeat de agente falhando é crítico mesmo sendo só 1 execução —
    # a taxa agregada (95%+) não pode esconder isso.
    assert has_critical is True


def test_single_agent_failure_is_critical_even_with_many_infra_successes(db):
    """A regressão original: 1 fail em ~150 runs (infra+agente somados)
    não batia o limiar de >=3 e o Pulse reportava tudo tranquilo."""
    conn = _conn(db)
    _insert_heartbeat(conn, "integrations-health", "system", "plugin_integration_health.tick")
    for _ in range(148):
        _insert_run(conn, "integrations-health", "success")
    _insert_heartbeat(conn, "pixel-growth-6h", "pixel-social-media", None)
    _insert_run(conn, "pixel-growth-6h", "fail")
    conn.commit()
    conn.close()

    _, has_critical = growth_pulse.generate_pulse()
    assert has_critical is True


def test_infra_failures_need_at_least_three_to_be_critical(db):
    conn = _conn(db)
    _insert_heartbeat(conn, "integrations-health", "system", "plugin_integration_health.tick")
    _insert_run(conn, "integrations-health", "fail")
    _insert_run(conn, "integrations-health", "success")
    conn.commit()
    conn.close()

    text, has_critical = growth_pulse.generate_pulse()
    assert "Heartbeats infra: 1 ok / 1 fail" in text
    assert has_critical is False


def test_no_heartbeats_today_shows_zero_without_error(db):
    text, has_critical = growth_pulse.generate_pulse()
    assert "Heartbeats infra: 0 ok / 0 fail" in text
    assert "Heartbeats agente: <b>0 ok / 0 fail" in text
    assert has_critical is False


def test_goals_block_reports_active_count(db):
    conn = _conn(db)
    conn.execute("INSERT INTO goals (id, status, due_date) VALUES (1, 'active', NULL)")
    conn.execute("INSERT INTO goals (id, status, due_date) VALUES (2, 'achieved', NULL)")
    conn.commit()
    conn.close()

    text, has_critical = growth_pulse.generate_pulse()
    assert "Goals ativos: <b>1</b>" in text
    assert has_critical is False


def test_goals_block_flags_overdue_goal_as_critical(db):
    conn = _conn(db)
    conn.execute("INSERT INTO goals (id, status, due_date) VALUES (1, 'active', '2020-01-01')")
    conn.commit()
    conn.close()

    text, has_critical = growth_pulse.generate_pulse()
    assert "1 vencida" in text
    assert has_critical is True


def test_no_active_goals_says_so_without_alarm(db):
    text, has_critical = growth_pulse.generate_pulse()
    assert "Goals: nenhum ativo" in text
    assert has_critical is False
