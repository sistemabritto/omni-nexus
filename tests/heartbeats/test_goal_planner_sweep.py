"""Tests for goal-planner's Python-side sweep pick and the step8_persist
ON CONFLICT fix — see memory `goals-decomposicao-quebrada-2026-09-11`.

Root cause recap: goal_created never fired for goals created before the
goal-planner heartbeat row existed, and the one real trigger that did fire
failed mid-run with no retry. The interval/manual fallback used to delegate
"which goal is due" to the LLM under a tight timeout, and the one real
execution of that prompt picked the wrong goal. These tests cover the
deterministic Python replacement instead.
"""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from heartbeat_runner import pick_orphan_goal_for_sweep, step8_persist  # noqa: E402


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE goals (
            id INTEGER PRIMARY KEY,
            parent_goal_id INTEGER,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE tickets (
            id TEXT PRIMARY KEY,
            goal_id INTEGER
        );
        CREATE TABLE heartbeat_runs (
            run_id TEXT PRIMARY KEY,
            heartbeat_id TEXT NOT NULL,
            trigger_id TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_ms INTEGER,
            tokens_in INTEGER,
            tokens_out INTEGER,
            cost_usd REAL,
            status TEXT NOT NULL DEFAULT 'running',
            prompt_preview TEXT,
            error TEXT,
            triggered_by TEXT
        );
    """)
    yield c
    c.close()


def _goal(conn, id, status="active", parent_goal_id=None, created_at=None):
    conn.execute(
        "INSERT INTO goals (id, parent_goal_id, status, created_at) VALUES (?, ?, ?, ?)",
        (id, parent_goal_id, status, created_at or f"2026-0{id}-01T00:00:00Z"),
    )


def _ticket(conn, goal_id):
    conn.execute("INSERT INTO tickets (id, goal_id) VALUES (?, ?)", (f"t-{goal_id}-{id(conn)}", goal_id))


class TestPickOrphanGoalForSweep:
    def test_picks_oldest_undecomposed_active_top_level_goal(self, conn):
        # goal 3 is older than goal 9, both orphaned — must pick 3, not 9
        # (this is the exact regression the LLM-driven sweep hit for real on
        # 2026-09-11: it picked 9 over the older, still-orphaned 3).
        _goal(conn, 3, created_at="2026-06-15T21:58:05Z")
        _goal(conn, 9, created_at="2026-07-27T19:08:17Z")
        conn.commit()

        assert pick_orphan_goal_for_sweep(conn) == 3

    def test_skips_goal_with_existing_tickets(self, conn):
        _goal(conn, 1, created_at="2026-01-01T00:00:00Z")
        _ticket(conn, 1)
        _goal(conn, 2, created_at="2026-02-01T00:00:00Z")
        conn.commit()

        assert pick_orphan_goal_for_sweep(conn) == 2

    def test_skips_goal_with_existing_sub_goals(self, conn):
        _goal(conn, 1, created_at="2026-01-01T00:00:00Z")
        _goal(conn, 2, parent_goal_id=1, created_at="2026-01-02T00:00:00Z")
        _goal(conn, 3, created_at="2026-02-01T00:00:00Z")
        conn.commit()

        # goal 1 has a sub-goal already (proposed decomposition) — not orphaned
        assert pick_orphan_goal_for_sweep(conn) == 3

    def test_skips_non_active_and_sub_goals_themselves(self, conn):
        _goal(conn, 1, status="achieved", created_at="2026-01-01T00:00:00Z")
        _goal(conn, 2, parent_goal_id=1, status="active", created_at="2026-01-02T00:00:00Z")
        conn.commit()

        # goal 2 is a sub-goal (parent_goal_id set) — never picked by the
        # top-level sweep, mirrors goal-planner's own "never re-trigger on
        # sub-goal creation" rule (ADR SPEC 5b)
        assert pick_orphan_goal_for_sweep(conn) is None

    def test_returns_none_when_nothing_pending(self, conn):
        _goal(conn, 1, created_at="2026-01-01T00:00:00Z")
        _ticket(conn, 1)
        conn.commit()

        assert pick_orphan_goal_for_sweep(conn) is None


class TestStep8PersistUpdatesTelemetryOnConflict:
    def test_final_persist_overwrites_initial_running_row(self, conn):
        """The initial INSERT (status='running') has no prompt_preview/cost_usd.
        step8_persist's final call must not leave those NULL forever — the bug
        that made prompt_preview/cost_usd empty on all 20k+ historical rows."""
        run_id = "r1"
        now = _now_iso()
        conn.execute(
            """INSERT INTO heartbeat_runs (run_id, heartbeat_id, started_at, status, triggered_by)
               VALUES (?, 'goal-planner', ?, 'running', 'interval')""",
            (run_id, now),
        )
        conn.commit()

        result = {
            "status": "success", "error": None, "agent": "goal-planner",
            "duration_ms": 12345, "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.0042,
            "started_at": now,
        }
        step8_persist(run_id, "goal-planner", result, None, "interval", "the real prompt text", conn)

        row = dict(conn.execute("SELECT * FROM heartbeat_runs WHERE run_id=?", (run_id,)).fetchone())
        assert row["prompt_preview"] == "the real prompt text"
        assert row["cost_usd"] == 0.0042
        assert row["tokens_in"] == 100
        assert row["tokens_out"] == 50
        assert row["status"] == "success"
