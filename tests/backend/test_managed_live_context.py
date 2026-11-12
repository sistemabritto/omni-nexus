"""Real Flask/SQLAlchemy routes with fake local terminal HTTP; no provider/key/audio."""
import sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import Mock
import pytest
from flask import Flask, g, request
from flask_login import LoginManager
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'dashboard/backend'))
ORIGIN={'Origin':'https://example.test'}

@pytest.fixture
def setup(tmp_path,monkeypatch):
    from models import db,User,Company
    # Other integration suites rebuild the models registry. Bind BOTH route
    # modules to this fixture's canonical models instead of reusing a cached
    # Ticket mapper from an earlier test app. Restore module mappings on teardown.
    import importlib.util
    importlib.import_module('routes')  # Fixture also works when this suite runs first.
    modules = {}
    for name in ('routes.tickets', 'routes.managed_live_context'):
        path = Path(__file__).resolve().parents[2] / 'dashboard/backend' / (name.replace('.', '/') + '.py')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        parent, child = name.rsplit('.', 1)
        monkeypatch.setattr(sys.modules[parent], child, module, raising=False)
        spec.loader.exec_module(module)
        modules[name] = module
    mod = modules['routes.managed_live_context']
    app=Flask(__name__)
    app.config.update(TESTING=True,SECRET_KEY='test-only',SERVER_NAME='example.test',SQLALCHEMY_DATABASE_URI='sqlite://',SQLALCHEMY_TRACK_MODIFICATIONS=False,NEXUS_LIVE_USER_ID=31,NEXUS_LIVE_CONTEXT_DB=str(tmp_path/'contexts.db'))
    db.init_app(app);login=LoginManager(app)
    @login.user_loader
    def load(uid):return db.session.get(User,int(uid))
    @app.before_request
    def api_token():g.auth_via_api_token=request.headers.get('X-Fixture-Token')=='yes'
    agents=tmp_path/'agents';agents.mkdir();(agents/'agent-a.md').write_text('fixture');monkeypatch.setattr(mod,'AGENTS_DIR',agents)
    runtime={};calls=[]
    def post(url,**kwargs):
        calls.append(('POST',url,kwargs));sid=str(uuid4());agent=kwargs['json']['agentName'];runtime[sid]={'id':sid,'name':'Runtime created in test','active':False,'workingDir':'not-returned'}
        return Mock(json=lambda:{'success':True,'sessionId':sid,'session':{'id':sid,'agentName':agent}},raise_for_status=lambda:None)
    def get(url,**kwargs):
        calls.append(('GET',url,kwargs));return Mock(json=lambda:runtime[url.rsplit('/',1)[-1]],raise_for_status=lambda:None)
    monkeypatch.setattr(mod.requests,'post',post);monkeypatch.setattr(mod.requests,'get',get)
    with app.app_context():
        db.create_all();db.session.add_all([User(id=31,username='personal-fixture',password_hash='test-only',role='admin'),User(id=32,username='other-fixture',password_hash='test-only',role='admin'),Company(id=7,name='Company A fixture',slug='a',status='active',created_at='test',updated_at='test'),Company(id=8,name='Company B fixture',slug='b',status='active',created_at='test',updated_at='test')]);db.session.commit()
    app.register_blueprint(mod.bp);client=app.test_client()
    def signin(uid=31):
        with client.session_transaction() as s:s['_user_id']=str(uid);s['_fresh']=True
    yield app,client,signin,mod,runtime,calls
    with app.app_context():db.session.remove();db.drop_all()

def create(client,company=7):
    return client.post('/api/live/omni-context',json={'companyId':company,'agentName':'agent-a'},headers=ORIGIN)

def link(client,cid,conversation='conv-fixture'):
    return client.post(f'/api/live/omni-context/{cid}/conversation',json={'conversationId':conversation},headers=ORIGIN)

def read(client,cid,conversation='conv-fixture',**extra):
    return client.post(f'/api/live/omni-context/{cid}/read',json={'conversationId':conversation,**extra},headers=ORIGIN)

def test_full_authenticated_create_link_read_uses_canonical_db_and_runtime(setup):
    app,c,login,mod,runtime,calls=setup;login()
    opts=c.get('/api/live/omni-context/options');assert opts.json=={'companies':[{'id':7,'name':'Company A fixture'},{'id':8,'name':'Company B fixture'}],'agents':['agent-a'],'consumptionApproved':False,'presentationGroups':{}}
    response=create(c);assert response.status_code==201;ctx=response.json;assert ctx['runtimeSessionId'] in runtime
    assert read(c,ctx['contextId']).status_code==403
    assert link(c,ctx['contextId']).status_code==200
    r=read(c,ctx['contextId']);assert r.status_code==200;assert r.headers['Cache-Control']=='no-store';assert r.json['company']=={'id':7,'name':'Company A fixture'};assert r.json['runtimeSessionId']==ctx['runtimeSessionId'];assert 'workingDir' not in r.text
    assert calls[0][2]['json']=={'agentName':'agent-a'};assert all('/api/sessions/' in x[1] for x in calls)

def test_personal_cookie_origin_and_configuration_guards_precede_runtime_calls(setup):
    app,c,login,mod,runtime,calls=setup
    assert create(c).status_code==401;login(32);assert create(c).status_code==403;login()
    assert c.post('/api/live/omni-context',json={'companyId':7,'agentName':'agent-a'}).status_code==403
    assert c.get('/api/live/omni-context/options',headers={'X-Fixture-Token':'yes'}).status_code==403
    app.config['NEXUS_LIVE_USER_ID']=None
    assert c.get('/api/live/omni-context/options').status_code==503;assert calls==[]

def test_no_legacy_session_adoption_no_agent_scope_override(setup):
    _,c,login,mod,runtime,calls=setup;login()
    assert c.post('/api/live/omni-context',json={'companyId':7,'agentName':'agent-a','sessionId':'someone-else'},headers=ORIGIN).status_code==400
    assert c.post('/api/live/omni-context',json={'companyId':7,'agentName':'../secret'},headers=ORIGIN).status_code==403
    assert create(c,999).status_code==403;assert calls==[]

def test_company_and_conversation_bindings_are_immutable_and_no_model_parameters_select_scope(setup):
    _,c,login,mod,runtime,calls=setup;login();a=create(c,7).json;b=create(c,8).json
    assert link(c,a['contextId'],'conv-a').status_code==200;assert link(c,b['contextId'],'conv-b').status_code==200
    assert link(c,a['contextId'],'conv-b').status_code==409
    assert read(c,a['contextId'],'conv-b').status_code==403
    assert read(c,a['contextId'],'conv-a',companyId=8).status_code==400
    assert read(c,a['contextId'],'conv-a').json['company']['id']==7
    assert read(c,b['contextId'],'conv-b').json['company']['id']==8
    login(32);assert read(c,a['contextId'],'conv-a').status_code==403

def test_revoked_agent_or_company_and_changed_runtime_fail_closed(setup,monkeypatch):
    app,c,login,mod,runtime,calls=setup;login();ctx=create(c).json;link(c,ctx['contextId'])
    monkeypatch.setattr(mod,'has_agent_access',lambda *_:False);assert read(c,ctx['contextId']).status_code==403
    monkeypatch.setattr(mod,'has_agent_access',lambda *_:True);runtime[ctx['runtimeSessionId']]['id']='wrong';assert read(c,ctx['contextId']).status_code==503
    from models import db,Company
    with app.app_context():db.session.get(Company,7).status='inactive';db.session.commit()
    assert read(c,ctx['contextId']).status_code==403

def test_routes_against_actual_terminal_http_handlers_and_persistence(setup,tmp_path,monkeypatch):
    """A real loopback HTTP request reaches the repo's actual terminal route code."""
    import os,subprocess,json,requests
    app,c,login,mod,_,_=setup
    script=Path(__file__).resolve().parents[2]/'qa/managed-live-context/runtime-http-fixture.cjs'
    env={**os.environ,'NODE_PATH':os.environ.get('NODE_PATH') or str(Path(__file__).resolve().parents[2]/'dashboard/terminal-server/node_modules')}
    process=subprocess.Popen(['node',str(script)],cwd=tmp_path,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        line=process.stdout.readline()
        assert line,process.stderr.read()
        port=json.loads(line)['port'];monkeypatch.setattr(mod,'TERMINAL_HTTP_BASE',f'http://127.0.0.1:{port}')
        # requests.request is not patched by the isolated fixture. Use real socket I/O.
        monkeypatch.setattr(mod.requests,'post',lambda url,**kw:requests.request('POST',url,**kw))
        monkeypatch.setattr(mod.requests,'get',lambda url,**kw:requests.request('GET',url,**kw))
        login();ctx=create(c).json;assert ctx.get('runtimeSessionId')
        assert link(c,ctx['contextId']).status_code==200
        result=read(c,ctx['contextId']);assert result.status_code==200;assert result.json['runtimeSessionId']==ctx['runtimeSessionId'];assert result.json['sessionName'].startswith('agent-a #')
    finally:
        process.terminate();process.wait(timeout=10)
    stored=json.loads((tmp_path/'runtime-sessions/sessions.json').read_text())
    assert ctx['runtimeSessionId'] in json.dumps(stored)


def test_signed_session_is_cost_gated_and_never_exposes_key(setup,monkeypatch):
    app,c,login,mod,_,calls=setup;login();ctx=create(c).json
    url=f"/api/live/omni-context/{ctx['contextId']}/signed-session"
    assert c.post(url,json={},headers=ORIGIN).status_code==403
    app.config['NEXUS_LIVE_COST_APPROVED']=True
    monkeypatch.delenv('ELEVENLABS_API_KEY',raising=False)
    assert c.post(url,json={},headers=ORIGIN).status_code==503
    app.config['NEXUS_LIVE_AGENT_ID']='agent_fixture'
    monkeypatch.setenv('ELEVENLABS_API_KEY','fixture-only')
    fake=Mock();fake.json.return_value={'signed_url':'wss://api.elevenlabs.io/v1/convai/conversation?fixture=yes'}
    get=Mock(return_value=fake);monkeypatch.setattr(mod.requests,'get',get)
    r=c.post(url,json={},headers=ORIGIN);assert r.status_code==200;assert 'fixture-only' not in r.text
    assert get.call_args.kwargs['params']['agent_id']=='agent_fixture'
    login(32);assert c.post(url,json={},headers=ORIGIN).status_code==403;assert get.call_count==1


def test_agent_identity_requires_server_configuration_not_request_override(setup,monkeypatch):
    app,c,login,mod,_,_=setup;login();ctx=create(c).json
    app.config['NEXUS_LIVE_COST_APPROVED']=True
    monkeypatch.delenv('NEXUS_LIVE_AGENT_ID',raising=False)
    provider=Mock();monkeypatch.setattr(mod.requests,'get',provider)
    url=f"/api/live/omni-context/{ctx['contextId']}/signed-session"
    assert c.post(url,json={},headers=ORIGIN).json['error']=='provider_agent_not_configured'
    assert c.post(url,json={'agentId':'agent_fixture'},headers=ORIGIN).status_code==400
    assert provider.call_count==0

def test_presentation_groups_are_private_configuration_filtered_by_authorized_catalog(setup,tmp_path):
    import json
    app,c,login,mod,_,_=setup;login()
    mapping=tmp_path/'groups.json';mapping.write_text(json.dumps({'Fixture sector':['agent-a','not-authorized','agent-a'],'Empty':['missing'],'Duplicate':['agent-a']}))
    app.config['NEXUS_LIVE_AGENT_GROUPS_FILE']=str(mapping)
    assert c.get('/api/live/omni-context/options').json['presentationGroups']=={'Fixture sector':['agent-a']}
    mapping.write_text('invalid json')
    assert c.get('/api/live/omni-context/options').json['presentationGroups']=={}


def test_read_includes_only_bound_company_tasks_through_existing_acl(setup,monkeypatch):
    app,c,login,mod,_,_=setup;login();ctx=create(c,7).json;link(c,ctx['contextId'])
    from models import db,Ticket
    with app.app_context():
        db.session.add_all([Ticket(id='fixture-a',title='Fixture pending',company_id=7,status='blocked',blocked_reason='pending_human_approval',created_by='fixture',created_at='test',updated_at='test'),Ticket(id='fixture-b',title='Fixture done',company_id=7,status='resolved',created_by='fixture',created_at='test',updated_at='test'),Ticket(id='fixture-c',title='Other company private fixture',company_id=8,status='open',created_by='fixture',created_at='test',updated_at='test')]);db.session.commit()
    response=read(c,ctx['contextId']);assert response.status_code==200
    tasks=response.json['tasks'];assert tasks['source']=='/api/tickets';assert tasks['total']==2;assert tasks['pendingTotal']==1;assert tasks['byStatus']['blocked']==1;assert tasks['byStatus']['resolved']==1;assert tasks['pending'][0]['title']=='Fixture pending'
    assert 'Other company private fixture' not in response.text;assert 'workspace_path' not in response.text;assert 'lock_token' not in response.text
    assert read(c,ctx['contextId'],companyId=8).status_code==400
    import routes.tickets as tickets
    monkeypatch.setattr(tickets,'has_permission',lambda *_:False)
    assert read(c,ctx['contextId']).status_code==403
