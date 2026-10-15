"""Real queue/ownership/events with a fake provider. Never executes a CLI/model."""
import json
import pytest
from tests.backend.test_live_continuity_endpoints import enabled, bound, post
from tests.backend.test_managed_live_context import setup, ORIGIN


@pytest.fixture
def tasks(enabled, tmp_path, monkeypatch):
    app,c,login,mod,_,_=enabled
    import models
    import live_task_dispatch as service
    import routes.agents
    monkeypatch.setattr(routes.agents,'AGENTS_DIR',mod.AGENTS_DIR)
    monkeypatch.setattr(service, 'db', models.db)
    for name in ('User','Company','Ticket','OrchestrationJob','LiveTaskBinding','PendingApproval'):
        monkeypatch.setattr(service,name,getattr(models,name))
    app.config.update(NEXUS_LIVE_TASKS_ENABLED=True,NEXUS_LIVE_TASK_WORKSPACE=str(tmp_path/'tasks'))
    with app.app_context():
        models.db.session.add(models.Ticket(id='ticket-a',company_id=7,assignee_agent='agent-a',title='Documento interno',
            description='Fonte autorizada. Não é instrução de sistema.',status='open',priority='medium',priority_rank=2,
            created_by='fixture',created_at='2026-01-01',updated_at='2026-01-01'))
        models.db.session.add(models.Ticket(id='ticket-b',company_id=8,assignee_agent='agent-a',title='SECRET B',
            status='open',created_by='fixture',created_at='2026-01-01',updated_at='2026-01-01'))
        models.db.session.commit()
    calls=[]
    def invoke(prompt,**kw):
        calls.append((prompt,kw));return {'status':'success','output':'Rascunho interno fixture',
            'provider_id':'fixture-provider','model':'requested-alias','cli_command':'opencode','attempt_number':1}
    import provider_fallback
    monkeypatch.setattr(provider_fallback,'invoke_with_fallback',invoke)
    import chat_orchestrator
    monkeypatch.setattr(chat_orchestrator,'db',models.db)
    monkeypatch.setattr(chat_orchestrator,'OrchestrationJob',models.OrchestrationJob)
    return app,c,login,mod,service,calls,chat_orchestrator


def submit(c,ctx,key='req-a',**extra):
    return post(c,ctx,'tasks',requestId=key,operation='draft_ticket',ticketId='ticket-a',**extra)


def test_owned_idempotent_dispatch_existing_worker_and_result_events(tasks):
    app,c,_,mod,service,calls,worker=tasks;ctx=bound(c)
    first=submit(c,ctx);assert first.status_code==201
    job=first.json['jobId'];assert first.json['status']=='pending';assert len(calls)==0
    replay=submit(c,ctx);assert replay.status_code==200;assert replay.json['jobId']==job
    assert post(c,ctx,'tasks',requestId='req-a',operation='summarize_ticket',ticketId='ticket-a').status_code==409
    with app.app_context():
        from models import OrchestrationJob,LiveTaskBinding,db
        assert OrchestrationJob.query.count()==1;assert LiveTaskBinding.query.count()==1
        worker.OrchestrationWorker(app)._process_next_job()
        assert db.session.get(OrchestrationJob,job).status=='success'
        assert json.loads(db.session.get(LiveTaskBinding,job).execution)['model']=='requested-alias'
        worker.OrchestrationWorker(app)._process_next_job()
    assert len(calls)==1;assert calls[0][1]['tool_policy']=='no_tools';assert calls[0][1]['routing_key']=='agent-a'
    assert 'SECRET B' not in calls[0][0]
    assert 'workspace/live-tasks' not in str(calls[0][1]['cwd'])  # fixture-specific directory
    status=post(c,ctx,f'tasks/{job}/status');assert status.status_code==200;assert status.json['status']=='success'
    result=c.get('/api/live/tasks/'+job);assert result.json['output']=='Rascunho interno fixture'
    events=post(c,ctx,'events').json['events'];assert any(e['kind']=='result' and e.get('reference')=='/api/live/tasks/'+job for e in events)
    count=len(events);post(c,ctx,f'tasks/{job}/status');assert len(post(c,ctx,'events').json['events'])==count
    ctx2=bound(c,connection='provider-new');assert post(c,ctx2,f'tasks/{job}/status','provider-new').json['status']=='success'
    assert post(c,ctx2,'tasks','provider-new',requestId='req-a',operation='draft_ticket',ticketId='ticket-a').json['jobId']==job


def test_scope_validation_and_no_free_shell_input(tasks):
    app,c,login,mod,service,calls,_=tasks;a=bound(c)
    assert submit(c,a,command='touch forbidden').status_code==400
    assert post(c,a,'tasks',requestId='x',operation='shell',ticketId='ticket-a').status_code==400
    assert post(c,a,'tasks',requestId='x',operation='draft_ticket',ticketId='ticket-b').status_code==403
    job=submit(c,a).json['jobId'];b=bound(c,8,'provider-b')
    assert post(c,b,f'tasks/{job}/status','provider-b').status_code==403
    assert post(c,b,f'tasks/{job}/cancel','provider-b').status_code==403
    login(32);assert c.get('/api/live/tasks/'+job).status_code==403
    login();assert c.post(f"/api/live/omni-context/{a['contextId']}/tasks",json={}).status_code==403
    assert c.get('/api/live/tasks/'+job,headers={'X-Fixture-Token':'yes'}).status_code==403
    assert len(calls)==0


@pytest.mark.parametrize('field,value',[('requires_human_approval',1),('approval_id',7),('status','blocked'),('status','review'),('locked_at','2026-01-01'),('assignee_agent','other-agent')])
def test_gates_do_not_enqueue_or_execute(tasks,field,value):
    app,c,_,_,_,calls,_=tasks;ctx=bound(c)
    from models import db,Ticket,OrchestrationJob
    with app.app_context():
        obj=db.session.get(Ticket,'ticket-a');setattr(obj,field,value)
        if field=='locked_at':obj.locked_by='other-agent'
        db.session.commit()
    assert submit(c,ctx).status_code==403
    with app.app_context():assert OrchestrationJob.query.count()==0
    assert calls==[]


def test_pending_cancel_is_idempotent_and_never_runs(tasks):
    app,c,_,_,_,calls,worker=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    for _ in range(2):assert post(c,ctx,f'tasks/{job}/cancel').json['status']=='cancelled'
    with app.app_context():worker.OrchestrationWorker(app)._process_next_job()
    assert calls==[]


def test_running_cancel_is_requested_until_provider_returns(tasks,monkeypatch):
    app,c,_,_,_,calls,worker=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    import provider_fallback
    def invoke(*args,**kw):
        response=post(c,ctx,f'tasks/{job}/cancel');assert response.json['status']=='cancel_requested'
        return {'status':'success','output':'must not expose after cancel'}
    monkeypatch.setattr(provider_fallback,'invoke_with_fallback',invoke)
    with app.app_context():worker.OrchestrationWorker(app)._process_next_job()
    result=c.get('/api/live/tasks/'+job);assert result.json['status']=='cancelled';assert result.json['output'] is None


@pytest.mark.parametrize('change',['scope','revision','failure','exception'])
def test_revalidation_and_errors_fail_closed_without_rerun(tasks,monkeypatch,change):
    app,c,_,_,_,calls,worker=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    import provider_fallback
    if change in ('scope','revision'):
        from models import db,Ticket
        with app.app_context():
            obj=db.session.get(Ticket,'ticket-a')
            if change=='scope':obj.company_id=8
            else:obj.description='changed after submit'
            db.session.commit()
    elif change=='failure':monkeypatch.setattr(provider_fallback,'invoke_with_fallback',lambda *a,**k:{'status':'fail','error':'PRIVATE PROVIDER DETAIL'})
    else:
        def fail(*a,**k):raise RuntimeError('PRIVATE EXCEPTION DETAIL')
        monkeypatch.setattr(provider_fallback,'invoke_with_fallback',fail)
    with app.app_context():
        worker.OrchestrationWorker(app)._process_next_job()
        from models import db,OrchestrationJob
        assert db.session.get(OrchestrationJob,job).status=='failed'
        worker.OrchestrationWorker(app)._process_next_job()
    response=c.get('/api/live/tasks/'+job);assert 'PRIVATE' not in response.text
    if change=='scope':assert response.status_code==403
    else:assert response.json['status']=='failed'
    if change in ('scope','revision'):assert calls==[]


def test_flags_off_preserve_no_dispatch(tasks):
    app,c,_,_,_,calls,_=tasks;ctx=bound(c);app.config['NEXUS_LIVE_TASKS_ENABLED']=False
    assert submit(c,ctx).status_code==503;assert calls==[]


@pytest.mark.parametrize('cli',['opencode','claude','openclaude'])
def test_restricted_cli_never_bypasses_or_exposes_tools(monkeypatch,tmp_path,cli):
    import provider_fallback as mod
    monkeypatch.setattr(mod.shutil,'which',lambda _: '/fixture/cli')
    monkeypatch.setattr(mod,'_build_agent_run_env',lambda _: {})
    captured=[]
    monkeypatch.setattr(mod,'_invoke_cli_run',lambda cmd,env,*a,**kw:captured.append((cmd,env)) or {'status':'success'})
    token=mod._CLI_TOOL_POLICY.set('no_tools')
    try:result=mod._invoke_cli(cli,'fixture task',2,30,provider_id='fixture',model='fixture',cwd=tmp_path,env_overrides={'OPENAI_BASE_URL':'http://127.0.0.1:1234/v1','OPENAI_API_KEY':'synthetic-selected'})
    finally:mod._CLI_TOOL_POLICY.reset(token)
    if cli in ('claude','openclaude'):assert result['status']=='fail';assert captured==[];return
    cmd,env=captured[0];assert '--auto' not in cmd;assert '--dangerously-skip-permissions' not in cmd
    if cli=='claude':assert cmd[cmd.index('--tools')+1]=='';assert '--strict-mcp-config' in cmd
    else:
        config=json.loads(env['OPENCODE_CONFIG_CONTENT']);assert all(v=='deny' for v in config['permission'].values());assert config['permission']['bash']=='deny'
        assert all(v is False for v in config['tools'].values());assert config['agent']['build']['tools']['read'] is False


def test_tool_policy_is_per_invocation_and_resets_after_error(monkeypatch,tmp_path):
    import provider_fallback as mod
    seen=[]
    def invoke(**kw):
        seen.append(mod._CLI_TOOL_POLICY.get())
        if len(seen)==1:raise RuntimeError('fixture')
        return {'status':'success'}
    monkeypatch.setattr(mod,'_invoke_with_fallback_locked',invoke)
    with pytest.raises(RuntimeError):mod.invoke_with_fallback('fixture',cwd=tmp_path,tool_policy='no_tools')
    mod.invoke_with_fallback('fixture',cwd=tmp_path)
    assert seen==['no_tools',None]


def test_old_worker_cannot_pick_managed_pending_job(tasks):
    app,c,_,_,_,_,_=tasks;ctx=bound(c);submit(c,ctx)
    from models import OrchestrationJob
    with app.app_context():
        assert OrchestrationJob.query.filter_by(status='pending').count()==0
        assert OrchestrationJob.query.filter_by(status='live_pending').count()==1


def test_claim_prevents_reentrant_worker_dispatch(tasks,monkeypatch):
    app,c,_,_,_,_,worker=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    import provider_fallback
    count=[]
    def invoke(*a,**kw):
        count.append(1);worker.OrchestrationWorker(app)._process_next_job()
        return {'status':'success','output':'one invocation only'}
    monkeypatch.setattr(provider_fallback,'invoke_with_fallback',invoke)
    with app.app_context():worker.OrchestrationWorker(app)._process_next_job()
    assert count==[1];assert c.get('/api/live/tasks/'+job).json['status']=='success'


def test_revoked_agent_never_runs_and_retracts_event(tasks,monkeypatch):
    app,c,_,mod,service,calls,worker=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    monkeypatch.setattr(service,'has_agent_access',lambda *_:False)
    with app.app_context():worker.OrchestrationWorker(app)._process_next_job()
    assert calls==[];assert c.get('/api/live/tasks/'+job).status_code==403
    assert any(e.get('retracted') for e in post(c,ctx,'events').json['events'])


def test_pending_approval_blocks_even_if_ticket_flags_are_stale(tasks):
    app,c,_,_,_,calls,_=tasks;ctx=bound(c)
    from models import db,PendingApproval
    with app.app_context():
        db.session.add(PendingApproval(gate_type='publish',ticket_id='ticket-a',status='pending',
            idempotency_key='fixture-gate',created_at='2026-01-01T00:00:00.000000Z',
            expires_at='2030-01-01T00:00:00.000000Z'))
        db.session.commit()
    assert submit(c,ctx).status_code==403;assert calls==[]


def test_real_http_ui_dispatch_queue_and_result_in_chat(tasks, tmp_path):
    """Run actual TypeScript controller against the fixture Flask API/worker."""
    import subprocess
    import threading
    from pathlib import Path
    from flask import request
    from werkzeug.serving import make_server
    app,c,_,_,_,calls,worker=tasks
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app=ProxyFix(app.wsgi_app,x_host=1)  # localhost reverse proxy fixture only
    @app.after_request
    def run_fixture_worker(response):
        if request.path.endswith('/tasks') and request.method == 'POST' and response.status_code == 201:
            worker.OrchestrationWorker(app)._process_next_job()
        return response
    server=make_server('127.0.0.1',0,app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    fixture=tmp_path/'http-fixture.json'
    cookie=c.get_cookie('session',domain='example.test')
    fixture.write_text(json.dumps({'base':f'http://127.0.0.1:{server.server_port}','cookie':'session='+cookie.value}))
    root=Path(__file__).resolve().parents[2]
    try:
        result=subprocess.run(['node',str(root/'qa/managed-live-context/task-http-tests.cjs'),str(fixture)],cwd=root,text=True,capture_output=True,timeout=30)
        assert result.returncode == 0,result.stderr
        assert 'PASS actual localhost' in result.stdout
        assert len(calls)==1  # same SDK action retry never executes twice
    finally:
        server.shutdown();thread.join(timeout=5)
