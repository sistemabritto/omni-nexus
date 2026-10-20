"""Actual Flask ownership/store/round behavior; execution is always mocked."""
import importlib.util
import json
import sys
from pathlib import Path
from threading import Event, Thread
import pytest
from tests.backend.test_managed_live_context import setup, ORIGIN


@pytest.fixture
def party(setup, monkeypatch):
    app, client, signin, live, runtime, calls = setup
    for agent in ('agent-a', 'agent-b', 'agent-c', 'agent-d'):
        (live.AGENTS_DIR / (agent + '.md')).write_text('## Live Identity\nCurated identity ' + agent + '\n## Private\nPRIVATE_MEMORY_MUST_NOT_LEAK')
    monkeypatch.setattr(live, 'load_operational_squad', lambda: {a: {'active': a != 'agent-d'} for a in ('agent-a','agent-b','agent-c','agent-d')})
    path=Path(__file__).resolve().parents[2]/'dashboard/backend/routes/live_party.py'
    spec=importlib.util.spec_from_file_location('routes.live_party',path)
    mod=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,'routes.live_party',mod)
    spec.loader.exec_module(mod)
    app.register_blueprint(mod.bp)
    app.config.update(NEXUS_PARTY_MODE_ENABLED=True,NEXUS_EXECUTION_ROUTING_ENABLED=True,NEXUS_LIVE_COST_APPROVED=True)
    executions=[]
    monkeypatch.setattr(mod.execution_runtime,'plan',lambda op,agent:{'status':'planned','eligible_routes':[{'model_id':'fixture-model'}],'plan_revision':'fixture','attempts':[]})
    def execute(planned,op,agent,prompt,cwd,authorize,persist):
        authorize();executions.append({'op':op,'agent':agent,'prompt':prompt,'cwd':cwd})
        persist({'status':'provider_success','attempts':[{'status':'provider_success'}]})
        authorize()
        return {'status':'success','output':'Answer from '+agent}
    mod._fixture_real_execute = mod.execution_runtime.execute
    monkeypatch.setattr(mod.execution_runtime,'execute',execute)
    signin()
    return app,client,signin,live,mod,executions


def create(client,agents=None,company=7):
    return client.post('/api/live/party/sessions',json={'companyId':company,'agents':agents or ['agent-a','agent-b']},headers=ORIGIN)


def start(client,sid,text='Please compare options',key='request-one'):
    return client.post(f'/api/live/party/sessions/{sid}/rounds',json={'text':text,'requestId':key},headers=ORIGIN)


def next_turn(client,sid,rid,index=0):
    return client.post(f'/api/live/party/sessions/{sid}/rounds/{rid}/next',json={'expectedIndex':index},headers=ORIGIN)


def cancel(client,sid,rid):
    return client.post(f'/api/live/party/sessions/{sid}/rounds/{rid}/cancel',json={},headers=ORIGIN)


def test_explicit_round_separate_agents_shared_only_party_context_and_order(party):
    app,c,login,live,mod,executions=party
    session=create(c).json;sid=session['id'];rid=start(c,sid).json['roundId']
    assert executions==[]
    first=next_turn(c,sid,rid).json
    assert first['rounds'][0]['status']=='pending'
    assert first['messages'][-1]['agent']=='agent-a'
    # Repeated delivery of the same command cannot claim the next speaker.
    assert next_turn(c,sid,rid).json==first
    assert len(executions)==1
    final=next_turn(c,sid,rid,1).json
    assert final['rounds'][0]['status']=='completed'
    assert [e['agent'] for e in executions]==['agent-a','agent-b']
    assert 'Answer from agent-a' in executions[1]['prompt']
    for e in executions:
        assert e['op']=='party_turn' and not e['cwd'].exists()
        assert 'PRIVATE_MEMORY_MUST_NOT_LEAK' not in e['prompt']
        assert 'Ferramentas estão desabilitadas' in e['prompt']
    assert next_turn(c,sid,rid,1).json==final and len(executions)==2
    assert c.get('/api/live/party/sessions?companyId=7').json['session']==final
    assert c.get('/api/live/party/sessions?companyId=8').json=={'session':None}


@pytest.mark.parametrize('flag',['NEXUS_PARTY_MODE_ENABLED','NEXUS_EXECUTION_ROUTING_ENABLED','NEXUS_LIVE_COST_APPROVED'])
def test_default_disabled_and_string_true_do_not_enable(party,flag):
    app,c,_,_,_,executions=party
    app.config[flag]=False
    assert create(c).status_code in (403,503)
    app.config[flag]='true'
    assert create(c).status_code in (403,503)
    assert executions==[]


@pytest.mark.parametrize('agents',[['agent-a'],['agent-a']*2,['agent-a','agent-d'],['agent-a','unknown'],['agent-a','../secret'],['agent-a','agent-b','agent-c','agent-d'],['agent-a',True]])
def test_manifest_and_bounded_participants(party,agents):
    _,c,_,_,_,executions=party
    assert create(c,agents).status_code in (400,403)
    assert not executions


def test_guards_and_no_scope_overrides(party):
    app,c,login,_,_,executions=party
    assert create(c,company=True).status_code==400
    assert create(c,company=999).status_code==403
    assert c.post('/api/live/party/sessions',json={'companyId':7,'agents':['agent-a','agent-b']}).status_code==403
    assert c.get('/api/live/party/options',headers={'X-Fixture-Token':'yes'}).status_code==403
    session=create(c).json;sid=session['id'];rid=start(c,sid).json['roundId']
    login(32)
    assert c.get('/api/live/party/sessions/'+sid).status_code==403
    assert next_turn(c,sid,rid).status_code==403
    assert cancel(c,sid,rid).status_code==403
    assert not executions


def test_round_idempotency_busy_conflict_and_validation(party):
    _,c,_,_,_,executions=party
    sid=create(c).json['id'];first=start(c,sid).json
    replay=start(c,sid).json
    assert replay['replayed'] and replay['roundId']==first['roundId']
    assert start(c,sid,text='Changed').status_code==409
    assert start(c,sid,key='another').status_code==409
    assert start(c,sid,text='').status_code==400
    assert start(c,sid,text='x'*4001).status_code==400
    assert next_turn(c,sid,first['roundId'],True).status_code==400
    assert next_turn(c,sid,'foreign-round').status_code==403
    assert not executions


def test_cancel_before_execution_and_after_feature_disabled(party):
    app,c,_,_,_,executions=party
    sid=create(c).json['id'];rid=start(c,sid).json['roundId']
    app.config['NEXUS_PARTY_MODE_ENABLED']=False
    assert cancel(c,sid,rid).json['rounds'][0]['status']=='cancelled'
    app.config['NEXUS_PARTY_MODE_ENABLED']=True
    assert next_turn(c,sid,rid).json['rounds'][0]['status']=='cancelled'
    assert not executions


@pytest.mark.parametrize('cause',['failed','exception','ineligible'])
def test_failed_or_ineligible_turn_stops_remaining_agents(party,monkeypatch,cause):
    _,c,_,_,mod,executions=party
    sid=create(c).json['id'];rid=start(c,sid).json['roundId']
    if cause=='ineligible':monkeypatch.setattr(mod.execution_runtime,'plan',lambda *_:{'status':'blocked','eligible_routes':[]})
    elif cause=='exception':monkeypatch.setattr(mod.execution_runtime,'execute',lambda *args:(_ for _ in ()).throw(RuntimeError('secret detail')))
    else:monkeypatch.setattr(mod.execution_runtime,'execute',lambda *args:{'status':'failed','output':'should not display'})
    data=next_turn(c,sid,rid).json
    assert data['rounds'][0]['status']=='failed' and len(data['messages'])==1
    assert 'secret detail' not in json.dumps(data)
    assert next_turn(c,sid,rid,1).json==data


@pytest.mark.parametrize('flag',['NEXUS_PARTY_MODE_ENABLED','NEXUS_LIVE_COST_APPROVED','NEXUS_EXECUTION_ROUTING_ENABLED'])
def test_revoked_consumption_or_feature_blocks_delivery(party,monkeypatch,flag):
    app,c,_,_,mod,_=party
    sid=create(c).json['id'];rid=start(c,sid).json['roundId']
    def execute(*args):
        app.config[flag]=False
        return {'status':'success','output':'must not display'}
    monkeypatch.setattr(mod.execution_runtime,'execute',execute)
    result=next_turn(c,sid,rid)
    assert result.status_code==200
    assert result.json['rounds'][0]['status']=='failed' and len(result.json['messages'])==1


@pytest.mark.parametrize('revocation',['agent','company','user'])
def test_scope_revoked_mid_call_withholds_output(party,monkeypatch,revocation):
    app,c,_,live,mod,_=party
    from models import db,Company,User
    sid=create(c).json['id'];rid=start(c,sid).json['roundId']
    def execute(*args):
        if revocation=='agent':monkeypatch.setattr(live,'has_agent_access',lambda *_:False)
        elif revocation=='company':db.session.get(Company,7).status='inactive';db.session.commit()
        else:db.session.get(User,31).is_active=False;db.session.commit()
        return {'status':'success','output':'must not display'}
    monkeypatch.setattr(mod.execution_runtime,'execute',execute)
    result=next_turn(c,sid,rid)
    assert result.status_code==403 and 'must not display' not in result.text
    with app.app_context(),live._store() as conn:
        assert conn.execute('SELECT COUNT(*) FROM live_party_messages').fetchone()[0]==1


def test_existing_running_claim_is_never_replayed_after_restart(party):
    app,c,_,live,mod,executions=party
    sid=create(c).json['id'];rid=start(c,sid).json['roundId']
    with app.app_context(),live._store() as conn:
        conn.execute("UPDATE live_party_rounds SET status='running',trace=? WHERE id=?",(json.dumps({'attempts':[{'status':'started'}]}),rid))
    assert next_turn(c,sid,rid).status_code==202
    assert not executions
    assert cancel(c,sid,rid).json['rounds'][0]['status']=='cancelled'


def test_concurrent_claim_and_cancel_discard_late_result(party,monkeypatch):
    app,c,_,_,mod,executions=party
    sid=create(c).json['id'];rid=start(c,sid).json['roundId']
    entered,release=Event(),Event()
    def execute(*args):
        executions.append('only-call');entered.set();assert release.wait(5)
        return {'status':'success','output':'late result'}
    monkeypatch.setattr(mod.execution_runtime,'execute',execute)
    other=app.test_client()
    with other.session_transaction() as s:s['_user_id']='31';s['_fresh']=True
    results=[]
    thread=Thread(target=lambda:results.append(next_turn(other,sid,rid)))
    thread.start();assert entered.wait(5)
    try:
        assert next_turn(c,sid,rid).status_code==202
        assert cancel(c,sid,rid).json['rounds'][0]['status']=='cancelled'
    finally:release.set();thread.join(5)
    assert len(executions)==1 and results[0].status_code==200
    assert len(results[0].json['messages'])==1


def test_new_round_limit_and_curated_identity_required(party,monkeypatch):
    _,c,_,live,mod,_=party
    sid=create(c).json['id']
    for n in range(mod.MAX_ROUNDS):
        rid=start(c,sid,key='round-'+str(n)).json['roundId'];cancel(c,sid,rid)
    assert start(c,sid,key='over-limit').status_code==409
    (live.AGENTS_DIR/'agent-b.md').write_text('No curated identity')
    assert create(c).json['error']=='party_identity_unavailable'


def test_real_restricted_executor_adapter_is_no_tools_and_independent_per_agent(party, monkeypatch):
    _,c,_,_,mod,_=party
    import provider_fallback as pf
    calls=[]
    planned={'status':'planned','eligible_routes':[{'harness_id':'opencode','provider_id':'fixture','model_id':'fixture:model','model':'fixture-model'}],
             'plan_revision':'fixture','attempts':[],'timeout_seconds':20}
    monkeypatch.setattr(mod.execution_runtime,'plan',lambda *_:planned)
    monkeypatch.setattr(mod.execution_runtime,'execute',mod._fixture_real_execute)
    monkeypatch.setattr(mod.execution_runtime,'_load',lambda:({'providers':{'fixture':{'default_base_url':'https://synthetic.invalid/v1'}}},{},{}))
    monkeypatch.setattr(pf,'_get_api_key',lambda *_:'fixture-only')
    def adapter(*args,**kwargs):
        assert pf._CLI_TOOL_POLICY.get()=='no_tools'
        assert args[0]=='opencode' and args[2]==2 and kwargs['agent']==''
        assert kwargs['model']=='fixture-model'
        assert kwargs['cwd'].is_dir()
        calls.append(args[1])
        return {'status':'success','output':'Restricted fixture answer'}
    monkeypatch.setattr(pf,'_invoke_cli',adapter)
    sid=create(c).json['id'];rid=start(c,sid).json['roundId']
    assert next_turn(c,sid,rid).json['rounds'][0]['status']=='pending'
    assert next_turn(c,sid,rid,1).json['rounds'][0]['status']=='completed'
    assert len(calls)==2 and 'Curated identity agent-a' in calls[0] and 'Curated identity agent-b' in calls[1]


def test_output_limit_is_explicit_and_history_is_bounded(party, monkeypatch):
    _,c,_,_,mod,_=party
    prompts=[]
    def execute(planned,op,agent,prompt,*args):
        prompts.append(prompt)
        return {'status':'success','output':'x' * 10000}
    monkeypatch.setattr(mod.execution_runtime,'execute',execute)
    sid=create(c).json['id']
    for n in range(3):
        rid=start(c,sid,text='question '+str(n)+'?'*3990,key='large-'+str(n)).json['roundId']
        next_turn(c,sid,rid)
        result=next_turn(c,sid,rid,1).json
    assert len(result['messages'][-1]['text'])<=mod.MAX_OUTPUT
    assert 'Resposta truncada' in result['messages'][-1]['text']
    assert max(map(len,prompts))<22000
