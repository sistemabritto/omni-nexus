"""
tests/heartbeats/test_deadline_check.py

Panorama 2026-07-17, item 4 — nothing proactively alerted on an overdue Goal
or Ticket between Weekly Review runs (Fridays only). deadline_check.tick()
closes that gap: a cheap, LLM-free heartbeat handler that checks due_date
and alerts via Telegram.

Run:
    cd /path/to/workspace && pytest tests/heartbeats/test_deadline_check.py -v
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import deadline_check  # noqa: E402
from heartbeat_schema import HeartbeatConfig  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_file = tmp_path / "deadline_test.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(
        """
        CREATE TABLE goals (id INTEGER PRIMARY KEY, title TEXT, status TEXT, due_date TEXT);
        CREATE TABLE tickets (id TEXT PRIMARY KEY, title TEXT, status TEXT, due_date TEXT, updated_at TEXT);
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(deadline_check, "DB_PATH", db_file)
    return db_file


def _conn(db_file):
    c = sqlite3.connect(str(db_file))
    c.row_factory = sqlite3.Row
    return c


def test_no_overdue_items_does_not_alert(db):
    with patch("notifications.send_telegram_alert") as mock_alert:
        result = deadline_check.tick()
    mock_alert.assert_not_called()
    assert result == {"overdue_goals": 0, "overdue_tickets": 0, "stale_blocked_tickets": 0, "alerted": False}


def test_overdue_goal_triggers_alert(db):
    conn = _conn(db)
    conn.execute("INSERT INTO goals (id, title, status, due_date) VALUES (1, 'Meta vencida', 'active', '2020-01-01')")
    conn.commit()
    conn.close()

    with patch("notifications.send_telegram_alert", return_value=True) as mock_alert:
        result = deadline_check.tick()

    mock_alert.assert_called_once()
    body = mock_alert.call_args[0][0]
    assert "Meta vencida" in body
    assert result["overdue_goals"] == 1
    assert result["alerted"] is True


def test_overdue_ticket_triggers_alert(db):
    conn = _conn(db)
    conn.execute("INSERT INTO tickets (id, title, status, due_date) VALUES ('t1', 'Ticket vencido', 'open', '2020-01-01')")
    conn.commit()
    conn.close()

    with patch("notifications.send_telegram_alert", return_value=True) as mock_alert:
        result = deadline_check.tick()

    body = mock_alert.call_args[0][0]
    assert "Ticket vencido" in body
    assert result["overdue_tickets"] == 1


def test_achieved_goal_past_due_date_is_ignored(db):
    """Only status='active' Goals count — an achieved Goal keeping an old
    due_date must never trigger a false alarm."""
    conn = _conn(db)
    conn.execute("INSERT INTO goals (id, title, status, due_date) VALUES (1, 'Meta feita', 'achieved', '2020-01-01')")
    conn.commit()
    conn.close()

    with patch("notifications.send_telegram_alert") as mock_alert:
        result = deadline_check.tick()
    mock_alert.assert_not_called()
    assert result["overdue_goals"] == 0


def test_resolved_ticket_past_due_date_is_ignored(db):
    conn = _conn(db)
    conn.execute("INSERT INTO tickets (id, title, status, due_date) VALUES ('t1', 'Ticket feito', 'resolved', '2020-01-01')")
    conn.commit()
    conn.close()

    with patch("notifications.send_telegram_alert") as mock_alert:
        result = deadline_check.tick()
    mock_alert.assert_not_called()


def test_future_due_date_does_not_alert(db):
    conn = _conn(db)
    conn.execute("INSERT INTO goals (id, title, status, due_date) VALUES (1, 'Meta no futuro', 'active', '2099-01-01')")
    conn.commit()
    conn.close()

    with patch("notifications.send_telegram_alert") as mock_alert:
        deadline_check.tick()
    mock_alert.assert_not_called()


def test_stale_blocked_ticket_without_due_date_triggers_alert(db):
    """A blocked ticket with no due_date (the common case — an
    auto-generated diagnostic, not a deadline) must still surface once it's
    sat unaddressed past _STALE_BLOCKED_DAYS — this is the gap
    _overdue_tickets alone leaves open."""
    conn = _conn(db)
    conn.execute(
        "INSERT INTO tickets (id, title, status, due_date, updated_at) "
        "VALUES ('t1', 'Funil: 87% de perda', 'blocked', NULL, datetime('now', '-10 days'))"
    )
    conn.commit()
    conn.close()

    with patch("notifications.send_telegram_alert", return_value=True) as mock_alert:
        result = deadline_check.tick()

    mock_alert.assert_called_once()
    body = mock_alert.call_args[0][0]
    assert "Funil: 87% de perda" in body
    assert result["stale_blocked_tickets"] == 1
    assert result["alerted"] is True


def test_recently_blocked_ticket_does_not_alert(db):
    """A ticket blocked yesterday hasn't earned a nudge yet."""
    conn = _conn(db)
    conn.execute(
        "INSERT INTO tickets (id, title, status, due_date, updated_at) "
        "VALUES ('t1', 'Bloqueado ontem', 'blocked', NULL, datetime('now', '-1 days'))"
    )
    conn.commit()
    conn.close()

    with patch("notifications.send_telegram_alert") as mock_alert:
        result = deadline_check.tick()
    mock_alert.assert_not_called()
    assert result["stale_blocked_tickets"] == 0


def test_stale_blocked_ticket_with_due_date_is_not_double_counted(db):
    """A blocked ticket that DOES have a due_date is already covered by
    _overdue_tickets — _stale_blocked_tickets must not also pick it up and
    list it twice in the same alert."""
    conn = _conn(db)
    conn.execute(
        "INSERT INTO tickets (id, title, status, due_date, updated_at) "
        "VALUES ('t1', 'Vencido com prazo', 'blocked', '2020-01-01', datetime('now', '-10 days'))"
    )
    conn.commit()
    conn.close()

    with patch("notifications.send_telegram_alert", return_value=True):
        result = deadline_check.tick()
    assert result["overdue_tickets"] == 1
    assert result["stale_blocked_tickets"] == 0


def test_missing_db_returns_error_without_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(deadline_check, "DB_PATH", tmp_path / "does-not-exist.db")
    result = deadline_check.tick()
    assert result["error"] == "db not found"


def test_deadline_check_heartbeat_seed_validates():
    data = yaml.safe_load((REPO_ROOT / "config" / "heartbeats.example.yaml").read_text())
    heartbeats = [HeartbeatConfig(**hb) for hb in data["heartbeats"]]
    hb = next(h for h in heartbeats if h.id == "deadline-check")
    assert hb.handler == "deadline_check.tick"
    assert hb.max_turns == 0
    assert hb.enabled is False
