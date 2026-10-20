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
    from live_adapter_errors import AdapterError
    policy=tmp_path/'pipeline.json';policy.write_text(json.dumps({'version':1,'ciWorkflows':['ci.yml'],'rollout':{'enabled':False}}))
    monkeypatch.setattr(mod,'POLICY',policy)
    monkeypatch.setattr(mod,'_principal',lambda row:{'owner':'fixture','repositories':'*','write':True,'delete':False})
    monkeypatch.setattr(mod,'_workflow',lambda *args:'verified-workflow-hash')
    monkeypatch.setattr(mod,'_head',lambda *args:BASE)
    return mod,adapters


def test_multi_file_commit_updates_ref_once_without_force(pipeline,monkeypatch):
    mod,_=pipeline;calls=[];head=BASE
    def request(method,path,**kwargs):
        nonlocal head
        calls.append((method,path,kwargs.get('body')))
        if method=='GET':return {'tree':{'sha':TREE}},False
        if path.endswith('/git/trees'):return {'sha':TREE},False
        if path.endswith('/git/commits'):return {'sha':COMMIT},False
        if method=='PATCH':head=COMMIT;return {},False
        raise AssertionError((method,path))
    monkeypatch.setattr(mod,'_request',request);monkeypatch.setattr(mod,'_head',lambda *args:head)
    result=mod.perform({}, {'operation':'commit','target':{'branchExists':True},'args':{
        'repository':'fixture/repo','branch':'fix/example','headSha':BASE,'message':'Fix',
        'files':[{'path':'src/app.py','content':'changed'},{'path':'tests/test_app.py','content':'checks'}]}},'job')
    assert result['sha']==COMMIT
    refs=[c for c in calls if c[0]=='PATCH'];assert len(refs)==1 and refs[0][2]=={'sha':COMMIT,'force':False}
    tree=next(c[2] for c in calls if c[1].endswith('/git/trees'))
    assert tree['base_tree']==TREE and len(tree['tree'])==2
    assert all(f['content'] and 'sha' not in f for f in tree['tree'])
    assert not any(c[0]=='DELETE' for c in calls)


def test_revocation_mid_commit_prevents_ref_update(pipeline,monkeypatch):
    mod,_=pipeline;writes=[]
    def principal(row):
        if writes:raise PermissionError()
        return {}
    monkeypatch.setattr(mod,'_principal',principal)
    def request(method,path,**kwargs):
        if method=='POST':writes.append(path);return {'sha':TREE},False
        return {'tree':{'sha':TREE}},False
    monkeypatch.setattr(mod,'_request',request)
    with pytest.raises(PermissionError):mod.perform({}, {'operation':'commit','target':{'branchExists':True},'args':{
        'repository':'fixture/repo','branch':'fix/example','headSha':BASE,'message':'Fix',
        'files':[{'path':'src/app.py','content':'changed'}]}},'job')
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
        if path.endswith('/environments/production'):return {'protection_rules':[{'type':'required_reviewers','reviewers':[{'type':'User','id':1}],'prevent_self_review':True}]},False
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
