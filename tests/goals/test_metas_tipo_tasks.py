"""
tests/goals/test_metas_tipo_tasks.py

2026-07-26 — metas `metric_type='tasks'` congelaram em junho.

`_recompute_goal_from_tickets` só recalculava metas `count`. O `tasks` conta
exatamente a mesma coisa — tarefas concluídas, que hoje são tickets — mas ficou
de fora do guard. Como `goal_tasks` foi congelado no goal-ticket-unification,
NADA passou a escrever nessas metas.

O estrago medido na VPS:
  - `pipeline-reels-vertical-pronto`: achieved com current_value=7 e ZERO
    tickets. O pipeline de vídeo nem existe.
  - `reports-whatsapp-operacionais`: 5/5 achieved com 4 tickets reais.
  - `evonexus-self-heal`: 2 gravado contra 3 reais — trabalho feito que não
    contou.

Run:
    pytest tests/goals/test_metas_tipo_tasks.py -v
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import heartbeat_outcome as ho  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE goals (
            id INTEGER PRIMARY KEY, project_id INTEGER, metric_type TEXT,
            current_value REAL DEFAULT 0, target_value REAL, status TEXT,
            completed_at TEXT, updated_at TEXT
        );
        CREATE TABLE tickets (id TEXT PRIMARY KEY, goal_id INTEGER, status TEXT);
        CREATE TABLE projects (id INTEGER PRIMARY KEY, status TEXT, completed_at TEXT, updated_at TEXT);
    """)
    return c


def _meta(conn, *, id, tipo, valor, alvo, status="active", projeto=1):
    conn.execute(
        "INSERT INTO goals (id, project_id, metric_type, current_value, target_value, status)"
        " VALUES (?,?,?,?,?,?)", (id, projeto, tipo, valor, alvo, status))
    conn.execute("INSERT OR IGNORE INTO projects (id, status) VALUES (?, 'active')", (projeto,))


def _tickets(conn, goal_id, *estados):
    for i, e in enumerate(estados):
        conn.execute("INSERT INTO tickets (id, goal_id, status) VALUES (?,?,?)",
                     (f"t{goal_id}-{i}", goal_id, e))


def _valor(conn, goal_id):
    return conn.execute("SELECT current_value, status FROM goals WHERE id=?", (goal_id,)).fetchone()


# ── o caso real da VPS ───────────────────────────────────────────────────

def test_meta_tasks_inflada_sem_ticket_algum_e_zerada(conn):
    """pipeline-reels-vertical-pronto: achieved com 7 pontos e nenhum ticket."""
    _meta(conn, id=3, tipo="tasks", valor=7, alvo=1, status="achieved")
    ho._recompute_goal_from_tickets(3, conn)
    linha = _valor(conn, 3)
    assert linha["current_value"] == 0
    assert linha["status"] == "active", "meta sem trabalho nenhum não pode seguir cumprida"


def test_meta_tasks_por_um_ponto_inexistente_reabre(conn):
    """reports-whatsapp: 5/5 achieved com 4 tickets reais."""
    _meta(conn, id=5, tipo="tasks", valor=5, alvo=5, status="achieved")
    _tickets(conn, 5, "resolved", "resolved", "resolved", "closed")
    ho._recompute_goal_from_tickets(5, conn)
    linha = _valor(conn, 5)
    assert linha["current_value"] == 4
    assert linha["status"] == "active"


def test_meta_tasks_subestimada_sobe(conn):
    """evonexus-self-heal: 2 gravado, 3 reais — trabalho feito que não contava."""
    _meta(conn, id=6, tipo="tasks", valor=2, alvo=11)
    _tickets(conn, 6, "resolved", "resolved", "closed")
    assert _valor(conn, 6)["current_value"] == 2
    ho._recompute_goal_from_tickets(6, conn)
    assert _valor(conn, 6)["current_value"] == 3


def test_meta_tasks_legitimamente_cumprida_continua_cumprida(conn):
    """autopilot-ferias: 10/10 com 10 tickets — a reconciliação não pode punir
    quem estava certo."""
    _meta(conn, id=4, tipo="tasks", valor=10, alvo=10, status="achieved")
    _tickets(conn, 4, *["resolved"] * 10)
    ho._recompute_goal_from_tickets(4, conn)
    linha = _valor(conn, 4)
    assert linha["current_value"] == 10
    assert linha["status"] == "achieved"


# ── count continua funcionando ───────────────────────────────────────────

def test_count_nao_regrediu(conn):
    _meta(conn, id=8, tipo="count", valor=0, alvo=3)
    _tickets(conn, 8, "resolved", "resolved", "resolved")
    ho._recompute_goal_from_tickets(8, conn)
    assert _valor(conn, 8)["status"] == "achieved"


# ── os tipos que precisam continuar de fora ──────────────────────────────

@pytest.mark.parametrize("tipo,valor", [
    ("currency", 45000.0),
    ("percentage", 87.5),
    ("boolean", 1.0),
])
def test_tipos_com_valor_proprio_nao_sao_tocados(conn, tipo, valor):
    """Contar tickets aqui destruiria o dado: R$ 45.000 de MRR viraria 1 na
    primeira transição de status."""
    _meta(conn, id=20, tipo=tipo, valor=valor, alvo=100000)
    _tickets(conn, 20, "resolved")
    ho._recompute_goal_from_tickets(20, conn)
    assert _valor(conn, 20)["current_value"] == valor


# ── idempotência e bordas ────────────────────────────────────────────────

def test_recalcular_duas_vezes_da_o_mesmo(conn):
    _meta(conn, id=6, tipo="tasks", valor=99, alvo=11)
    _tickets(conn, 6, "resolved", "resolved")
    ho._recompute_goal_from_tickets(6, conn)
    primeiro = _valor(conn, 6)["current_value"]
    ho._recompute_goal_from_tickets(6, conn)
    assert _valor(conn, 6)["current_value"] == primeiro == 2


def test_ticket_reaberto_derruba_a_meta_de_volta(conn):
    """Drift ao contrário: meta cumprida cujo ticket voltou a abrir."""
    _meta(conn, id=9, tipo="tasks", valor=2, alvo=2, status="achieved")
    _tickets(conn, 9, "resolved", "resolved")
    ho._recompute_goal_from_tickets(9, conn)
    assert _valor(conn, 9)["status"] == "achieved"

    conn.execute("UPDATE tickets SET status='in_progress' WHERE id='t9-0'")
    ho._recompute_goal_from_tickets(9, conn)
    linha = _valor(conn, 9)
    assert linha["current_value"] == 1
    assert linha["status"] == "active"


def test_ticket_nao_terminal_nao_conta(conn):
    _meta(conn, id=10, tipo="tasks", valor=0, alvo=5)
    _tickets(conn, 10, "open", "in_progress", "blocked", "review")
    ho._recompute_goal_from_tickets(10, conn)
    assert _valor(conn, 10)["current_value"] == 0


def test_meta_inexistente_nao_quebra(conn):
    ho._recompute_goal_from_tickets(999, conn)


def test_goal_id_nulo_nao_quebra(conn):
    ho._recompute_goal_from_tickets(None, conn)
