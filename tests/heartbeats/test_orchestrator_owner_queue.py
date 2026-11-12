"""An unavailable owner must not starve another agent's actionable queue."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
import nexus_orchestrator as orch


@pytest.fixture
def queue():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
      CREATE TABLE tickets (id TEXT, title TEXT, assignee_agent TEXT, priority TEXT,
        priority_rank INTEGER, goal_id INTEGER, status TEXT, locked_at TEXT,
        updated_at TEXT, created_at TEXT);
      CREATE TABLE goals (id INTEGER, status TEXT);
      CREATE TABLE heartbeats (id TEXT, agent TEXT, enabled INTEGER);
      INSERT INTO goals VALUES (1,'active');
      INSERT INTO tickets VALUES ('orphan','Unavailable owner','missing-owner','urgent',4,1,'open',NULL,NULL,'2020-01-01');
      INSERT INTO tickets VALUES ('ready','Actionable','ready-owner','medium',2,1,'open',NULL,NULL,'2020-01-02');
      INSERT INTO heartbeats VALUES ('autopilot-ready','ready-owner',1);
    ''')
    yield c
    c.close()


@pytest.mark.parametrize('heartbeat', ['missing', 'disabled'])
def test_owner_without_enabled_heartbeat_cannot_starve_next_ticket(queue, heartbeat):
    if heartbeat == 'disabled':
        queue.execute("INSERT INTO heartbeats VALUES ('off','missing-owner',0)")
    assert orch._next_ticket(queue)['id'] == 'ready'
    assert queue.execute("SELECT status FROM tickets WHERE id='orphan'").fetchone()[0] == 'open'


def test_no_enabled_owner_means_empty_queue_without_enabling_jobs(queue):
    queue.execute('UPDATE heartbeats SET enabled=0')
    assert orch._next_ticket(queue) is None
    assert queue.execute('SELECT sum(enabled) FROM heartbeats').fetchone()[0] == 0


@pytest.mark.parametrize('status,locked', [('blocked', None), ('closed', None), ('open', 'lock')])
def test_enabled_owner_does_not_override_status_or_lock(queue, status, locked):
    queue.execute("UPDATE tickets SET status=?,locked_at=? WHERE id='ready'", (status, locked))
    assert orch._next_ticket(queue) is None


def test_existing_priority_is_preserved_when_both_owners_enabled(queue):
    queue.execute("INSERT INTO heartbeats VALUES ('available','missing-owner',1)")
    queue.execute("INSERT INTO heartbeats VALUES ('duplicate','missing-owner',1)")
    assert orch._next_ticket(queue)['id'] == 'orphan'
