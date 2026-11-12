"""Blocked outcome metadata used by selective recovery triage."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
from heartbeat_outcome import apply_outcome


@pytest.mark.parametrize('previous,expected', [
    (None, 'agent_blocked'), ('', 'agent_blocked'), ('  ', 'agent_blocked'),
    ('pending_human_approval', 'pending_human_approval'),
    ('review_exhausted', 'review_exhausted'), ('external_dependency', 'external_dependency'),
])
def test_blocked_outcome_records_cause_without_replacing_existing_gate(previous, expected):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE tickets (id TEXT PRIMARY KEY, title TEXT, status TEXT,
            goal_id TEXT, blocked_reason TEXT, requires_human_approval INTEGER,
            approval_id INTEGER, updated_at TEXT, resolved_at TEXT);
        CREATE TABLE ticket_comments (id TEXT, ticket_id TEXT, author TEXT,
            body TEXT, mentions TEXT, created_at TEXT);
        CREATE TABLE ticket_activity (id TEXT, ticket_id TEXT, actor TEXT,
            action TEXT, payload TEXT, created_at TEXT);
    ''')
    conn.execute("INSERT INTO tickets VALUES ('t1','CRM','in_progress',NULL,?,1,42,NULL,NULL)", (previous,))
    notice = apply_outcome('hb1', 'tester', {'status': 'success', 'output': {
        'action': 'blocked', 'ticket_id': 't1', 'blocked_reason': 'Cloudflare HTTP 403',
        'needs': 'Revisar acesso externo', 'result': 'Sondagem somente leitura',
    }}, conn)
    row = conn.execute('SELECT * FROM tickets').fetchone()
    assert row['status'] == 'blocked'
    assert row['blocked_reason'] == expected
    assert (row['requires_human_approval'], row['approval_id']) == (1, 42)
    comment = conn.execute('SELECT body FROM ticket_comments').fetchone()[0]
    assert 'Cloudflare HTTP 403' in comment
    assert 'Revisar acesso externo' in comment
    assert notice['kind'] == 'blocked'
    assert conn.execute('SELECT COUNT(*) FROM ticket_activity').fetchone()[0] == 1
    conn.close()
