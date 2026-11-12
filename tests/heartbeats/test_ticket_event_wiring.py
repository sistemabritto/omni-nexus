"""Real Flask routes + temporary SQLite + fake executor; no provider or external calls."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from tests.tickets.test_tickets import app, client


@pytest.fixture
def wiring(app, client, monkeypatch):
    import models as m
    import heartbeat_dispatcher as d
    monkeypatch.setenv('TICKET_EVENT_WAKES_ENABLED', '1')
    now = datetime.now(timezone.utc).isoformat()
    with app.app_context():
        m.db.session.add(m.Company(id=1, name='One', slug='one', status='active',created_at=now,updated_at=now))
        m.db.session.add(m.Mission(id=1,slug='m',title='Mission',created_at=now,updated_at=now))
        m.db.session.add(m.GoalProject(id=1,slug='p',title='Project',company_id=1,mission_id=1,created_at=now,updated_at=now))
        m.db.session.add(m.Goal(id=1,slug='g',title='Goal',project_id=1,created_at=now,updated_at=now))
        m.db.session.add(m.Ticket(id='ticket',title='Task',status='open',company_id=1,project_id=1,goal_id=1,assignee_agent='pixel-social-media',created_at=now,updated_at=now))
        m.db.session.add(m.Heartbeat(id='hb',agent='pixel-social-media',interval_seconds=3600,enabled=True,wake_triggers='["mention","new_task"]',decision_prompt='Use ticket context.',created_at=now,updated_at=now))
        m.db.session.commit()
        path = m.db.engine.url.database
    def connect():
        c=sqlite3.connect(path,timeout=10);c.row_factory=sqlite3.Row;return c
    monkeypatch.setattr(d,'_get_db',connect)
    import routes.tickets as routes
    monkeypatch.setattr(routes,'raw_conn',connect)
    d._running.clear()
    yield client, connect, d
    d._running.clear()


def mention(w, **kwargs):
    return w[0].post('/api/tickets/ticket/comments',json={'body':'Please review @pixel-social-media','author':'agent:spoofed'},**kwargs)


def event(w):
    c=w[1]();row=dict(c.execute('SELECT * FROM heartbeat_triggers').fetchone());c.close();return row


def test_authenticated_context_atomic_and_idempotent(wiring):
    w=wiring;r=mention(w,headers={'Idempotency-Key':'source-1'});assert r.status_code==201
    p=json.loads(event(w)['payload'])
    assert p['actor_user_id']==1 and p['owner']=='pixel-social-media'
    assert [p[k] for k in ['company_id','mission_id','project_id','goal_id']]==[1,1,1,1]
    assert p['schema']=='ticket-wake-v1' and p['depth']==0 and p['max_depth']==0
    assert not p['ownership_changed'] and not p['publication_approved']
    assert mention(w,headers={'Idempotency-Key':'source-1'}).status_code==200
    assert w[0].post('/api/tickets/ticket/comments',json={'body':'different'},headers={'Idempotency-Key':'source-1'}).status_code==409
    c=w[1]();assert c.execute('SELECT count(*) FROM ticket_comments').fetchone()[0]==1
    assert c.execute('SELECT count(*) FROM heartbeat_triggers').fetchone()[0]==1;c.close()


def test_default_gate_no_wakes(wiring,monkeypatch):
    monkeypatch.delenv('TICKET_EVENT_WAKES_ENABLED');assert mention(wiring).status_code==201
    c=wiring[1]();assert c.execute('SELECT count(*) FROM heartbeat_triggers').fetchone()[0]==0;c.close()


def test_shared_token_cannot_impersonate_agent(wiring,app):
    from flask import g
    @app.before_request
    def service_auth():g.auth_via_api_token=True
    assert mention(wiring).status_code==201
    c=wiring[1]();assert c.execute('SELECT count(*) FROM heartbeat_triggers').fetchone()[0]==0;c.close()


@pytest.mark.parametrize('mutation',[
    "UPDATE heartbeats SET enabled=0", "UPDATE heartbeats SET wake_triggers='[]'",
    "UPDATE tickets SET status='blocked'", "UPDATE tickets SET requires_human_approval=1",
    "UPDATE tickets SET updated_at='new-version'", "UPDATE users SET role='viewer'",
    "UPDATE projects SET company_id=2", "UPDATE companies SET status='inactive'",
])
def test_dispatch_revalidates_authority_context_and_gate(wiring,monkeypatch,mutation):
    w=wiring;assert mention(w).status_code==201
    c=w[1]();c.execute(mutation);c.commit();c.close()
    submit=Mock();monkeypatch.setattr(w[2]._executor,'submit',submit)
    assert w[2].drain_event_triggers()==0;assert not submit.called;assert not w[2]._running


def test_capacity_and_duplicate_claim(wiring,monkeypatch):
    w=wiring;mention(w);submit=Mock();monkeypatch.setattr(w[2]._executor,'submit',submit)
    assert w[2].drain_event_triggers()==1
    assert w[2].drain_event_triggers()==0
    assert submit.call_count==1
    # A second process cannot overlap the same durable reservation.
    w[2]._running.clear();assert w[2]._claim_event(event(w)) is None


def test_submit_failure_backoff_no_lost_event_no_slot_leak(wiring,monkeypatch):
    w=wiring;mention(w);submit=Mock(side_effect=RuntimeError('pool unavailable'));monkeypatch.setattr(w[2]._executor,'submit',submit)
    assert w[2].drain_event_triggers()==0 and not w[2]._running
    r=event(w);assert r['consumed_at'] is None
    assert json.loads(r['payload'])['_dispatcher_retry']['attempts']==1
    c=w[1]();assert c.execute('SELECT count(*) FROM heartbeat_runs').fetchone()[0]==0;c.close()
    assert w[2].drain_event_triggers()==0;assert submit.call_count==1


def test_stale_queued_callback_cannot_run_after_reconcile(wiring):
    w=wiring;mention(w);r=event(w);rid=w[2]._claim_event(r);assert rid
    c=w[1]();c.execute("UPDATE heartbeat_runs SET started_at='2000-01-01T00:00:00Z'");c.commit();c.close()
    assert w[2].reconcile_event_reservations()==1
    assert not w[2]._start_event(r,rid)
    assert event(w)['consumed_at'] is None


def test_disable_between_submit_and_callback(wiring):
    w=wiring;mention(w);r=event(w);rid=w[2]._claim_event(r)
    c=w[1]();c.execute('UPDATE heartbeats SET enabled=0');c.commit();c.close()
    assert not w[2]._start_event(r,rid)


def test_work_event_lease_before_work_and_cas_release(wiring):
    from ticket_wake_contract import acquire_work_lease,release_work_lease
    w=wiring
    assert w[0].patch('/api/tickets/ticket',json={'status':'in_progress'}).status_code==200
    r=event(w);assert r['trigger_type']=='new_task';p=json.loads(r['payload'])
    c=w[1]();token=acquire_work_lease(c,p,'pixel-social-media','run',300)
    assert c.execute('SELECT locked_by FROM tickets').fetchone()[0]=='pixel-social-media'
    with pytest.raises(ValueError,match='ticket_locked'):acquire_work_lease(c,p,'pixel-social-media','other',300)
    assert not release_work_lease(c,'ticket','pixel-social-media','wrong-token')
    assert release_work_lease(c,'ticket','pixel-social-media',token)
    assert c.execute('SELECT assignee_agent FROM tickets').fetchone()[0]=='pixel-social-media';c.close()


def test_noop_patch_does_not_queue_work(wiring):
    assert wiring[0].patch('/api/tickets/ticket',json={'status':'open'}).status_code==200
    c=wiring[1]();assert c.execute('SELECT count(*) FROM heartbeat_triggers').fetchone()[0]==0;c.close()


def test_comment_and_wake_roll_back_together(wiring,monkeypatch):
    import routes.tickets as routes
    def fail(*args,**kwargs):raise RuntimeError('simulated outbox failure')
    monkeypatch.setattr(routes,'_fire_mention_triggers',fail)
    with pytest.raises(RuntimeError):mention(wiring)
    c=wiring[1]();assert c.execute('SELECT count(*) FROM ticket_comments').fetchone()[0]==0;c.close()


def test_approved_aliases_and_email_boundary():
    from routes.tickets import _parse_mentions
    assert _parse_mentions('@Dante @pixel-social-media @Íris @Argos') == ['pixel-social-media','canvas-designer','oath-verifier']
    assert _parse_mentions('user@Dante.com @UNKNOWN') == []


def test_three_preinvoke_failures_exhaust_without_execution(wiring,monkeypatch):
    w=wiring;mention(w);submit=Mock(side_effect=RuntimeError('pool unavailable'));monkeypatch.setattr(w[2]._executor,'submit',submit)
    for attempt in range(3):
        assert w[2].drain_event_triggers()==0
        r=event(w);p=json.loads(r['payload']);assert p['_dispatcher_retry']['attempts']==attempt+1
        if attempt<2:
            p['_dispatcher_retry']['next_at']='2000-01-01T00:00:00Z'
            c=w[1]();c.execute('UPDATE heartbeat_triggers SET payload=?',(json.dumps(p),));c.commit();c.close()
    assert event(w)['consumed_at'] is not None
    assert w[2].drain_event_triggers()==0 and submit.call_count==3


def test_two_process_claims_have_one_winner(wiring):
    from concurrent.futures import ThreadPoolExecutor
    w=wiring;mention(w);r=event(w)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(lambda _:w[2]._claim_event(r),range(2)))
    assert sum(value is not None for value in claims)==1


@pytest.mark.parametrize('kind',['mention','new_task'])
def test_route_to_dispatch_to_runner_to_observed_result(wiring,monkeypatch,tmp_path,kind):
    import hashlib
    import heartbeat_runner as runner
    import provider_fallback
    import runtime_preflight
    w=wiring
    if kind=='mention':mention(w)
    else:assert w[0].patch('/api/tickets/ticket',json={'status':'in_progress'}).status_code==200
    r=event(w);p=json.loads(r['payload'])
    root=tmp_path/'runtime';(root/'workspace').mkdir(parents=True)
    proof=root/'workspace'/'proof.md';proof.write_text('Simulated local task delivery, no external systems.')
    monkeypatch.setattr(runner,'WORKSPACE',root)
    monkeypatch.setattr(runner,'LOGS_DIR',root/'logs')
    monkeypatch.setattr(runner,'_get_db',w[1])
    monkeypatch.setattr(runner,'step1_load_identity',lambda agent:'Test identity; preserve it.')
    monkeypatch.setattr(runtime_preflight,'runtime_preflight',lambda *args,**kwargs:{})
    monkeypatch.setattr(provider_fallback,'_read_providers_config',lambda:{'active_provider':'anthropic'})
    notify=Mock(side_effect=AssertionError('No legacy auto-review or external notification'))
    monkeypatch.setattr(runner,'_send_heartbeat_notification',notify)
    calls=[]
    def invoke(**kwargs):
        calls.append(kwargs)
        assert p['event_id'] in kwargs['prompt'] and 'echo $DASHBOARD_API_TOKEN' not in kwargs['prompt']
        assert runner.REVIEW_LOOP_SUBAGENT_INSTRUCTIONS not in kwargs['prompt']
        if kind=='new_task':
            c=w[1]();t=c.execute('SELECT * FROM tickets').fetchone();assert t['locked_by']=='pixel-social-media' and t['lock_token'];c.close()
            spec={'action':'work','ticket_id':'ticket','new_status':'review','result':'Prepared simulated evidence','evidence':[{'ref':'proof.md','sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}]}
        else:
            response=w[0].post('/api/tickets/ticket/comments',json={'body':'Verified against the simulated evidence.'},headers={'Idempotency-Key':'wake:'+p['event_id'],'X-Ticket-Version':p['ticket_version']})
            assert response.status_code==201
            # Replay must return the same comment even after its version changed.
            replay=w[0].post('/api/tickets/ticket/comments',json={'body':'Verified against the simulated evidence.'},headers={'Idempotency-Key':'wake:'+p['event_id'],'X-Ticket-Version':p['ticket_version']})
            assert replay.status_code==200
            spec={'action':'work','ticket_id':None,'result':'Feedback posted'}
        return {'status':'success','output':json.dumps(spec),'duration_ms':1}
    monkeypatch.setattr(runner,'step7_invoke_claude',invoke)
    callbacks=[];monkeypatch.setattr(w[2]._executor,'submit',lambda fn:callbacks.append(fn))
    assert w[2].drain_event_triggers()==1
    callbacks[0]()
    assert len(calls)==1 and not notify.called
    c=w[1]();run=dict(c.execute('SELECT * FROM heartbeat_runs').fetchone());t=dict(c.execute('SELECT * FROM tickets').fetchone())
    assert run['status']=='success',run['error']
    assert t['assignee_agent']=='pixel-social-media' and t['locked_by'] is None and t['lock_token'] is None
    assert t['status']==('review' if kind=='new_task' else 'open')
    if kind=='new_task':
        receipt=json.loads(c.execute("SELECT payload FROM ticket_activity WHERE action='ticket_event_result'").fetchone()[0]);assert receipt['acknowledgement']=='not_recorded' and receipt['evidence']
    assert c.execute('SELECT count(*) FROM heartbeat_triggers').fetchone()[0]==1
    c.close()
    assert w[2].drain_event_triggers()==0


def test_gate_off_preserves_pending_events(wiring,monkeypatch):
    w=wiring;mention(w);monkeypatch.delenv('TICKET_EVENT_WAKES_ENABLED')
    submit=Mock();monkeypatch.setattr(w[2]._executor,'submit',submit)
    assert w[2].drain_event_triggers()==0 and not submit.called
    assert event(w)['consumed_at'] is None


def test_malformed_event_is_diagnosed_without_slot_leak(wiring,monkeypatch):
    w=wiring;mention(w);c=w[1]();c.execute("UPDATE heartbeat_triggers SET payload='[]'");c.commit();c.close()
    submit=Mock();monkeypatch.setattr(w[2]._executor,'submit',submit)
    assert w[2].drain_event_triggers()==0 and not submit.called and not w[2]._running
    assert json.loads(event(w)['payload'])['_dispatcher_rejection']=='invalid_event_payload'


def test_stale_comment_rejected_without_new_rows(wiring):
    w=wiring
    r=w[0].post('/api/tickets/ticket/comments',json={'body':'stale feedback'},headers={'X-Ticket-Version':'stale'})
    assert r.status_code==409
    c=w[1]();assert c.execute('SELECT count(*) FROM ticket_comments').fetchone()[0]==0;c.close()


def test_direct_dispatch_cannot_bypass_authenticated_outbox(wiring,monkeypatch):
    submit=Mock();monkeypatch.setattr(wiring[2]._executor,'submit',submit)
    assert wiring[2].dispatch('hb','mention',{'ticket_id':'ticket'})==(False,None)
    assert not submit.called


def test_missing_or_wrong_evidence_does_not_move_ticket(wiring,tmp_path):
    from ticket_wake_contract import acquire_work_lease,apply_result,release_work_lease
    w=wiring;w[0].patch('/api/tickets/ticket',json={'status':'in_progress'});p=json.loads(event(w)['payload'])
    c=w[1]();token=acquire_work_lease(c,p,'pixel-social-media','run',300)
    result={'status':'success','output':json.dumps({'action':'work','ticket_id':'ticket','new_status':'review','result':'Claimed completion'})}
    with pytest.raises(ValueError,match='work_evidence_required'):apply_result(c,p,result,'pixel-social-media','run',token,tmp_path)
    f=tmp_path/'proof';f.write_text('real file')
    result['output']=json.dumps({'action':'work','ticket_id':'ticket','new_status':'review','evidence':[{'ref':'proof','sha256':'0'*64}]})
    with pytest.raises(ValueError,match='work_evidence_hash_mismatch'):apply_result(c,p,result,'pixel-social-media','run',token,tmp_path)
    assert c.execute('SELECT status FROM tickets').fetchone()[0]=='in_progress'
    release_work_lease(c,'ticket','pixel-social-media',token);c.close()


def test_handler_switch_after_claim_cannot_invoke_handler(wiring,monkeypatch):
    import heartbeat_runner as runner
    w=wiring;mention(w);r=event(w);rid=w[2]._claim_event(r)
    c=w[1]();c.execute("UPDATE heartbeats SET handler='unexpected.handler'");c.commit();c.close()
    assert not w[2]._start_event(r,rid)
    monkeypatch.setattr(runner,'_get_db',w[1])
    persisted=Mock();monkeypatch.setattr(runner,'step8_persist',persisted)
    runner.run_heartbeat('hb','mention',r['id'],'direct-test')
    assert persisted.call_args.args[2]['error']=='ticket_event_handler_not_supported'


def test_actor_revoked_before_result_cannot_move_ticket(wiring,tmp_path):
    import hashlib
    from ticket_wake_contract import acquire_work_lease,apply_result,release_work_lease
    w=wiring;w[0].patch('/api/tickets/ticket',json={'status':'in_progress'});p=json.loads(event(w)['payload'])
    c=w[1]();token=acquire_work_lease(c,p,'pixel-social-media','run',300)
    proof=tmp_path/'proof';proof.write_text('actual local evidence')
    output={'action':'work','ticket_id':'ticket','new_status':'review','evidence':[{'ref':'proof','sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}]}
    c.execute("UPDATE users SET role='viewer'");c.commit()
    with pytest.raises(ValueError,match='actor_revoked_before_result'):
        apply_result(c,p,{'status':'success','output':json.dumps(output)},'pixel-social-media','run',token,tmp_path)
    assert c.execute('SELECT status FROM tickets').fetchone()[0]=='in_progress'
    release_work_lease(c,'ticket','pixel-social-media',token);c.close()
