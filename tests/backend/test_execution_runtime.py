"""Existing queue/ACL/idempotency with mock adapter only; no external provider."""
import copy
import json
import pytest
from tests.backend.test_live_task_dispatch import tasks, submit
from tests.backend.test_live_continuity_endpoints import bound, post
from tests.backend.test_managed_live_context import setup
from tests.backend.test_live_continuity_endpoints import enabled


@pytest.fixture
def routed(tasks, tmp_path, monkeypatch):
    app,c,login,mod,service,old_calls,worker=tasks
    import provider_fallback as pf
    import execution_runtime as runtime
    from execution_catalog import legacy_to_catalog
    config={"active_provider":"omnirouter","providers":{"omnirouter":{"cli_command":"opencode",
        "default_base_url":"https://synthetic.invalid/v1","model_chain":["first","second"],
        "env_vars":{"OPENAI_API_KEY":"PRIVATE_SELECTED"}}}}
    p=tmp_path/'providers.json';p.write_text(json.dumps(config))
    routing=tmp_path/'routing.yaml';routing.write_text('enabled: false')
    policy=tmp_path/'execution-policy.json'
    declarations={f'omnirouter:{alias}':{"verified_capabilities":["text_generation"],"evidence_ref":"fixture-only",
        "max_cost_per_attempt_usd":0.01,"approved_budget_usd":0.03} for alias in ['first','second']}
    value={"version":1,"catalog_revision":legacy_to_catalog(config).payload()["catalog_revision"],
        "expires_at":"2030-01-01T00:00:00+00:00","models":declarations,"max_attempts":2,"timeout_seconds":60}
    policy.write_text(json.dumps(value))
    monkeypatch.setattr(pf,'PROVIDERS_CONFIG',p);monkeypatch.setattr(pf,'ROUTING_CONFIG',routing)
    monkeypatch.setattr(runtime,'_attest_binary',lambda:True)
    monkeypatch.setattr(pf,'_availability_windows',lambda:{})
    monkeypatch.setattr(pf,'is_on_cooldown',lambda _:False)
    app.config.update(NEXUS_EXECUTION_ROUTING_ENABLED=True,NEXUS_EXECUTION_POLICY_PATH=str(policy))
    attempts=[]
    def adapter(*args,**kwargs):
        assert args[0]=='opencode' and pf._CLI_TOOL_POLICY.get()=='no_tools'
        assert kwargs['agent']=='' and kwargs['env_overrides']=={
            "OPENAI_BASE_URL":"https://synthetic.invalid/v1","OPENAI_API_KEY":"PRIVATE_SELECTED"}
        attempts.append(kwargs)
        return {"status":"success","output":"Delivered internal draft"}
    monkeypatch.setattr(pf,'_invoke_cli',adapter)
    return tasks, runtime, pf, attempts, policy, value, p


def run(routed, job):
    tasks,*_=routed
    app,c,_,_,_,_,worker=tasks
    with app.app_context():
        worker.OrchestrationWorker(app)._process_next_job()
    return c.get('/api/live/tasks/'+job)


def trace(routed,job):
    return routed[0][1].get('/api/execution/decisions/'+job)


def test_same_queue_idempotent_execution_durable_decision_and_delivered_result(routed):
    tasks,runtime,pf,attempts,*_=routed
    app,c,_,_,_,old_calls,worker=tasks;ctx=bound(c)
    first=submit(c,ctx);job=first.json['jobId']
    assert submit(c,ctx).json['jobId']==job and attempts==[]
    from models import db,ExecutionRouteDecision,OrchestrationJob
    with app.app_context():
        assert ExecutionRouteDecision.query.count()==1 and OrchestrationJob.query.count()==1
    response=run(routed,job)
    assert response.json['status']=='success' and response.json['output']=='Delivered internal draft'
    observed=trace(routed,job).json
    assert observed['intended']['model_id']=='omnirouter:first'
    assert observed['attempts'][0]['intended']['harness_id']=='opencode'
    assert observed['attempts'][0]['adapter_invoked']=='opencode_restricted_v1'
    assert observed['attempts'][0]['realized'] is None  # no upstream identity claimed
    assert observed['delivery_status']=='result_delivered'
    assert 'PRIVATE' not in json.dumps(observed) and 'Delivered internal draft' not in json.dumps(observed)
    assert response.json['routeDecisionReference']=='/api/execution/decisions/'+job
    run(routed,job)
    assert len(attempts)==1 and old_calls==[]


def test_attempt_is_saved_before_adapter_and_fallback_reason_is_bounded(routed,monkeypatch):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    from models import db,ExecutionRouteDecision
    def adapter(*args,**kwargs):
        stored=json.loads(db.session.get(ExecutionRouteDecision,job).trace)
        assert stored['attempts'][-1]['status']=='started'
        attempts.append(kwargs)
        return {"status":"timeout","error":"PRIVATE KEY traceback","output":""} if len(attempts)==1 else {"status":"success","output":"Draft second"}
    monkeypatch.setattr(pf,'_invoke_cli',adapter)
    assert run(routed,job).json['status']=='success'
    d=trace(routed,job).json
    assert len(d['attempts'])==2
    assert d['attempts'][1]['fallback_reason']=='timeout'
    assert d['attempts'][1]['intended']['model_id']=='omnirouter:second'
    assert 'PRIVATE' not in json.dumps(d)


@pytest.mark.parametrize('change',['policy','config','disabled','binary','scope','approval'])
def test_revalidation_at_worker_claim_blocks_without_adapter(routed,change,monkeypatch):
    tasks,runtime,pf,attempts,policy,value,config=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    from models import db,Ticket,Company
    if change=='policy':
        value['max_attempts']=1;policy.write_text(json.dumps(value))
    elif change=='config':
        cfg=json.loads(config.read_text());cfg['active_provider']='none';config.write_text(json.dumps(cfg))
    elif change=='disabled':app.config['NEXUS_EXECUTION_ROUTING_ENABLED']=False
    elif change=='binary':monkeypatch.setattr(runtime,'_attest_binary',lambda:False)
    else:
        with app.app_context():
            ticket=db.session.get(Ticket,'ticket-a')
            if change=='scope':ticket.company_id=8
            else:ticket.requires_human_approval=1
            db.session.commit()
    result=run(routed,job)
    assert attempts==[]
    if change=='scope':assert result.status_code==403
    else:assert result.json['status']=='failed'


@pytest.mark.parametrize('missing',['capabilities','budget','expired','unsupported','missing_policy'])
def test_unknown_capabilities_budget_or_adapter_never_imply_compatibility(routed,missing):
    tasks,runtime,pf,attempts,policy,value,config=routed
    app,c,*_=tasks
    if missing=='capabilities':
        for d in value['models'].values():d['verified_capabilities']=[]
    elif missing=='budget':
        for d in value['models'].values():d.pop('approved_budget_usd')
    elif missing=='expired':value['expires_at']='2000-01-01T00:00:00+00:00'
    elif missing=='unsupported':
        cfg=json.loads(config.read_text());cfg['providers']['omnirouter']['cli_command']='claude';config.write_text(json.dumps(cfg))
        from execution_catalog import legacy_to_catalog
        value['catalog_revision']=legacy_to_catalog(cfg).payload()['catalog_revision']
    if missing=='missing_policy':policy.unlink()
    else:policy.write_text(json.dumps(value))
    ctx=bound(c);job=submit(c,ctx).json['jobId']
    assert run(routed,job).json['status']=='failed'
    assert attempts==[] and trace(routed,job).json['status']=='blocked'


def test_empty_output_is_not_delivery_and_does_not_leak_provider_error(routed,monkeypatch):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    monkeypatch.setattr(pf,'_invoke_cli',lambda *a,**k:{"status":"success","output":" ","error":"PRIVATE"})
    assert run(routed,job).json['status']=='failed'
    d=trace(routed,job).json
    assert d['delivery_status']=='failed' and all(a['status']=='provider_failed' for a in d['attempts'])


def test_cancel_or_revocation_during_attempt_suppresses_result_and_fallback(routed,monkeypatch):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    def adapter(*a,**k):
        attempts.append(1)
        assert post(c,ctx,f'tasks/{job}/cancel').json['status']=='cancel_requested'
        return {"status":"success","output":"MUST_NOT_DELIVER"}
    monkeypatch.setattr(pf,'_invoke_cli',adapter)
    response=run(routed,job)
    assert response.json['status']=='cancelled' and response.json['output'] is None and attempts==[1]
    assert trace(routed,job).json['delivery_status']=='cancelled'


def test_decision_read_reuses_personal_user_and_company_revocation_acl(routed):
    tasks,*_=routed
    app,c,login,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    login(32);assert trace(routed,job).status_code==403
    login()
    assert c.get('/api/execution/decisions/'+job,headers={'X-Fixture-Token':'yes'}).status_code==403
    from models import db,Company
    with app.app_context():
        db.session.get(Company,7).status='inactive';db.session.commit()
    assert trace(routed,job).status_code==403


@pytest.mark.parametrize('value',[None,42,[],{},'not-a-date'])
def test_bad_policy_expiry_fails_closed_without_enqueue_error(routed,value):
    tasks,runtime,pf,attempts,path,policy,_=routed
    app,c,*_=tasks;policy['expires_at']=value;path.write_text(json.dumps(policy))
    ctx=bound(c);job=submit(c,ctx).json['jobId']
    assert run(routed,job).json['status']=='failed' and attempts==[]


def test_decision_created_atomically_and_replayed_request_never_replans(routed,monkeypatch):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    def forbidden(*a,**kw):raise AssertionError('idempotent request must not plan again')
    monkeypatch.setattr(runtime,'plan',forbidden)
    assert submit(c,ctx).json['jobId']==job
    assert attempts==[]


def test_existing_started_attempt_is_not_replayed(routed):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    from models import db,ExecutionRouteDecision
    with app.app_context():
        decision=db.session.get(ExecutionRouteDecision,job)
        value=json.loads(decision.trace);value['attempts']=[{'ordinal':1,'status':'started'}]
        decision.trace=json.dumps(value);db.session.commit()
    assert run(routed,job).json['status']=='failed' and attempts==[]
    assert trace(routed,job).json['attempts']==[{'ordinal':1,'status':'started'}]


def test_policy_switch_on_does_not_adopt_legacy_pending_job(routed):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;app.config['NEXUS_EXECUTION_ROUTING_ENABLED']=False
    ctx=bound(c);job=submit(c,ctx).json['jobId']
    app.config['NEXUS_EXECUTION_ROUTING_ENABLED']=True
    assert run(routed,job).json['status']=='failed' and attempts==[]
    assert trace(routed,job).status_code==403


def test_revocation_after_provider_success_does_not_expose_output_or_retry(routed,monkeypatch):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    from models import db,Ticket
    def adapter(*args,**kw):
        attempts.append(1)
        db.session.get(Ticket,'ticket-a').company_id=8;db.session.commit()
        return {'status':'success','output':'PRIVATE_OUTPUT'}
    monkeypatch.setattr(pf,'_invoke_cli',adapter)
    assert run(routed,job).status_code==403 and attempts==[1]
    assert trace(routed,job).status_code==403
    with app.app_context():
        from models import OrchestrationJob
        result=db.session.get(OrchestrationJob,job)
        assert result.status=='failed' and result.stage_result is None


@pytest.mark.parametrize('change',['policy','flag','ticket'])
def test_success_cannot_deliver_after_configuration_or_input_changed_in_call(routed,monkeypatch,change):
    tasks,runtime,pf,attempts,path,policy,_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    from models import db,Ticket
    def adapter(*args,**kwargs):
        attempts.append(1)
        if change=='policy':
            policy['timeout_seconds']=30;path.write_text(json.dumps(policy))
        elif change=='flag':app.config['NEXUS_EXECUTION_ROUTING_ENABLED']=False
        else:
            db.session.get(Ticket,'ticket-a').description='changed during generation';db.session.commit()
        return {'status':'success','output':'DO_NOT_EXPOSE'}
    monkeypatch.setattr(pf,'_invoke_cli',adapter)
    response=run(routed,job)
    assert response.json['status']=='failed' and response.json['output'] is None and attempts==[1]


def test_adapter_policy_context_is_restored_after_exception(routed,monkeypatch):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    before=pf._CLI_TOOL_POLICY.get()
    def fail(*args,**kwargs):raise RuntimeError('PRIVATE_DETAIL')
    monkeypatch.setattr(pf,'_invoke_cli',fail)
    assert run(routed,job).json['status']=='failed'
    assert pf._CLI_TOOL_POLICY.get()==before and 'PRIVATE' not in trace(routed,job).text


def test_binary_attestation_matches_committed_real_adapter_proof():
    import execution_runtime as runtime
    from pathlib import Path
    proof=json.loads((Path(__file__).resolve().parents[2]/'qa/live-cli-isolation/runtime-proof.json').read_text())
    assert runtime.PROOF_VERSION==proof['version'] and runtime.PROOF_SHA256==proof['binary_sha256']


def test_missing_binary_never_runs_cli_for_attestation(monkeypatch):
    import execution_runtime as runtime
    monkeypatch.setattr(runtime.shutil,'which',lambda _:None)
    assert runtime._attest_binary() is False


def test_internal_http_configured_omniroute_is_preserved_not_replaced(routed):
    tasks,runtime,pf,attempts,path,policy,config=routed
    app,c,*_=tasks
    cfg=json.loads(config.read_text());cfg['providers']['omnirouter']['default_base_url']='http://omniroute.internal:20128/v1'
    config.write_text(json.dumps(cfg))
    # Endpoint values are not catalog payload. Runtime guard fingerprint changes.
    with app.app_context():
        planned=runtime.plan('draft_ticket','agent-a')
    assert planned['intended']['provider_id']=='omnirouter'
    assert 'explicit_provider_unavailable' not in planned['intended']['reasons']


@pytest.mark.parametrize('source',['window','cooldown'])
def test_known_provider_unavailable_is_not_probed_or_forced(routed,monkeypatch,source):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks
    if source=='window':monkeypatch.setattr(pf,'_availability_windows',lambda:{'omnirouter':99999999999})
    else:monkeypatch.setattr(pf,'is_on_cooldown',lambda _:True)
    ctx=bound(c);job=submit(c,ctx).json['jobId']
    assert run(routed,job).json['status']=='failed' and attempts==[]
    assert all('provider_temporarily_unavailable' in route['reasons'] for route in trace(routed,job).json['candidates'])


def test_pathological_budget_number_fails_closed_without_float_overflow(routed):
    tasks,runtime,pf,attempts,path,policy,_=routed
    app,c,*_=tasks
    for d in policy['models'].values():d['approved_budget_usd']=10**500
    path.write_text(json.dumps(policy));ctx=bound(c);job=submit(c,ctx).json['jobId']
    assert run(routed,job).json['status']=='failed' and attempts==[]


def test_pending_cancel_has_durable_trace_without_worker_or_provider(routed):
    tasks,runtime,pf,attempts,*_=routed
    app,c,*_=tasks;ctx=bound(c);job=submit(c,ctx).json['jobId']
    assert post(c,ctx,f'tasks/{job}/cancel').json['status']=='cancelled'
    assert post(c,ctx,f'tasks/{job}/cancel').json['status']=='cancelled'
    decision=trace(routed,job).json
    assert decision['status']=='cancelled_before_attempt' and decision['delivery_status']=='cancelled'
    assert decision['attempts']==[] and attempts==[]
