import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
from stale_ticket_sweep import _stale_in_progress, _flag_blocked


@pytest.mark.parametrize('change', ['touch', 'lock', 'status', None])
def test_sweep_revalidates_selected_ticket_before_blocking(change):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
        CREATE TABLE tickets (id TEXT, title TEXT, assignee_agent TEXT, status TEXT,
          updated_at TEXT, created_at TEXT, locked_at TEXT, blocked_reason TEXT);
        CREATE TABLE ticket_comments (id TEXT, ticket_id TEXT, author TEXT, body TEXT, created_at TEXT);
        CREATE TABLE ticket_activity (id TEXT, ticket_id TEXT, actor TEXT, action TEXT, payload TEXT, created_at TEXT);
        INSERT INTO tickets VALUES ('t1','Test','agent','in_progress','2020-01-01','2020-01-01',NULL,NULL);
    ''')
    selected = _stale_in_progress(c, 60)[0]
    if change == 'touch':
        c.execute("UPDATE tickets SET updated_at='2026-10-15T12:00:00Z'")
    elif change == 'lock':
        c.execute("UPDATE tickets SET locked_at='2026-10-15T12:00:00Z'")
    elif change == 'status':
        c.execute("UPDATE tickets SET status='review'")
    assert _flag_blocked(c, selected) is (change is None)
    row = c.execute('SELECT status,blocked_reason FROM tickets').fetchone()
    assert (row['status'] == 'blocked') is (change is None)
    assert c.execute('SELECT count(*) FROM ticket_comments').fetchone()[0] == int(change is None)
    assert c.execute('SELECT count(*) FROM ticket_activity').fetchone()[0] == int(change is None)
