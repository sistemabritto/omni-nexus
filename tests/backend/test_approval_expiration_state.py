"""Expiration must preserve human gates and must not impersonate rejection."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard/backend"))
import importlib
from unittest.mock import patch

import pytest
from flask import Flask


@pytest.fixture
def app():
    import models
    importlib.reload(models)
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', TESTING=True)
    models.db.init_app(app)
    with app.app_context():
        models.db.create_all()
        models.db.session.commit()
    return app


def seed(app, kind):
    import models
    with app.app_context():
        models.db.session.add(models.Ticket(id='content', title='Content', status='blocked', priority='medium', created_at='2000', updated_at='2000', requires_human_approval=1, approval_id=1))
        models.db.session.add(models.Goal(id=1, project_id=1, slug='goal', title='Goal', status='active', decomposition_state='proposed', created_at='2000', updated_at='2000'))
        models.db.session.add(models.PendingApproval(id=1, gate_type=kind, ticket_id='content', goal_id=1, payload='{}', created_at='2000-01-01T00:00:00.000000Z', expires_at='2000-01-01T08:00:00.000000Z', status='pending', idempotency_key='test'))
        models.db.session.commit()


def test_publication_expiration_stays_blocked_and_requires_human(app):
    import models
    from ticket_janitor import sweep_pending_approvals
    seed(app, 'publish')
    with app.app_context(), patch('notifications.send_approval_request') as send, patch('routes.approvals._expire_approval_ticket'):
        assert sweep_pending_approvals() == 1
        ticket = models.db.session.get(models.Ticket, 'content')
        assert (ticket.status, ticket.requires_human_approval, ticket.blocked_reason) == ('blocked', 1, 'approval_expired')
        assert ticket.approval_id is None  # fresh approval may link later, never approval by silence
        assert models.db.session.execute(models.db.text('SELECT status FROM pending_approvals')).scalar() == 'expired'
        assert sweep_pending_approvals() == 0
        send.assert_not_called()


def test_decomposition_expiration_is_not_rejection(app):
    import models
    from ticket_janitor import sweep_pending_approvals
    seed(app, 'decomposition')
    with app.app_context(), patch('notifications.send_approval_request'), patch('routes.approvals._expire_approval_ticket'):
        assert sweep_pending_approvals() == 1
        goal = models.db.session.get(models.Goal, 1)
        assert goal.decomposition_state == 'expired'
        assert goal.status == 'active'
        assert models.Ticket.query.count() == 1


def test_human_decided_gate_is_untouched(app):
    import models
    from ticket_janitor import sweep_pending_approvals
    seed(app, 'decomposition')
    with app.app_context(), patch('notifications.send_approval_request'):
        models.db.session.execute(models.db.text("UPDATE pending_approvals SET status='approved'"))
        models.db.session.commit()
        assert sweep_pending_approvals() == 0
        assert models.db.session.get(models.Goal, 1).decomposition_state == 'proposed'
