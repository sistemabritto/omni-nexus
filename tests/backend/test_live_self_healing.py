"""GitHub/VPS contracts exercised without network, SSH, Docker or paid providers."""
import importlib.util
import json
from pathlib import Path
import pytest
from tests.backend.test_live_adapters import adapters,operate,approve
from tests.backend.test_live_experience import experience
from tests.backend.test_managed_live_context import setup,ORIGIN

ROOT=Path(__file__).resolve().parents[2]
BASE='1'*40;TREE='2'*40;COMMIT='3'*40


@pytest.fixture
def pipeline(adapters,tmp_path,monkeypatch):
    import live_self_healing as mod
    policy=tmp_path/'pipeline.json';policy.write_text(json.dumps({'version':1,'ciWorkflows':['ci.yml'],'rollout':{'enabled':False}}))
    monkeypatch.setattr(mod,'POLICY',policy)
    monkeypatch.setattr(mod,'_principal',lambda row:{'owner':'fixture','repositories':'*','write':True,'delete':False})
    monkeypatch.setattr(mod,'_workflow',lambda *args:'verified-workflow-hash')
    monkeypatch.setattr(mod,'_head',lambda *args:BASE)
    def unmocked_request(*args,**kwargs):
        raise AssertionError('A pipeline test must supply its own synthetic GitHub response')
    monkeypatch.setattr(mod,'_request',unmocked_request)
    return mod,adapters


def test_multi_file_commit_updates_ref_once_without_force(pipeline,monkeypatch):
    mod,_=pipeline;calls=[];head=BASE
    def request(method,path,**kwargs):
        nonlocal head
        calls.append((method,path,kwargs.get('body')))
        if method=='GET':return {'tree':{'sha':TREE},'object':{'sha':head}},False
        if path.endswith('/git/trees'):return {'sha':TREE},False
        if path.endswith('/git/commits'):return {'sha':COMMIT},False
        if method=='PATCH':head=COMMIT;return {},False
        raise AssertionError((method,path))
    monkeypatch.setattr(mod,'_request',request);monkeypatch.setattr(mod,'_head',lambda *args:head)
    row={'agent_name':'bolt-executor'}
    args={
        'repository':'fixture/repo','branch':'fix/example','headSha':BASE,'message':'Fix',
        'files':[{'path':'src/app.py','content':'changed'},{'path':'tests/test_app.py','content':'checks'}]}
    proposal=mod.prepare(row,{},'commit',args)
    result=mod.perform(row,proposal,'job')
    assert result['sha']==COMMIT
    refs=[c for c in calls if c[0]=='PATCH'];assert len(refs)==1 and refs[0][2]=={'sha':COMMIT,'force':False}
    tree=next(c[2] for c in calls if c[1].endswith('/git/trees'))
    assert tree['base_tree']==TREE and len(tree['tree'])==2
    assert all(f['content'] and 'sha' not in f for f in tree['tree'])
    assert not any(c[0]=='DELETE' for c in calls)


def test_revocation_mid_commit_prevents_ref_update(pipeline,monkeypatch):
    mod,_=pipeline;writes=[]
    def request(method,path,**kwargs):
        if method=='POST':writes.append(path);return {'sha':TREE},False
        return {'tree':{'sha':TREE},'object':{'sha':BASE}},False
    monkeypatch.setattr(mod,'_request',request)
    # Prepare while authorized, then revoke as soon as the first object is made.
    monkeypatch.setattr(mod,'_principal',lambda row:{'owner':'fixture','repositories':'*','write':True,'delete':False})
    row={'agent_name':'bolt-executor'}
    args={
        'repository':'fixture/repo','branch':'fix/example','headSha':BASE,'message':'Fix',
        'files':[{'path':'src/app.py','content':'changed'}]}
    proposal=mod.prepare(row,{},'commit',args)
    scope=mod._principal(row)
    def principal(row):
        if writes:raise PermissionError()
        return scope
    monkeypatch.setattr(mod,'_principal',principal)
    with pytest.raises(PermissionError):mod.perform(row,proposal,'job')
    assert writes==['repos/fixture/repo/git/trees']


def test_production_cannot_be_unlocked_by_yolo_or_safe_flag(pipeline):
    _,(_,_,c,ctx,effects)=pipeline
    args={'repository':'fixture/repo','branch':'fix/example','headSha':BASE,
          'image':'excarplex/evo-nexus-dashboard@sha256:'+'a'*64,
          'previousImage':'excarplex/evo-nexus-dashboard@sha256:'+'b'*64,'ciRunId':1,'buildRunId':2}
    result=operate(c,ctx,'github','rollout',args)
    assert result.status_code==400 and result.json['error']=='pipeline_rollout_not_configured'
    assert not effects
    assert operate(c,ctx,'github','rollout',{**args,'safe':True},'no-safe-override').status_code==400


def test_expired_human_approval_never_reaches_executor(adapters):
    _,app,c,ctx,effects=adapters
    result=operate(c,ctx,'routines','create',{'name':'Report','script':'daily_status_report.py','frequency':'daily','time':'09:00'})
    from routes.live_experience import live
    with app.app_context(),live._store() as conn:conn.execute('UPDATE live_action_approvals SET expires_at=1 WHERE id=?',(result.json['approvalId'],))
    assert approve(c,ctx,result).status_code==409 and not effects


def test_verified_production_still_needs_human_and_returns_a_real_pending_job(pipeline,monkeypatch):
    mod,(_,_,c,ctx,effects)=pipeline
    mod.POLICY.write_text(json.dumps({'version':1,'ciWorkflows':['ci.yml'],'rollout':{
        'enabled':True,'repository':'fixture/repo','workflow':'live-rollout.yml','environment':'production'}}))
    monkeypatch.setattr(mod,'_verified_file',lambda *a:'verified-executor-hash')
    reads=[]
    def request(method,path,**kwargs):
        assert method=='GET';reads.append(path)
        if path.endswith('/environments/production'):return {'protection_rules':[]},False
        return {'head_sha':BASE,'status':'completed','conclusion':'success','path':'.github/workflows/'+('ci.yml' if path.endswith('/1') else 'docker-publish-britto.yml')},False
    monkeypatch.setattr(mod,'_request',request)
    starts=[]
    class Thread:
        def __init__(self,**kwargs):starts.append(kwargs)
        def start(self):pass
    monkeypatch.setattr(mod.threading,'Thread',Thread)
    args={'repository':'fixture/repo','branch':'fix/example','headSha':BASE,
          'image':'excarplex/evo-nexus-dashboard@sha256:'+'a'*64,
          'previousImage':'excarplex/evo-nexus-dashboard@sha256:'+'b'*64,'ciRunId':1,'buildRunId':2}
    pending=operate(c,ctx,'github','rollout',args)
    assert pending.status_code==200 and pending.json['approvalRequired'] and not starts
    result=approve(c,ctx,pending)
    assert result.status_code==200,result.json
    job=result.json['data'];assert job['status']=='pending' and len(job['jobId'])==32
    assert len(starts)==1 and not effects
    state=operate(c,ctx,'github','status',{'jobId':job['jobId']},'read-job')
    assert state.status_code==200 and state.json['status']=='pending'


def test_operator_can_require_additional_environment_review(pipeline,monkeypatch):
    mod,(_,_,c,ctx,effects)=pipeline
    mod.POLICY.write_text(json.dumps({'version':1,'ciWorkflows':['ci.yml'],'rollout':{
        'enabled':True,'repository':'fixture/repo','workflow':'live-rollout.yml',
        'environment':'production','requireEnvironmentReview':True}}))
    def request(method,path,**kwargs):
        assert method=='GET'
        if path.endswith('/environments/production'):return {'protection_rules':[]},False
        return {'head_sha':BASE,'status':'completed','conclusion':'success','path':'.github/workflows/'+('ci.yml' if path.endswith('/1') else 'docker-publish-britto.yml')},False
    monkeypatch.setattr(mod,'_request',request)
    result=operate(c,ctx,'github','rollout',{'repository':'fixture/repo','branch':'fix/example','headSha':BASE,
        'image':'excarplex/evo-nexus-dashboard@sha256:'+'a'*64,
        'previousImage':'excarplex/evo-nexus-dashboard@sha256:'+'b'*64,'ciRunId':1,'buildRunId':2})
    assert result.status_code==400 and result.json['error']=='pipeline_production_review_not_configured'
    assert not effects


def test_executor_rejects_non_digest_and_revision_mismatch_without_deploy(monkeypatch):
    spec=importlib.util.spec_from_file_location('live_rollout',ROOT/'scripts/ci/live_rollout.py')
    executor=importlib.util.module_from_spec(spec);spec.loader.exec_module(executor)
    calls=[]
    monkeypatch.setattr(executor,'command',lambda *args:calls.append(args) or '')
    with pytest.raises(ValueError):executor.rollout('image:latest',BASE,'image:previous')
    assert not calls
    previous='excarplex/evo-nexus-dashboard@sha256:'+'b'*64
    monkeypatch.setattr(executor,'inspect',lambda *args:{'Spec':{'TaskTemplate':{'ContainerSpec':{'Image':previous}}}} if args[0]=='service' else {'Config':{'Labels':{'org.opencontainers.image.revision':'wrong'}}})
    with pytest.raises(RuntimeError,match='revision_mismatch'):executor.rollout('excarplex/evo-nexus-dashboard@sha256:'+'a'*64,BASE,previous)
    assert not any('update' in call for call in calls)


def test_search_filters_private_urls_and_never_follows_result_sites(adapters,monkeypatch):
    import live_adapter_content as content
    monkeypatch.setenv('BRAVE_SEARCH_API_KEY','synthetic-brave-key')
    calls=[]
    class Response:
        status_code=200
        def json(self):return {'web':{'results':[{'url':'https://example.org/article','title':'Public','description':'Reference'},
            {'url':'https://127.0.0.1/private'},{'url':'https://service.internal/secret'},
            {'url':'https://user:password@example.org/private'}]}}
    monkeypatch.setattr(content.requests,'get',lambda url,**kw:calls.append((url,kw)) or Response())
    result=content.search({'query':'public question','count':5})
    assert len(result['results'])==1
    assert len(calls)==1 and calls[0][0]=='https://api.search.brave.com/res/v1/web/search'
    assert calls[0][1]['allow_redirects'] is False
    assert 'synthetic-brave-key' not in json.dumps(result)


def test_alert_cooldown_and_disabled_preferences(tmp_path):
    import sqlite3
    from live_heartbeat_alerts import ensure,DEFAULT,reserve
    path=tmp_path/'alerts.db'
    with sqlite3.connect(path) as conn:
        ensure(conn);conn.execute('INSERT INTO live_heartbeat_alerts VALUES(?,?,?,?,?)',('hb',31,7,json.dumps(DEFAULT),0))
    assert reserve('hb','timeout',path=path,now=1000)
    assert not reserve('hb','timeout',path=path,now=1001)
    assert reserve('hb','timeout',path=path,now=1301)
    with sqlite3.connect(path) as conn:conn.execute('UPDATE live_heartbeat_alerts SET preferences=?',(json.dumps({**DEFAULT,'enabled':False}),))
    assert not reserve('hb','timeout',path=path,now=5000)


def _ci_proposal(mod):
    return mod.prepare({'user_id':31,'company_id':7,'agent_name':'agent-a'}, {}, 'ci', {
        'repository':'fixture/repo','branch':'fix/example','headSha':BASE,'workflow':'ci.yml'})


def _stored_job(mod,app,proposal,*,state='uncertain',checkpoint=None,ident='a'*32,result=None,agent='agent-a'):
    from routes.live_experience import live
    from live_approval_policy import cipher
    with app.app_context(),live._store() as conn:
        mod.ensure(conn)
        encrypt=lambda value:'enc:'+cipher().encrypt(json.dumps(value).encode()).decode()
        conn.execute(
            '''INSERT INTO live_pipeline_jobs(id,user_id,company_id,agent_name,operation,
               request_id,parameters,status,result,created_at,checkpoint)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (ident,31,7,agent,proposal['operation'],ident,encrypt(proposal),state,
             json.dumps(result) if result else None,100,encrypt(checkpoint) if checkpoint else None))
    return ident


def _workflow_run(ident,**changes):
    return {'id':123,'display_title':'Live '+ident,'head_sha':BASE,
            'head_branch':'fix/example','event':'workflow_dispatch',
            'path':'.github/workflows/ci.yml','head_repository':{'full_name':'fixture/repo'},
            'status':'completed','conclusion':'success',**changes}


def _job_status(mod,app,ident,row=None):
    with app.app_context():
        return mod.status(row or {'user_id':31,'company_id':7,'agent_name':'agent-a'},ident)


def test_worker_revalidates_approved_policy_before_any_mutation(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='pending')
    policy=json.loads(mod.POLICY.read_text());policy['ciWorkflows']=[]
    mod.POLICY.write_text(json.dumps(policy))
    calls=[]
    monkeypatch.setattr(mod,'_request',lambda *a,**kw:calls.append((a,kw)))
    mod.run_job(app,{'user_id':31,'company_id':7,'agent_name':'agent-a'},ident)
    assert not calls
    from routes.live_experience import live
    with app.app_context(),live._store() as conn:
        job=conn.execute('SELECT * FROM live_pipeline_jobs WHERE id=?',(ident,)).fetchone()
        assert job['status']=='blocked' and json.loads(job['result'])['error']=='scope_denied'


def test_worker_rejects_substituted_identity_without_claiming_job(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='pending')
    monkeypatch.setattr(mod,'perform',lambda *a,**kw:pytest.fail('Must not execute'))
    mod.run_job(app,{'user_id':32,'company_id':7,'agent_name':'agent-a'},ident)
    result=_job_status(mod,app,ident)
    assert result['status']=='pending'
    assert result['recovery']['evidence']=='awaiting_worker_no_replay'


def test_execution_scope_rechecks_repository_allowlist(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    monkeypatch.setattr(mod,'_principal',lambda row:{
        'owner':'fixture','repositories':['different'],'write':True,'delete':False})
    monkeypatch.setattr(mod,'_request',lambda *a,**kw:pytest.fail('No remote call allowed'))
    with app.app_context(),pytest.raises(PermissionError):
        mod.perform({'agent_name':'agent-a'},proposal,'job')


def test_policy_change_mid_commit_blocks_visible_ref_update(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    writes=[]
    def request(method,path,**kwargs):
        if method=='GET':return {'tree':{'sha':TREE},'object':{'sha':BASE}},False
        writes.append(path)
        mod.POLICY.write_text(json.dumps({'version':1,'ciWorkflows':[],'rollout':{'enabled':False}}))
        return {'sha':TREE},False
    monkeypatch.setattr(mod,'_request',request)
    args={'repository':'fixture/repo','branch':'fix/example','headSha':BASE,
          'message':'Fix','files':[{'path':'src/app.py','content':'changed'}]}
    from live_adapter_errors import AdapterError
    with app.app_context():
        proposal=mod.prepare({'agent_name':'bolt-executor'},{},'commit',args)
        with pytest.raises(AdapterError,match='approval_target_changed'):
            mod.perform({'agent_name':'bolt-executor'},proposal,'job')
    assert writes==['repos/fixture/repo/git/trees']


def test_interrupted_commit_reconciles_exact_checkpoint_without_replay(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    proposal={'operation':'commit','args':{'repository':'fixture/repo','branch':'fix/example','headSha':BASE}}
    ident=_stored_job(mod,app,proposal,checkpoint={'stage':'commit_created','sha':COMMIT})
    calls=[]
    def request(method,path,**kwargs):
        calls.append((method,path))
        assert method=='GET'
        return {'object':{'sha':COMMIT}},False
    monkeypatch.setattr(mod,'_request',request)
    result=_job_status(mod,app,ident)
    assert result['status']=='success' and result['result']['sha']==COMMIT
    assert result['recovery']['automaticReplayAllowed'] is False
    assert _job_status(mod,app,ident)['status']=='success'
    assert calls==[('GET','repos/fixture/repo/git/ref/heads/fix/example')]


@pytest.mark.parametrize('checkpoint,head',[
    (None,COMMIT),
    ({'stage':'commit_created','sha':COMMIT},BASE),
    ({'stage':'commit_created','sha':'invalid'},COMMIT),
])
def test_unproven_commit_remains_uncertain(pipeline,monkeypatch,checkpoint,head):
    mod,(_,app,_,_,_)=pipeline
    proposal={'operation':'commit','args':{'repository':'fixture/repo','branch':'fix/example','headSha':BASE}}
    ident=_stored_job(mod,app,proposal,checkpoint=checkpoint)
    def request(method,path,**kwargs):
        assert method=='GET'
        return {'object':{'sha':head}},False
    monkeypatch.setattr(mod,'_request',request)
    result=_job_status(mod,app,ident)
    assert result['status']=='uncertain' and result['recovery']['evidence']=='inconclusive_no_replay'


def test_lost_dispatch_response_recovers_exact_workflow_evidence(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,checkpoint={'stage':'dispatch_intent','workflow':'ci.yml'})
    calls=[]
    def request(method,path,**kwargs):
        calls.append((method,path,kwargs))
        assert method=='GET'
        return {'workflow_runs':[_workflow_run(ident)]},False
    monkeypatch.setattr(mod,'_request',request)
    result=_job_status(mod,app,ident)
    assert result['status']=='success' and result['result']['executionComplete'] is True
    assert result['result']['url']=='https://github.com/fixture/repo/actions/runs/123'
    assert len(calls)==1 and calls[0][1]=='repos/fixture/repo/actions/workflows/ci.yml/runs'


@pytest.mark.parametrize('change',[
    {'path':'.github/workflows/unreviewed.yml'},
    {'head_branch':'main'},
    {'event':'push'},
    {'head_repository':{'full_name':'other/repo'}},
    {'head_sha':COMMIT},
    {'display_title':'Live other'},
    {'conclusion':None},
    {'id':True},
])
def test_workflow_reconciliation_rejects_partial_or_wrong_evidence(pipeline,monkeypatch,change):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,checkpoint={'stage':'dispatch_intent','workflow':'ci.yml'})
    def request(method,path,**kwargs):
        assert method=='GET'
        return {'workflow_runs':[_workflow_run(ident,**change)]},False
    monkeypatch.setattr(mod,'_request',request)
    result=_job_status(mod,app,ident)
    assert result['status']=='uncertain' and not result['result']


@pytest.mark.parametrize('exhausted',[False,True])
def test_ambiguous_or_incomplete_run_scan_never_claims_success(pipeline,monkeypatch,exhausted):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='dispatched')
    pages=[]
    def request(method,path,**kwargs):
        assert method=='GET'
        page=kwargs['params']['page'];pages.append(page)
        runs=[_workflow_run(ident,id=123+page)] if page==1 or not exhausted else []
        return {'workflow_runs':runs},True
    monkeypatch.setattr(mod,'_request',request)
    result=_job_status(mod,app,ident)
    assert result['status']=='dispatched' and result['recovery']['evidence']=='inconclusive_no_replay'
    assert pages==([1,2,3] if exhausted else [1,2])


def test_status_uses_current_repository_scope_and_owner_before_network(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='dispatched')
    monkeypatch.setattr(mod,'_request',lambda *a,**kw:pytest.fail('No remote call allowed'))
    with pytest.raises(PermissionError):
        _job_status(mod,app,ident,{'user_id':32,'company_id':7,'agent_name':'agent-a'})
    with pytest.raises(PermissionError):
        _job_status(mod,app,ident,{'user_id':31,'company_id':8,'agent_name':'agent-a'})
    monkeypatch.setattr(mod,'_principal',lambda row:{
        'owner':'fixture','repositories':[],'write':True,'delete':False})
    with pytest.raises(PermissionError):_job_status(mod,app,ident)


def test_submission_idempotency_checks_payload_and_agent(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    starts=[]
    class Thread:
        def __init__(self,**kwargs):starts.append(kwargs)
        def start(self):pass
    monkeypatch.setattr(mod.threading,'Thread',Thread)
    row={'user_id':31,'company_id':7,'agent_name':'agent-a'}
    with app.app_context():
        proposal=_ci_proposal(mod)
        first=mod.submit(row,proposal,'request')
        replay=mod.submit(row,proposal,'request')
        assert replay['jobId']==first['jobId'] and replay['replayed'] is True
        with pytest.raises(ValueError,match='idempotency_conflict'):
            mod.submit(row,{**proposal,'guard':'changed'},'request')
        with pytest.raises(ValueError,match='idempotency_conflict'):
            mod.submit({**row,'agent_name':'agent-b'},proposal,'request')
    assert len(starts)==1


def test_worker_does_not_overwrite_reconciled_terminal_result(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='pending')
    from routes.live_experience import live
    def perform(row,proposal,job_id,checkpoint):
        with live._store() as conn:
            conn.execute("UPDATE live_pipeline_jobs SET status='success',result=? WHERE id=?",
                (json.dumps({'runId':123,'executionComplete':True}),job_id))
        return {'dispatched':True}
    monkeypatch.setattr(mod,'perform',perform)
    mod.run_job(app,{'user_id':31,'company_id':7,'agent_name':'agent-a'},ident)
    result=_job_status(mod,app,ident)
    assert result['status']=='success' and result['result']['executionComplete'] is True


@pytest.mark.parametrize('value',['not json','[]','{"version":2}','{"version":1,"rollout":null}'])
def test_diagnostics_fail_closed_without_changing_approval_or_rollout(pipeline,value):
    mod,(_,app,_,_,_)=pipeline
    mod.POLICY.write_text(value)
    result=mod.diagnostics({'agent_name':'agent-a'})
    assert result['policyAvailable'] is False and result['rolloutPolicyEnabled'] is False
    assert result['mutationsRequireHumanApproval'] is True and result['automaticReplayAllowed'] is False
    assert result['commitAgentEligible'] is False and result['credentialPermissionsVerified'] is False


def test_versioned_policy_remains_disabled_and_no_privilege_expansion():
    policy=json.loads((ROOT/'config/live-self-healing.json').read_text())
    assert policy['rollout']['enabled'] is False
    from live_self_healing import diagnostics,PROTECTED
    value=diagnostics({'agent_name':'bolt-executor'})
    assert value['commitAgentEligible'] is True and value['protectedBranchesAllowed'] is False
    assert 'config/live-' in PROTECTED and '.github/' in PROTECTED


def test_real_worker_lost_dispatch_response_is_observed_not_replayed(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    from live_adapter_errors import AdapterError
    from live_approval_policy import unpack
    from routes.live_experience import live
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='pending')
    mutations=[]
    def request(method,path,**kwargs):
        if method=='POST':
            mutations.append(path)
            raise AdapterError('github_network_unavailable',503)
        if path.endswith('/runs'):return {'workflow_runs':[_workflow_run(ident)]},False
        return {'object':{'sha':BASE}},False
    monkeypatch.setattr(mod,'_request',request)
    row={'user_id':31,'company_id':7,'agent_name':'agent-a'}
    mod.run_job(app,row,ident)
    with app.app_context(),live._store() as conn:
        job=conn.execute('SELECT * FROM live_pipeline_jobs WHERE id=?',(ident,)).fetchone()
        assert job['status']=='uncertain' and job['checkpoint'].startswith('enc:')
        assert json.loads(unpack(job['checkpoint']))=={'stage':'dispatch_intent','workflow':'ci.yml'}
        assert job['updated_at']>job['created_at']
    mod.run_job(app,row,ident)  # A duplicate invocation cannot claim uncertain.
    result=_job_status(mod,app,ident)
    assert result['status']=='success'
    assert mutations==['repos/fixture/repo/actions/workflows/ci.yml/dispatches']


def test_real_worker_lost_ref_response_recovers_checkpoint_once(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    from live_adapter_errors import AdapterError
    head=BASE;mutations=[]
    def request(method,path,**kwargs):
        nonlocal head
        if method=='GET':return {'object':{'sha':head},'tree':{'sha':TREE}},False
        mutations.append((method,path))
        if path.endswith('/git/trees'):return {'sha':TREE},False
        if path.endswith('/git/commits'):return {'sha':COMMIT},False
        if method=='PATCH':
            head=COMMIT
            raise AdapterError('github_network_unavailable',503)
        raise AssertionError(path)
    monkeypatch.setattr(mod,'_request',request)
    args={'repository':'fixture/repo','branch':'fix/example','headSha':BASE,
          'message':'Fix','files':[{'path':'src/app.py','content':'changed'}]}
    row={'user_id':31,'company_id':7,'agent_name':'bolt-executor'}
    with app.app_context():proposal=mod.prepare(row,{},'commit',args)
    ident=_stored_job(mod,app,proposal,state='pending',agent='bolt-executor')
    mod.run_job(app,row,ident)
    mod.run_job(app,row,ident)
    result=_job_status(mod,app,ident,row)
    assert result['status']=='success' and result['result']['sha']==COMMIT
    assert [method for method,_ in mutations]==['POST','POST','PATCH']


def test_two_workers_claim_one_pending_job(pipeline,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='pending')
    entered=Event();release=Event();calls=[]
    def perform(*args,**kwargs):
        calls.append(args[2]);entered.set()
        assert release.wait(5)
        return {'dispatched':True}
    monkeypatch.setattr(mod,'perform',perform)
    row={'user_id':31,'company_id':7,'agent_name':'agent-a'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(mod.run_job,app,row,ident)
        assert entered.wait(5)
        try:
            second=pool.submit(mod.run_job,app,row,ident)
            second.result(timeout=5)
        finally:release.set()
        first.result(timeout=5)
    assert calls==[ident]


def test_read_only_reconciliation_does_not_expose_cached_result_after_scope_revocation(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='success',result={'runId':123})
    monkeypatch.setattr(mod,'_principal',lambda row:{
        'owner':'fixture','repositories':[],'write':True,'delete':False})
    monkeypatch.setattr(mod,'_request',lambda *a,**kw:pytest.fail('No remote call allowed'))
    with pytest.raises(PermissionError):_job_status(mod,app,ident)


@pytest.mark.parametrize('agent,branch,path',[
    ('agent-a','fix/example','src/app.py'),
    ('bolt-executor','main','src/app.py'),
    ('hawk-debugger','develop','src/app.py'),
    ('bolt-executor','fix/example','config/live-self-healing.json'),
    ('bolt-executor','fix/example','.github/workflows/ci.yml'),
    ('hawk-debugger','fix/example','dashboard/backend/live_self_healing.py'),
])
def test_autonomy_preserves_agent_branch_and_file_gates(pipeline,monkeypatch,agent,branch,path):
    mod,(_,app,_,_,_)=pipeline
    monkeypatch.setattr(mod,'_request',lambda *a,**kw:({'default_branch':'main'},False))
    args={'repository':'fixture/repo','branch':branch,'headSha':BASE,
          'message':'Fix','files':[{'path':path,'content':'changed'}]}
    with app.app_context(),pytest.raises(PermissionError):
        mod.prepare({'agent_name':agent},{},'commit',args)


def test_rollout_title_is_not_proof_of_approved_image_inputs(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    proposal={'operation':'rollout','args':{
        'repository':'fixture/repo','branch':'fix/example','headSha':BASE}}
    ident=_stored_job(mod,app,proposal,state='dispatched',
        checkpoint={'stage':'dispatch_intent','workflow':'live-rollout.yml'})
    monkeypatch.setattr(mod,'_request',lambda *a,**kw:pytest.fail('Do not infer rollout from list title'))
    result=_job_status(mod,app,ident)
    assert result['status']=='dispatched'
    assert result['recovery']['evidence']=='inconclusive_no_replay'


@pytest.mark.parametrize('returned_id',[123,456])
def test_rollout_requires_exact_run_id_from_dispatch_receipt(pipeline,monkeypatch,returned_id):
    mod,(_,app,_,_,_)=pipeline
    proposal={'operation':'rollout','args':{
        'repository':'fixture/repo','branch':'fix/example','headSha':BASE}}
    ident=_stored_job(mod,app,proposal,state='uncertain',
        checkpoint={'stage':'dispatch_intent','workflow':'live-rollout.yml','runId':123})
    calls=[]
    def request(method,path,**kwargs):
        assert method=='GET';calls.append(path)
        return _workflow_run(ident,id=returned_id,path='.github/workflows/live-rollout.yml'),False
    monkeypatch.setattr(mod,'_request',request)
    result=_job_status(mod,app,ident)
    assert result['status']==('success' if returned_id==123 else 'uncertain')
    assert calls==['repos/fixture/repo/actions/runs/123']


def test_legacy_schema_migration_is_additive_and_idempotent():
    import sqlite3
    from live_self_healing import ensure
    with sqlite3.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE live_pipeline_jobs(
            id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,operation TEXT NOT NULL,request_id TEXT NOT NULL,
            parameters TEXT NOT NULL,status TEXT NOT NULL,result TEXT,created_at REAL NOT NULL,
            UNIQUE(user_id,company_id,request_id))''')
        row=('a'*32,31,7,'agent-a','ci','original','{}','uncertain',None,100)
        conn.execute('INSERT INTO live_pipeline_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',row)
        ensure(conn);ensure(conn)
        migrated=conn.execute('SELECT * FROM live_pipeline_jobs').fetchone()
        assert migrated[:10]==row and migrated[10:]==(None,None)


def test_legacy_dispatched_ci_can_be_observed_without_new_checkpoint(pipeline,monkeypatch):
    mod,(_,app,_,_,_)=pipeline
    with app.app_context():proposal=_ci_proposal(mod)
    ident=_stored_job(mod,app,proposal,state='dispatched')
    def request(method,path,**kwargs):
        assert method=='GET'
        return {'workflow_runs':[_workflow_run(ident)]},False
    monkeypatch.setattr(mod,'_request',request)
    result=_job_status(mod,app,ident)
    assert result['status']=='success' and result['result']['reconciled'] is True
