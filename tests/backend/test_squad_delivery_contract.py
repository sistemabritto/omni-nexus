"""Executable contract and authenticated validation; no worker/queue/provider."""
from copy import deepcopy
from pathlib import Path
import pytest
from squad_delivery_contract import FRONTS, METHODS, validate_handoff
from tests.backend.test_managed_live_context import setup, ORIGIN

ROOT = Path(__file__).resolve().parents[2]


def candidate(front='editorial'):
    owner = FRONTS[front][1]
    return dict(companyId=7, front=front, taskId='fixture-task', currentOwner=owner,
        version='fixture-v1', objective='Produce bounded fixture', limits='No publish or spend',
        inputs=['Authorized fixture source'], output='Versioned fixture artifact',
        acceptance=['Output matches brief and channel constraints'],
        evidence=[dict(ref='fixture/output.txt', sha256='a'*64, version='fixture-v1')],
        dependencies=[], nextAction='Recipient inspects package', contributors=[owner],
        criticality='P1', tools=[dict(name='fixture-tool',state='available',evidenceRef='fixture/probe.json')])


@pytest.mark.parametrize('front', FRONTS)
def test_all_fronts_bind_existing_distinct_roles_and_methods(front):
    label, *roles = FRONTS[front]
    assert len(set(roles)) == 3
    assert all((ROOT / '.claude/agents' / (slug+'.md')).is_file() for slug in roles)
    assert all((ROOT / path).is_file() for path in METHODS[front])
    payload = candidate(front)
    original = deepcopy(payload)
    result = validate_handoff(payload)
    assert payload == original
    assert result['status'] == 'candidate_complete'
    assert result['dispatchAllowed'] is False and result['ownershipChanged'] is False
    assert result['acknowledgement'] == 'not_recorded'
    assert result['evidenceStatus'] == 'declared_not_verified'


def test_reviewer_cannot_review_own_contribution_and_caller_cannot_override_roles():
    data = candidate()
    data['contributors'].append(FRONTS['editorial'][3])
    with pytest.raises(ValueError, match='reviewer_contributed'):
        validate_handoff(data)
    data = candidate(); data['reviewer'] = 'pixel-social-media'
    with pytest.raises(ValueError, match='invalid_fields'):
        validate_handoff(data)


def test_missing_access_is_not_missing_persona_and_blocked_tool_never_becomes_ready():
    data = candidate(); data['tools'][0]['state'] = 'unavailable'
    result = validate_handoff(data)
    assert result['status'] == 'blocked'
    assert 'tool:fixture-tool:unavailable' in result['blockers']
    data['tools'][0]['state'] = 'not_verified'
    assert validate_handoff(data)['status'] == 'blocked'
    data['tools'][0]['state'] = 'available'; data['dependencies'] = ['Human decision pending']
    assert validate_handoff(data)['status'] == 'blocked'


def test_reject_stale_artifact_and_missing_acceptance():
    data = candidate(); data['evidence'][0]['version'] = 'old-version'
    with pytest.raises(ValueError, match='evidence_binding'): validate_handoff(data)
    data = candidate(); data['acceptance'] = []
    with pytest.raises(ValueError, match='invalid_acceptance'): validate_handoff(data)


def test_endpoint_preserves_auth_acl_and_never_accepts_ownership(setup, monkeypatch, tmp_path):
    app,c,login,context,_,calls = setup
    from routes import agents
    app.register_blueprint(agents.bp)
    monkeypatch.setattr(agents, 'WORKSPACE', ROOT)
    for slug in FRONTS['editorial'][1:]:
        (context.AGENTS_DIR / (slug+'.md')).write_text('Fixture persona')
    endpoint = '/api/agents/delivery-contract/validate'
    assert c.post(endpoint,json=candidate(),headers=ORIGIN).status_code == 401
    login()
    from models import db, Ticket
    with app.app_context():
        db.session.add(Ticket(id='fixture-task', title='Protected fixture', company_id=7,
            status='blocked', blocked_reason='registered_not_dispatched',
            assignee_agent='pixel-social-media', created_by='fixture',
            created_at='fixture', updated_at='fixture'))
        db.session.commit()
    def ticket_state():
        with app.app_context():
            row = db.session.get(Ticket, 'fixture-task')
            return {column.name: getattr(row, column.name) for column in Ticket.__table__.columns}
    protected = ticket_state()
    assert c.post(endpoint,json=candidate()).status_code == 403
    assert c.post(endpoint,json=candidate(),headers={**ORIGIN,'X-Fixture-Token':'yes'}).status_code == 403
    result = c.post(endpoint,json=candidate(),headers=ORIGIN)
    assert result.status_code == 200 and result.json['status'] == 'candidate_complete'
    assert result.json['currentOwner'] == 'pixel-social-media'
    assert result.json['dispatchAllowed'] is False and calls == []
    monkeypatch.setattr(agents, 'WORKSPACE', tmp_path)
    blocked = c.post(endpoint,json=candidate(),headers=ORIGIN)
    assert blocked.json['status'] == 'blocked'
    assert any(x.startswith('method_missing:') for x in blocked.json['blockers'])
    monkeypatch.setattr(context, 'has_agent_access', lambda *_: False)
    assert c.post(endpoint,json=candidate(),headers=ORIGIN).status_code == 403
    assert calls == []
    assert ticket_state() == protected


@pytest.mark.parametrize('state', ['missing', 'empty', 'invalid_utf8', 'oversized', 'external_symlink'])
def test_unusable_or_external_method_is_not_packaged_availability(tmp_path, state):
    from squad_delivery_contract import unavailable_methods
    root = tmp_path / 'workspace'; root.mkdir()
    path = root / 'method.md'
    if state == 'empty': path.write_text('  ')
    elif state == 'invalid_utf8': path.write_bytes(b'\xff')
    elif state == 'oversized': path.write_bytes(b'x' * 262145)
    elif state == 'external_symlink':
        external = tmp_path / 'external.md'; external.write_text('External fixture')
        path.symlink_to(external)
    assert unavailable_methods(root, ['method.md']) == ['method.md']
    if path.exists() or path.is_symlink(): path.unlink()
    path.write_text('# Local fixture method')
    assert unavailable_methods(root, ['method.md']) == []
