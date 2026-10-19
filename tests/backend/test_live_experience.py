"""Real isolated Flask/SQLite endpoints; provider generation and media worker mocked."""
import importlib
import io
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from tests.backend.test_managed_live_context import setup,create,link,ORIGIN

@pytest.fixture
def experience(setup,tmp_path,monkeypatch):
    app,c,login,base,runtime,calls=setup
    app.config.update(NEXUS_LIVE_CONTINUITY_ENABLED=True,NEXUS_LIVE_CONTINUITY_DB=str(tmp_path/'continuity.db'))
    from routes import live_experience as api
    monkeypatch.setattr(api,'live',base)
    import live_approval_policy
    monkeypatch.setattr(live_approval_policy,'live',base)
    monkeypatch.setattr(live_approval_policy,'policy',lambda:{'yoloMode':True,'source':'fixture'})
    monkeypatch.setattr(api,'load_operational_squad',lambda:{'agent-a':{'active':True},'agent-b':{'active':True}})
    monkeypatch.setattr(base,'WORKSPACE',tmp_path)
    (base.AGENTS_DIR/'agent-b.md').write_text('Second persona')
    from routes import workspace
    monkeypatch.setattr(workspace,'REPO_ROOT',tmp_path)
    monkeypatch.setattr(workspace,'WORKSPACE_DIR',tmp_path/'workspace')
    monkeypatch.setattr(workspace,'ADMIN_ROOTS',[tmp_path/name for name in ('.claude','config','docs')])
    monkeypatch.setattr(workspace,'_audit',lambda *a,**kw:None)
    app.register_blueprint(workspace.bp)
    app.register_blueprint(api.bp);login();ctx=create(c).json;link(c,ctx['contextId'])
    return app,c,login,base,ctx,api


def call(c,ctx,action,parameters=None,request_id='request-1'):
    return c.post(f"/api/live/omni-context/{ctx['contextId']}/experience",json={'conversationId':'conv-fixture','action':action,'parameters':parameters or {},'requestId':request_id},headers=ORIGIN)


def test_artifact_persists_idempotently_with_owned_download_and_live_links(experience):
    app,c,login,base,ctx,api=experience
    params={'title':'Plano.md','format':'md','content':'# Plano\nPróximos passos.'}
    result=call(c,ctx,'create_artifact',params);assert result.status_code==200
    assert call(c,ctx,'create_artifact',params).json==result.json
    assert call(c,ctx,'create_artifact',{**params,'content':'Different'}).status_code==400
    assert c.get(result.json['reference']).data==params['content'].encode()
    listed=call(c,ctx,'assets').json;assert len(listed['artifacts'])==1
    visible=base._visible_event
    with app.test_request_context():pass
    # Actual continuity projection supplies only a current authorized download.
    history=c.post(f"/api/live/omni-context/{ctx['contextId']}/read",json={'conversationId':'conv-fixture'},headers=ORIGIN)
    assert history.status_code==200
    assert result.json['reference'] in history.text
    login(32);assert c.get(result.json['reference']).status_code==403


def test_artifact_storage_cannot_be_read_through_general_workspace(experience):
    _,c,login,base,ctx,api=experience
    result=call(c,ctx,'create_artifact',{'title':'Private','format':'txt','content':'Owner only'}).json
    filename=result['artifactId']+'.txt'
    assert api.artifact_root()==Path(base.WORKSPACE)/'dashboard/data/live-artifacts'
    assert c.get(result['reference']).data==b'Owner only'
    for user in (31,32):
        login(user)
        for endpoint in ('download','file','tree'):
            response=c.get('/api/workspace/'+endpoint,query_string={'path':'dashboard/data/live-artifacts/'+filename})
            assert response.status_code==403
        assert c.get('/api/workspace/download',query_string={'path':'workspace/live-artifacts/'+filename}).status_code==404


@pytest.mark.parametrize('fmt,content',[('svg','<svg><script>alert(1)</script></svg>'),('svg','<!DOCTYPE svg><svg/>'),('svg','<svg><animate/></svg>'),('svg','<svg'),('json','{bad'),('md','api_key=sk-sensitive'),('html','<script/>')])
def test_unsafe_artifacts_rejected_without_file(experience,fmt,content):
    _,c,_,_,ctx,api=experience
    assert call(c,ctx,'create_artifact',{'title':'Unsafe','format':fmt,'content':content}).status_code==400
    assert not api.artifact_root().exists()


def test_handoff_rechecks_acl_activity_and_manifest(experience,monkeypatch):
    _,c,_,base,ctx,api=experience
    args={'agentName':'agent-b','reason':'Especialista da tarefa'}
    assert call(c,ctx,'handoff',args).json['authorized']
    monkeypatch.setattr(base,'has_agent_access',lambda _,name:name!='agent-b')
    assert call(c,ctx,'handoff',args).status_code==403
    monkeypatch.setattr(api,'load_operational_squad',lambda:(_ for _ in ()).throw(ValueError()))
    assert call(c,ctx,'handoff',args).status_code==503


def test_attachment_checks_binding_manifest_and_current_runtime(experience,monkeypatch):
    app,c,_,base,ctx,api=experience
    url=f"/api/live/omni-context/{ctx['contextId']}/attachments"
    def upload(conversation='conv-fixture'):
        return c.post(url,data={'conversationId':conversation,'file':(io.BytesIO(b'Useful brief'),'brief.txt')},headers=ORIGIN)
    assert upload('wrong').status_code==403
    assert upload().status_code==201
    app.config['NEXUS_LIVE_CONTINUITY_ENABLED']=False
    assert upload().status_code==503


def test_capabilities_filter_sensitive_and_symlink_skills(experience,tmp_path):
    _,c,_,_,ctx,api=experience
    skills=tmp_path/'.claude/skills';safe=skills/'useful';safe.mkdir(parents=True);(safe/'SKILL.md').write_text('---\ndescription: Useful skill\n---\nReference text')
    secret=skills/'private';secret.mkdir();(secret/'SKILL.md').write_text('api_key=sk-private-value')
    (skills/'external').symlink_to(safe,target_is_directory=True)
    data=call(c,ctx,'capabilities',{'query':'useful'}).json
    assert [x['name'] for x in data['skills']['items']]==['useful']
    assert call(c,ctx,'skill',{'name':'useful'}).json['execution']=='not_executed'
    assert call(c,ctx,'skill',{'name':'private'}).status_code==400
    assert call(c,ctx,'skill',{'name':'../private'}).status_code==403


def test_image_reservation_does_not_repeat_paid_calls(experience,monkeypatch):
    _,c,_,_,ctx,api=experience
    import live_image_jobs
    monkeypatch.setenv('OPENAI_API_KEY','fixture-key-never-sent')
    starts=[]
    class Thread:
        def __init__(self,**kwargs):starts.append(kwargs)
        def start(self):pass
    monkeypatch.setattr(live_image_jobs.threading,'Thread',Thread)
    params={'title':'Capa','prompt':'Capa editorial azul com tipografia legível','format':'square'}
    a=call(c,ctx,'create_image',params);assert a.status_code==200;assert a.json['status']=='processing'
    assert call(c,ctx,'create_image',params).json==a.json;assert len(starts)==1
    assert call(c,ctx,'create_image',params,'different-request').status_code==400
    assert c.get(a.json['reference']).status_code==404
    events=c.post(f"/api/live/omni-context/{ctx['contextId']}/read",json={'conversationId':'conv-fixture'},headers=ORIGIN).json['continuity']['current']
    image=next(e for e in events if e['source']==a.json['reference']);assert image['kind']=='progress';assert image['links']==[]


def test_video_uses_existing_draft_queue_once_with_company_scope(experience,monkeypatch):
    app,c,_,_,ctx,api=experience
    from routes import media_jobs
    from models import db,MediaJob
    calls=[]
    def queue(data_override,job_id_override):
        calls.append(data_override)
        db.session.add(MediaJob(id=job_id_override,title=data_override['title'],brief=data_override['brief'],company_id=7,status='queued',job_type='social_clip',platform='instagram',format='vertical',width=1080,height=1920,fps=30,duration_seconds=15,publication_mode='draft',created_at='2026-10-19',updated_at='2026-10-19'))
        db.session.commit();return {},201
    monkeypatch.setattr(media_jobs,'create_media_job',queue)
    params={'title':'Vídeo','brief':'Explicação curta sobre o produto','durationSeconds':15,'format':'vertical'}
    a=call(c,ctx,'create_media',params);assert a.status_code==200
    assert call(c,ctx,'create_media',params).status_code==200;assert len(calls)==1
    assert calls[0]['publication_mode']=='draft';assert calls[0]['company_id']==7


def test_image_worker_stores_verified_png_and_never_follows_redirects(experience,monkeypatch):
    app,c,_,_,ctx,api=experience
    import live_image_jobs,base64
    import struct,zlib
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\xff'))+chunk(b'IEND',b'')
    output=io.BytesIO(raw)
    response=Mock(json=lambda:{'data':[{'b64_json':base64.b64encode(output.getvalue()).decode()}]},raise_for_status=lambda:None)
    requests=[]
    def generate(url,**kw):requests.append((url,kw));return response
    monkeypatch.setattr(live_image_jobs.requests,'post',generate)
    identifier='1'*32
    live_image_jobs.generate(app,identifier,{'format':'square','prompt':'A blue square'},'fixture-key')
    assert (api.artifact_root()/(identifier+'.png')).read_bytes()==output.getvalue()
    assert requests[0][0]=='https://api.openai.com/v1/images/generations'
    assert requests[0][1]['allow_redirects'] is False


def test_intelligence_uses_original_human_cookie_fixed_routes_and_redacts_secrets(experience,monkeypatch):
    app,c,_,_,ctx,api=experience
    import live_workspace_actions as actions
    sent=[]
    def native(method,url,**kwargs):
        sent.append((method,url,kwargs));return Mock(status_code=200,json=lambda:{'servers':[{'name':'Valid','env':{'API_KEY':'private'},'token':'secret'}]})
    monkeypatch.setattr(actions.requests,'request',native)
    response=call(c,ctx,'inspect_area',{'area':'mcp'})
    assert response.status_code==200;assert 'private' not in response.text;assert 'secret' not in response.text
    assert sent[0][1]=='http://127.0.0.1:8080/api/mcp-servers'
    assert sent[0][2]['headers']['Cookie'].startswith('session=')
    assert 'Authorization' not in sent[0][2]['headers'];assert sent[0][2]['allow_redirects'] is False
    assert call(c,ctx,'inspect_area',{'area':'https://evil.invalid'}).status_code==400
    assert len(sent)==1


def test_intelligence_update_allowlist_idempotency_and_scope(experience,monkeypatch):
    _,c,_,_,ctx,api=experience
    import live_workspace_actions as actions
    updates=[]
    monkeypatch.setattr(actions,'native',lambda method,path,body=None,params=None:updates.append((method,path,body)) or {'saved':True})
    parameters={'area':'heartbeats','identifier':'existing-heartbeat','changesJson':'{"enabled":false}'}
    assert call(c,ctx,'update_area',parameters).json['status']=='success'
    assert call(c,ctx,'update_area',parameters).json['replayed'];assert len(updates)==1
    assert call(c,ctx,'update_area',{**parameters,'area':'providers'},'provider-denied').status_code==400
    assert call(c,ctx,'update_area',{**parameters,'changesJson':'{"handler":"shell"}'},'handler-denied').status_code==400
    assert call(c,ctx,'update_area',{'area':'tickets','identifier':'missing','changesJson':'{"title":"Changed"}'},'other-company').status_code==403
    assert len(updates)==1


def test_document_edit_checks_digest_backup_path_and_permissions(experience,tmp_path,monkeypatch):
    _,c,_,_,ctx,api=experience
    from routes import workspace
    import hashlib
    root=tmp_path/'workspace';root.mkdir();path=root/'brief.md';path.write_text('Original')
    monkeypatch.setattr(workspace,'REPO_ROOT',tmp_path);monkeypatch.setattr(workspace,'WORKSPACE_DIR',root)
    monkeypatch.setattr(workspace,'_audit',lambda *a,**kw:None)
    read=call(c,ctx,'read_document',{'area':'materials','name':'brief.md'});assert read.status_code==200
    sha=hashlib.sha256(b'Original').hexdigest();assert read.json['sha256']==sha
    change={'area':'materials','name':'brief.md','content':'Updated','expectedSha256':sha}
    response=call(c,ctx,'write_document',change);assert response.status_code==200;assert path.read_text()=='Updated'
    assert next((tmp_path/'backups/live-document-edits').rglob('brief.md')).read_text()=='Original'
    assert call(c,ctx,'write_document',change).status_code==400
    assert call(c,ctx,'read_document',{'area':'materials','name':'../config/.env'}).status_code==400
    assert call(c,ctx,'write_document',{**change,'content':'password=private','expectedSha256':hashlib.sha256(b'Updated').hexdigest()}).status_code==400


def test_harness_yolo_bypasses_application_approval_but_off_requires_human_endpoint(experience,monkeypatch):
    _,c,_,_,ctx,api=experience
    import live_approval_policy,live_workspace_actions
    writes=[]
    monkeypatch.setattr(live_workspace_actions,'native',lambda *args,**kwargs:writes.append(args) or {'saved':True})
    monkeypatch.setattr(live_approval_policy,'policy',lambda:{'yoloMode':False,'source':'fixture'})
    params={'area':'heartbeats','identifier':'heartbeat-a','changesJson':'{"enabled":false}'}
    waiting=call(c,ctx,'update_area',params);assert waiting.status_code==200;assert waiting.json['approvalRequired'];assert not writes
    endpoint=f"/api/live/omni-context/{ctx['contextId']}/approvals"
    pending=c.post(endpoint,json={'conversationId':'conv-fixture'},headers=ORIGIN);assert len(pending.json['pending'])==1
    body={'conversationId':'conv-fixture','approvalId':waiting.json['approvalId'],'decision':'approve'}
    assert c.post(endpoint,json=body,headers=ORIGIN).status_code==200;assert len(writes)==1
    assert c.post(endpoint,json=body,headers=ORIGIN).status_code==409;assert len(writes)==1
    monkeypatch.setattr(live_approval_policy,'policy',lambda:{'yoloMode':True,'source':'fixture'})
    direct=call(c,ctx,'update_area',params,'yolo-direct');assert direct.status_code==200;assert direct.json['status']=='success';assert len(writes)==2


def test_admin_approval_encrypts_credentials_and_revalidates_acl(experience,monkeypatch):
    app,c,_,base,ctx,api=experience
    import live_approval_policy,live_workspace_actions
    monkeypatch.setattr(live_approval_policy,'policy',lambda:{'yoloMode':False,'source':'fixture'})
    params={'operation':'configure_provider','argumentsJson':json.dumps({'providerId':'fixture','envVars':{'OPENAI_API_KEY':'fixture-secret-value'}})}
    pending=call(c,ctx,'admin_action',params);assert pending.json['approvalRequired']
    with app.app_context(),base._store() as conn:
        saved=conn.execute('SELECT parameters FROM live_action_approvals').fetchone()[0]
        assert saved.startswith('enc:');assert 'fixture-secret-value' not in saved
    endpoint=f"/api/live/omni-context/{ctx['contextId']}/approvals"
    listing=c.post(endpoint,json={'conversationId':'conv-fixture'},headers=ORIGIN);assert 'fixture-secret-value' not in listing.text
    monkeypatch.setattr(live_workspace_actions,'has_permission',lambda *_:False)
    response=c.post(endpoint,json={'conversationId':'conv-fixture','approvalId':pending.json['approvalId'],'decision':'approve'},headers=ORIGIN)
    assert response.status_code==403
