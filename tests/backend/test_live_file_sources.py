"""Explicit file ownership fixtures only; never production files or provider calls."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from tests.backend.test_live_continuity_endpoints import enabled, bound, post
from tests.backend.test_managed_live_context import setup, read, ORIGIN


@pytest.fixture
def files(enabled, tmp_path, monkeypatch):
    from routes import workspace
    root = tmp_path/'repo'
    (root/'workspace'/'editorial').mkdir(parents=True)
    monkeypatch.setattr(workspace, 'REPO_ROOT', root)
    monkeypatch.setattr(workspace, 'WORKSPACE_DIR', root/'workspace')
    monkeypatch.setattr(workspace, 'ADMIN_ROOTS', [root/'.claude', root/'config', root/'docs'])
    monkeypatch.setattr(workspace, '_audit', lambda *_args, **_kwargs: None)
    def save(name='roteiro.md', text='Zephyr roteiro aprovado para revisão'):
        path=root/'workspace'/'editorial'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return 'workspace/editorial/'+name, path
    yield enabled, root, save


def bind_file(c, ctx, path, connection='provider-a'):
    preview=post(c,ctx,'file-sources/preview',connection,path=path)
    assert preview.status_code==200,preview.json
    assert 'text' not in preview.json
    data=preview.json
    response=post(c,ctx,'file-sources/bind',connection,path=path,sha256=data['sha256'],
                  expectedRevision=data['expectedRevision'],confirmOwnership=True)
    assert response.status_code==200,response.json
    return response.json


def test_unbound_project_folder_is_not_adopted_then_explicit_file_reaches_query_and_read(files):
    enabled,root,save=files;app,c,_,_,_,_=enabled
    path,file=save(text='prefix '*120+'Zephyr roteiro aprovado https://do-not-fetch.invalid')
    from models import db,GoalProject
    with app.app_context():
        db.session.add(GoalProject(id=19,slug='fixture',title='Fixture',company_id=7,
            workspace_folder_path='workspace/editorial',created_at='fixture',updated_at='fixture'))
        db.session.commit()
    ctx=bound(c)
    assert post(c,ctx,'query',query='Zephyr').json['files']['results']==[]
    binding=bind_file(c,ctx,path)
    result=post(c,ctx,'query',query='Zephyr')
    assert result.status_code==200 and result.headers['Cache-Control']=='no-store'
    source=result.json['files'];assert source['bindingCount']==source['availableCount']==1
    hit=source['results'][0]
    assert hit['bindingId']==binding['id'] and hit['revision']==1
    assert hit['sha256']==hashlib.sha256(file.read_bytes()).hexdigest()
    assert hit['path']==path and hit['reference']=='/api/workspace/file?path=workspace%2Feditorial%2Froteiro.md'
    assert 'Zephyr roteiro aprovado' in hit['text'] and len(hit['text'])<=600
    assert source['policy']=='explicit_user_company_digest_and_current_workspace_acl'
    # Same no-argument tool contract; no remote search tool/grant is required.
    post(c,ctx,'transcript',eventId='file-question',role='user',text='Zephyr roteiro')
    output=read(c,ctx['contextId'],'provider-a')
    assert output.status_code==200
    assert output.json['queryResult']['files']['results'][0]['sha256']==hit['sha256']
    assert len(json.dumps(output.json,ensure_ascii=False))<24000
    assert post(c,ctx,'file-sources/list').json['bindings'][0]['id']==binding['id']


def test_digest_change_requires_explicit_cas_rebind_and_revocation_removes_source(files):
    enabled,_,save=files;_,c,_,_,_,_=enabled
    path,file=save();ctx=bound(c);binding=bind_file(c,ctx,path)
    file.write_text('Zephyr roteiro nova versão')
    result=post(c,ctx,'query',query='Zephyr').json['files']
    assert result['results']==[] and result['unavailableCount']==1
    assert post(c,ctx,'file-sources/list').json['bindings'][0]['status']=='changed_rebind_required'
    assert post(c,ctx,'file-sources/bind',path=path,sha256=binding['sha256'],expectedRevision=1,confirmOwnership=True).status_code==409
    new=bind_file(c,ctx,path);assert new['revision']==2
    assert post(c,ctx,'file-sources/revoke',id=new['id'],expectedRevision=1).status_code==409
    assert post(c,ctx,'file-sources/revoke',id=new['id'],expectedRevision=2).status_code==200
    assert post(c,ctx,'query',query='Zephyr').json['files']['results']==[]
    assert post(c,ctx,'file-sources/list').json['bindings']==[]


def test_user_company_session_and_explicit_confirmation_cannot_be_overridden(files):
    enabled,_,save=files;app,c,login,mod,_,_=enabled
    path,_=save();a=bound(c);binding=bind_file(c,a,path)
    b=bound(c,company=8,connection='provider-b')
    assert post(c,b,'query','provider-b',query='Zephyr').json['files']['bindingCount']==0
    data=post(c,b,'file-sources/preview','provider-b',path=path).json
    assert post(c,b,'file-sources/bind','provider-b',path=path,sha256=data['sha256'],expectedRevision=0,confirmOwnership=True).status_code==409
    assert post(c,b,'file-sources/revoke','provider-b',id=binding['id'],expectedRevision=1).status_code==409
    for field in ('companyId','userId','projectId','sessionId','palace'):
        assert post(c,a,'file-sources/preview',path=path,**{field:8}).status_code==400
    assert post(c,a,'file-sources/bind',path=path,sha256=binding['sha256'],expectedRevision=1,confirmOwnership=False).status_code==400
    assert post(c,a,'file-sources/list','foreign-conversation').status_code==403
    assert c.post(f"/api/live/omni-context/{a['contextId']}/file-sources/list",json={'conversationId':'provider-a'}).status_code==403
    # Even an independently authorized Workspace reader cannot see another user's bindings.
    from flask_login import login_user
    from models import db,User
    from live_file_sources import search
    with app.test_request_context('/'):
        login_user(db.session.get(User,32))
        with mod._store() as conn:
            assert search(conn,{'user_id':32,'company_id':7},['Zephyr'])['bindingCount']==0
    login(32)
    assert post(c,a,'file-sources/list').status_code==403


def test_current_workspace_acl_revocation_and_source_failure_do_not_remove_memory(files,monkeypatch):
    enabled,_,save=files;_,c,_,_,_,_=enabled
    path,_=save();ctx=bound(c);bind_file(c,ctx,path)
    post(c,ctx,'notes',requestId='memory',kind='fact',text='Zephyr fato confirmado',confirmed=True)
    from routes import workspace
    monkeypatch.setattr(workspace,'has_workspace_folder_access',lambda *_:False)
    result=post(c,ctx,'query',query='Zephyr')
    assert result.status_code==200 and result.json['files']['results']==[]
    assert any('fato confirmado' in m['text'] for m in result.json['memory'])
    assert post(c,ctx,'file-sources/list').json['bindings']==[{'id':post(c,ctx,'file-sources/list').json['bindings'][0]['id'],'revision':1,'active':True,'status':'unavailable'}]
    import live_file_sources
    original=live_file_sources.has_permission
    monkeypatch.setattr(live_file_sources,'has_permission',lambda role,resource,action:False if resource=='workspace' else original(role,resource,action))
    assert post(c,ctx,'query',query='Zephyr').json['files']['status']=='denied'


@pytest.mark.parametrize('bad',['../outside.md','/tmp/outside.md','workspace/../outside.md',
    'workspace/editorial/../editorial/roteiro.md','workspace/editorial/.env.md',
    'workspace/editorial/api-token.txt','workspace/editorial/secret.md','docs/report.md',
    'workspace/editorial/roteiro.json','workspace/editorial/roteiro.md/','workspace\\editorial\\roteiro.md'])
def test_unsafe_paths_fail_without_exposing_content(files,bad):
    enabled,_,save=files;_,c,_,_,_,_=enabled;save();ctx=bound(c)
    response=post(c,ctx,'file-sources/preview',path=bad)
    assert response.status_code==403 and response.json=={'error':'file_source_denied'}


@pytest.mark.parametrize('text',['-----BEGIN PRIVATE KEY-----\nconfidential',
    'api_key = sk-1234567890abcdefghijklmn', 'password=not-for-the-agent',
    'Authorization: Bearer abcdefghijklmnop123456', 'binary\x00Zephyr'])
def test_secret_like_and_binary_contents_fail_closed(files,text):
    enabled,_,save=files;_,c,_,_,_,_=enabled
    path,_=save(text=text);ctx=bound(c)
    assert post(c,ctx,'file-sources/preview',path=path).status_code==403
    assert post(c,ctx,'query',query='Zephyr').json['files']['results']==[]


def test_symlinks_hardlinks_large_files_and_invalid_utf8_are_rejected(files):
    enabled,root,save=files;_,c,_,_,_,_=enabled;ctx=bound(c)
    path,file=save()
    outside=root/'outside.md';outside.write_text('Zephyr SECRET outside')
    (file.parent/'link.md').symlink_to(outside)
    (file.parent/'inside-link.md').symlink_to(file)
    (file.parent/'linked-dir').symlink_to(file.parent, target_is_directory=True)
    os.link(file,file.parent/'hard.md')
    (file.parent/'large.md').write_bytes(b'x'*(128*1024+1))
    (file.parent/'invalid.md').write_bytes(b'\xff')
    for name in ('link.md','inside-link.md','linked-dir/roteiro.md','hard.md','roteiro.md','large.md','invalid.md'):
        assert post(c,ctx,'file-sources/preview',path='workspace/editorial/'+name).status_code==403


def test_binding_limit_also_applies_to_reactivation(files,monkeypatch):
    enabled,_,save=files;_,c,_,_,_,_=enabled;ctx=bound(c)
    import live_file_sources
    monkeypatch.setattr(live_file_sources,'MAX_BINDINGS',1)
    a,_=save('first.md');first=bind_file(c,ctx,a)
    b,_=save('second.md');data=post(c,ctx,'file-sources/preview',path=b).json
    assert post(c,ctx,'file-sources/bind',path=b,sha256=data['sha256'],expectedRevision=0,confirmOwnership=True).status_code==409
    post(c,ctx,'file-sources/revoke',id=first['id'],expectedRevision=1)
    bind_file(c,ctx,b)
    assert post(c,ctx,'file-sources/bind',path=a,sha256=first['sha256'],expectedRevision=2,confirmOwnership=True).status_code==409


def test_revoked_binding_during_read_is_not_serialized(files,monkeypatch):
    enabled,_,save=files;_,c,_,mod,_,_=enabled;ctx=bound(c)
    path,_=save();binding=bind_file(c,ctx,path)
    import live_file_sources
    original=live_file_sources._read;calls=[]
    def racing_read(path):
        file=original(path);calls.append(path)
        if len(calls)==2:
            with mod._store() as conn:
                live_file_sources.revoke(conn,{'user_id':31,'company_id':7},binding['id'],1)
        return file
    monkeypatch.setattr(live_file_sources,'_read',racing_read)
    assert post(c,ctx,'query',query='Zephyr').json['files']['results']==[]


def test_real_http_and_sdk_dispatcher_deliver_only_explicit_file(files,tmp_path):
    import subprocess,threading
    from werkzeug.middleware.proxy_fix import ProxyFix
    from werkzeug.serving import make_server
    from tests.backend.test_live_query_tools import prepare_history
    enabled,_,save=files;app,c,_,_,_,_=enabled
    ctx=prepare_history(enabled)
    path,file=save();binding=bind_file(c,ctx,path,'current-provider')
    save('unbound.md','Zephyr SECRET unbound file')
    app.wsgi_app=ProxyFix(app.wsgi_app,x_host=1)
    server=make_server('127.0.0.1',0,app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    cookie=c.get_cookie('session',domain='example.test')
    fixture=tmp_path/'file-http.json'
    fixture.write_text(json.dumps({'base':f'http://127.0.0.1:{server.server_port}',
        'cookie':'session='+cookie.value,'expectedFile':{'path':path,'sha256':binding['sha256']}}))
    root=Path(__file__).resolve().parents[2]
    try:
        result=subprocess.run(['node',str(root/'qa/managed-live-context/query-http-tests.cjs'),str(fixture)],
            cwd=root,text=True,capture_output=True,timeout=30)
        assert result.returncode==0,result.stderr
        assert 'PASS actual HTTP' in result.stdout
    finally:
        server.shutdown();thread.join(timeout=5)


def test_company_binding_before_voice_uses_no_runtime_and_keeps_existing_guards(files):
    enabled,_,save=files;app,c,login,_,_,calls=enabled
    path,_=save()
    def action(company,action,**data):
        return c.post(f'/api/live/file-sources/{company}/{action}',json=data,headers=ORIGIN)
    preview=action(7,'preview',path=path);assert preview.status_code==200
    assert preview.json['companyId']==7
    assert action(7,'bind',path=path,sha256=preview.json['sha256'],expectedRevision=0,confirmOwnership=False).status_code==400
    binding=action(7,'bind',path=path,sha256=preview.json['sha256'],expectedRevision=0,confirmOwnership=True)
    assert binding.status_code==200 and calls==[]
    assert len(action(7,'list').json['bindings'])==1
    assert action(8,'list').json['bindings']==[]
    assert action(999,'list').status_code==403
    assert action(7,'preview',path=path,userId=32).status_code==400
    assert c.post('/api/live/file-sources/7/list',json={}).status_code==403
    assert c.post('/api/live/file-sources/7/list',json={},headers={**ORIGIN,'X-Fixture-Token':'yes'}).status_code==403
    from models import db,Company
    with app.app_context():
        db.session.get(Company,7).status='inactive';db.session.commit()
    assert action(7,'list').status_code==403
    login(32);assert action(8,'list').status_code==403
    assert calls==[]
