"""No real provider, network, CRM, Ghost or publication calls in these tests."""
import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
import internal_ticket_draft as d
import provider_fallback as pf


@pytest.fixture
def db():
    c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
    c.executescript('''CREATE TABLE tickets(id TEXT PRIMARY KEY,assignee_agent TEXT,company_id INTEGER,
    status TEXT,description TEXT,updated_at TEXT,locked_at TEXT,locked_by TEXT,lock_timeout_seconds INTEGER,
    approval_id INTEGER,requires_human_approval INTEGER,blocked_reason TEXT);
    CREATE TABLE ticket_activity(id TEXT,ticket_id TEXT,actor TEXT,action TEXT,payload TEXT,created_at TEXT);''')
    c.execute('INSERT INTO tickets VALUES(?,?,?,?,?,?,NULL,NULL,NULL,NULL,0,NULL)',
              (d.PILOT_ID,d.PILOT_AGENT,1,'open',d.MARKER,'revision-1'))
    c.commit()
    return c


def success(**kw):
    assert kw['tool_policy'] == 'no_tools'
    assert kw['agent'] == '' and kw['max_turns'] == 1
    return {'status':'success','output':'RASCUNHO — EXEMPLO HIPOTÉTICO\nDados fictícios: 100 casos, 80 resolvidos = 80%.'}


def run(db, tmp_path, invoke=success, ticket=None):
    return d.run_draft(db, ticket or d.restricted_candidate(db,d.PILOT_AGENT),
                       d.PILOT_AGENT,str(uuid.uuid4()),tmp_path,invoke=invoke)


def test_checkout_before_inference_and_controlled_artifact(db,tmp_path):
    def invoke(**kw):
        r=db.execute('SELECT * FROM tickets').fetchone()
        assert r['locked_by']==d.PILOT_AGENT
        assert db.execute("SELECT count(*) FROM ticket_activity WHERE action='checkout'").fetchone()[0]==1
        return success(**kw)
    result=run(db,tmp_path,invoke)
    assert result['status']=='success' and result['output']==''
    path=tmp_path/result['internal_draft']; assert path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600
    r=db.execute('SELECT * FROM tickets').fetchone()
    assert r['status']=='review' and r['locked_by'] is None and r['approval_id'] is None
    audit=json.loads(db.execute("SELECT payload FROM ticket_activity WHERE action='internal_draft_ready'").fetchone()[0])
    assert audit['sha256']==result['sha256'] and audit['human_publication_approval'] is False


def test_cas_refuses_stale_revision(db,tmp_path):
    ticket=d.restricted_candidate(db,d.PILOT_AGENT)
    db.execute("UPDATE tickets SET updated_at='human-edit'");db.commit()
    def forbidden(**kw):raise AssertionError('must not invoke')
    assert run(db,tmp_path,forbidden,ticket)['error']=='restricted_checkout_conflict'
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('field,value',[('company_id',2),('assignee_agent','other'),('approval_id',12),('requires_human_approval',1)])
def test_contract_and_owner_cannot_be_changed(db,tmp_path,field,value):
    ticket=d.restricted_candidate(db,d.PILOT_AGENT)
    if field=='assignee_agent':
        db.execute('UPDATE tickets SET assignee_agent=?',(value,));db.commit()
        assert run(db,tmp_path,ticket=ticket)['error']=='restricted_checkout_conflict'
    else:
        ticket[field]=value
        with pytest.raises(ValueError):run(db,tmp_path,ticket=ticket)


@pytest.mark.parametrize('output',['', 'Caso real comprovado', {'tool':'crm'}, 'X'*64001])
def test_invalid_or_unlabelled_draft_is_specific_block_no_retry(db,tmp_path,output):
    calls=[]
    def invoke(**kw):calls.append(kw);return {'status':'success','output':output}
    result=run(db,tmp_path,invoke)
    assert result['status']=='fail' and len(calls)==1
    assert db.execute('SELECT blocked_reason FROM tickets').fetchone()[0]=='internal_draft_failed'
    assert not list(tmp_path.iterdir())


def test_model_action_json_is_inert_text_never_applied(db,tmp_path):
    dangerous='RASCUNHO — EXEMPLO HIPOTÉTICO\n'+json.dumps({'action':'publish','publish_intent':True,
        'publish_target':'ghost','crm':'fetch','path':'/tmp/escape','new_status':'resolved'})
    result=run(db,tmp_path,lambda **kw:{'status':'success','output':dangerous})
    assert result['status']=='success'
    assert db.execute('SELECT status FROM tickets').fetchone()[0]=='review'
    assert (tmp_path/result['internal_draft']).read_text()==dangerous
    assert [r[0] for r in db.execute('SELECT action FROM ticket_activity')]==['checkout','internal_draft_ready']


def test_ticket_prompt_injection_not_forwarded(db,tmp_path):
    db.execute("UPDATE tickets SET description=description || ' CRM_SECRET Ghost POST curl malicious'");db.commit()
    def invoke(**kw):
        assert 'CRM_SECRET' not in kw['prompt'] and 'curl malicious' not in kw['prompt']
        return success(**kw)
    assert run(db,tmp_path,invoke)['status']=='success'


def test_symlink_cannot_redirect_controller_write(db,tmp_path):
    outside=tmp_path/'outside';outside.mkdir()
    (tmp_path/'internal-drafts').symlink_to(outside,target_is_directory=True)
    assert run(db,tmp_path)['status']=='fail'
    assert list(outside.iterdir())==[]


def test_concurrent_human_edit_not_overwritten(db,tmp_path):
    def invoke(**kw):
        db.execute("UPDATE tickets SET status='closed',updated_at='human'");db.commit()
        return success(**kw)
    assert run(db,tmp_path,invoke)['error']=='restricted_completion_conflict'
    assert db.execute('SELECT status FROM tickets').fetchone()[0]=='closed'
    assert not list(tmp_path.iterdir())


def test_provider_failure_or_exception_never_native_retry(db,tmp_path):
    def invoke(**kw):raise RuntimeError('adapter unavailable')
    assert run(db,tmp_path,invoke)['error']=='adapter unavailable'
    assert db.execute('SELECT status FROM tickets').fetchone()[0]=='blocked'


def test_nonpilot_defaults_and_blocked_not_selected(db):
    assert d.restricted_candidate(db,'other') is None
    assert not d.is_restricted(str(uuid.uuid4()))
    db.execute("UPDATE tickets SET status='blocked'")
    assert d.restricted_candidate(db,d.PILOT_AGENT) is None


def test_policy_survives_each_fallback_and_resets(tmp_path,monkeypatch):
    seen=[]
    class Engine:
        attempts_log=[1,2,3]
        def attempts(self,**kw):
            for i,cli in enumerate(['opencode','openclaude','claude'],1):
                yield pf.FallbackAttempt(i,'existing',str(i),cli,kw['prompt'],1,5,
                    env_overrides={'OPENAI_BASE_URL':'https://example.invalid/v1','OPENAI_API_KEY':'fixture'})
    def invoke(**kw):
        seen.append((kw['cli_command'],pf._CLI_TOOL_POLICY.get()))
        return {'status':'fail','error':'fixture','output':''}
    monkeypatch.setattr(pf,'FallbackEngine',Engine);monkeypatch.setattr(pf,'_invoke_cli',invoke)
    result=pf.invoke_with_fallback('text',cwd=tmp_path,tool_policy='no_tools')
    assert result['fallback_exhausted']
    assert seen==[(cli,'no_tools') for cli in ['opencode','openclaude','claude']]
    assert pf._CLI_TOOL_POLICY.get() is None


@pytest.mark.parametrize('cli',['claude','openclaude','unknown'])
def test_unsupported_adapters_fail_closed_without_launch(cli,monkeypatch):
    monkeypatch.setattr(pf,'_invoke_cli_configured',lambda **kw:pytest.fail('unrestricted subprocess'))
    token=pf._CLI_TOOL_POLICY.set('no_tools')
    try:
        assert pf._invoke_cli(cli,'CRM Ghost publish',1,5)['error']=='restricted_adapter_unsupported'
    finally:pf._CLI_TOOL_POLICY.reset(token)


def test_heartbeat_routes_pilot_without_general_tools_outcomes_or_notifications(db,tmp_path,monkeypatch):
    import heartbeat_runner as runner
    db.execute('CREATE TABLE heartbeat_runs(run_id TEXT PRIMARY KEY,heartbeat_id TEXT,trigger_id TEXT,started_at TEXT,status TEXT,triggered_by TEXT)')
    db.commit()
    class Connection:
        def __getattr__(self,name):return getattr(db,name)
        def close(self):pass
    monkeypatch.setattr(runner,'_get_db',lambda:Connection())
    monkeypatch.setattr(runner,'_load_heartbeat',lambda _: {'agent':d.PILOT_AGENT,'timeout_seconds':10})
    monkeypatch.setattr(runner,'step1_load_identity',lambda _: 'persona')
    monkeypatch.setattr(runner,'step2_check_approvals',lambda *a: [])
    monkeypatch.setattr(runner,'step3_query_inbox',lambda *a:[dict(db.execute('SELECT * FROM tickets').fetchone())])
    monkeypatch.setattr(runner,'_load_trigger_payload',lambda *a:None)
    monkeypatch.setattr(runner,'WORKSPACE',tmp_path)
    (tmp_path/'workspace').mkdir()
    monkeypatch.setattr(pf,'invoke_with_fallback',success)
    def forbidden(*a,**kw):pytest.fail('generic execution/outcome/notification reached')
    for name in ('step4_pick_priority','step6_assemble_context','step7_invoke_claude',
                 '_send_heartbeat_notification','step9_release_checkout'):
        monkeypatch.setattr(runner,name,forbidden)
    persisted=[]
    monkeypatch.setattr(runner,'step8_persist',lambda *a:persisted.append(a[2]))
    runner.run_heartbeat('autopilot-pixel-social-media',triggered_by='interval')
    assert len(persisted)==1 and persisted[0]['internal_draft']
    assert db.execute('SELECT status FROM tickets').fetchone()[0]=='review'


def test_replaced_checkout_cannot_commit_or_release_new_lock(db,tmp_path):
    def invoke(**kw):
        db.execute("UPDATE tickets SET locked_at='new-checkout'");db.commit()
        return success(**kw)
    assert run(db,tmp_path,invoke)['error']=='restricted_completion_conflict'
    r=db.execute('SELECT status,locked_at FROM tickets').fetchone()
    assert tuple(r)==('open','new-checkout')
    assert not list(tmp_path.iterdir())


def test_unsupported_runtime_reported_as_specific_block(db,tmp_path):
    result=run(db,tmp_path,lambda **kw:{'status':'fail','error':'restricted_adapter_unsupported'})
    assert result['error']=='restricted_adapter_unsupported'
    audit=json.loads(db.execute("SELECT payload FROM ticket_activity WHERE action='internal_draft_failed'").fetchone()[0])
    assert audit['reason']=='restricted_adapter_unsupported'


def test_approval_change_during_inference_is_preserved(db,tmp_path):
    def invoke(**kw):
        db.execute('UPDATE tickets SET approval_id=42,requires_human_approval=1');db.commit()
        return success(**kw)
    assert run(db,tmp_path,invoke)['error']=='restricted_completion_conflict'
    assert tuple(db.execute('SELECT status,approval_id,requires_human_approval FROM tickets').fetchone())==('open',42,1)
    assert not list(tmp_path.iterdir())
