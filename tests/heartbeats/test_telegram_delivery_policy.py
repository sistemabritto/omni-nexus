"""Heartbeat transport policy never suppresses outcome state or approval gates."""
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
import notifications as n
import heartbeat_runner as hr
import heartbeat_outcome as ho


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.delenv('HEARTBEAT_TELEGRAM_ENABLED', raising=False)
    send = Mock(return_value=True)
    monkeypatch.setattr(n, '_send_telegram', send)
    return send


@pytest.mark.parametrize('value', [None, '', '0', 'false', 'off', 'typo'])
def test_default_and_false_policy_blocks_heartbeat_alerts(value, transport, monkeypatch):
    if value is not None:
        monkeypatch.setenv('HEARTBEAT_TELEGRAM_ENABLED', value)
    assert n.send_heartbeat_alert('heartbeat') is False
    assert n.notify_heartbeat_success('hb', 'bolt', 10) is False
    assert n.notify_heartbeat_failure('hb', 'bolt', 'error') is False
    assert hr.step_alert_on_failure('hb', {'status': 'timeout'}) is False
    assert hr._step_report_success('hb', {'status': 'success'}) is False
    transport.assert_not_called()


@pytest.mark.parametrize('kind', ['result', 'blocked', 'tech_fail'])
def test_outcome_is_applied_before_delivery_policy(kind, transport, monkeypatch):
    # A real outcome can create a pending approval; the transport gate must not
    # short-circuit it, or change its returned notification into a new action.
    apply = Mock(return_value={'kind': kind, 'agent': 'bolt'})
    monkeypatch.setattr(ho, 'apply_outcome', apply)
    conn = object()
    result = {'status': 'success'}
    hr._send_heartbeat_notification('hb', 'bolt', result, conn)
    apply.assert_called_once_with('hb', 'bolt', result, conn)
    transport.assert_not_called()


def test_approvals_publications_and_interactive_transport_preserved(transport):
    assert n.notify_approval_pending('Content') is True
    assert n.notify_publicacao('youtube', 'Approved content') is True
    assert n.send_telegram_alert('interactive / approval transport') is True
    assert transport.call_count == 3


def test_explicit_opt_in_uses_same_single_policy(transport, monkeypatch):
    monkeypatch.setenv('HEARTBEAT_TELEGRAM_ENABLED', 'true')
    assert n.send_heartbeat_alert('heartbeat') is True
    transport.assert_called_once_with('heartbeat')


def test_blocked_ticket_persists_with_telegram_disabled(transport):
    import sqlite3
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
      CREATE TABLE tickets (id TEXT, title TEXT, goal_id TEXT, status TEXT,
        updated_at TEXT, resolved_at TEXT, blocked_reason TEXT);
      CREATE TABLE ticket_comments (id TEXT, ticket_id TEXT, author TEXT,
        body TEXT, mentions TEXT, created_at TEXT);
      CREATE TABLE ticket_activity (id TEXT, ticket_id TEXT, actor TEXT,
        action TEXT, payload TEXT, created_at TEXT);
      INSERT INTO tickets VALUES ('t1','Internal task',NULL,'in_progress',NULL,NULL,NULL);
    ''')
    hr._send_heartbeat_notification('hb', 'bolt', {'status': 'success', 'output': {
        'action': 'blocked', 'ticket_id': 't1', 'blocked_reason': 'dependency',
        'needs': 'internal evidence', 'result': 'investigation',
    }}, c)
    row = c.execute('SELECT status,blocked_reason FROM tickets').fetchone()
    assert tuple(row) == ('blocked', 'agent_blocked')
    assert c.execute('SELECT count(*) FROM ticket_comments').fetchone()[0] == 1
    assert c.execute('SELECT count(*) FROM ticket_activity').fetchone()[0] == 1
    transport.assert_not_called()
    c.close()


def test_approval_created_during_outcome_still_delivers(transport, monkeypatch):
    def apply(*args):
        n.notify_approval_pending('Pending publication')
        return {'kind': 'blocked', 'agent': 'bolt'}
    monkeypatch.setattr(ho, 'apply_outcome', apply)
    hr._send_heartbeat_notification('hb', 'bolt', {'status': 'success'}, object())
    assert transport.call_count == 1
    assert 'Aprovação Pendente' in transport.call_args.args[0]
