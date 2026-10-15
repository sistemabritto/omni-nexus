"""Private mobile queue contracts; all APIs local/in-memory, no external services."""
import hashlib
import importlib
import io
import json
import pytest

PNG = b'\x89PNG\r\n\x1a\n' + b'local-test-pixels' * 4

@pytest.fixture
def queue(app):
    import models as m
    import routes.recordings as routes
    importlib.reload(routes)
    app.register_blueprint(routes.bp)
    with app.app_context():
        m.db.session.add_all([m.Company(id=1,name='A',slug='a',created_at='2026-10-15',updated_at='2026-10-15'),m.Company(id=2,name='B',slug='b',created_at='2026-10-15',updated_at='2026-10-15'),
                              m.User(id=3,username='editor-a',role='operator',password_hash='test'),m.User(id=4,username='editor-b',role='operator',password_hash='test')])
        m.db.session.add_all([m.RecordingAccess(user_id=3,company_id=1,level='editor'),m.RecordingAccess(user_id=4,company_id=2,level='editor'),m.RecordingAccess(user_id=2,company_id=1,level='viewer')])
        m.db.session.commit()
    return app

def client(queue, user=1):
    c=queue.test_client()
    if user:
        with c.session_transaction() as session:session['_user_id']=str(user);session['_fresh']=True
    return c

def create(c, company=1, origin='script-1'):
    response=c.post('/api/recordings',json={'company_id':company,'title':'Teste','script':'Roteiro original','origin_type':'script','origin_id':origin,
        'references':[{'label':'histórico','reference':'artifact:old'},{'label':'histórico','reference':'artifact:old'}]})
    assert response.status_code in (200,201),response.data
    return response.json

def init(c,r,key='one',position=0,data=PNG):
    response=c.post(f"/api/recordings/{r['id']}/uploads",json={'client_key':key,'name':key+'.png','size':len(data),'position':position,'sha256':hashlib.sha256(data).hexdigest()})
    assert response.status_code in (200,201),response.data
    return response.json

def finish(c,r,u,data=PNG):
    root=f"/api/recordings/{r['id']}/uploads/{u['id']}"
    assert c.put(root+'?offset=0',data=data).status_code==200
    response=c.post(root+'/complete');assert response.status_code==200,response.data
    return response.json

def get(c,r):return c.get('/api/recordings/'+r['id']).json

def close(c,r,ids):
    fresh=get(c,r)
    payload={'expected_revision':fresh['revision'],'upload_ids':ids,'photo_seconds':1}
    response=c.post(f"/api/recordings/{r['id']}/close",json=payload)
    assert response.status_code==201,response.data
    return response.json,payload

def test_origin_and_script_versions_are_immutable(queue):
    c=client(queue);r=create(c);assert create(c)['id']==r['id']
    assert len(r['scripts'][0]['references'])==2
    assert c.post('/api/recordings',json={'company_id':1,'title':'Bad ref','script':'test','references':[{'label':'bad','reference':'https:no-host'}]}).status_code==400
    response=c.post(f"/api/recordings/{r['id']}/scripts",json={'expected_revision':0,'script':'Outro','references':[]})
    assert response.status_code==201
    assert [s['text'] for s in response.json['scripts']]==['Outro','Roteiro original']
    assert create(c,2)['id']!=r['id']

def test_tenant_boundaries_cover_lists_files_jobs_feedback(queue):
    a=client(queue,3);b=client(queue,4);r=create(a);u=init(a,r);finish(a,r,u);closed,_=close(a,r,[u['id']]);v=closed['versions'][0]
    root=f"/api/recordings/{r['id']}"
    feedback=a.post(f"{root}/versions/{v['id']}/feedback",json={'client_key':'f','text':'Corrigir início'})
    assert feedback.status_code==201
    for path in [root,root+f"/uploads/{u['id']}/file",f"/api/media/jobs/{v['job']['id']}",f"/api/media/jobs/{v['job']['id']}/video",f"/api/media/jobs/{v['job']['id']}/release"]:
        assert b.get(path).status_code==404,path
    assert b.get('/api/recordings?company_id=1').status_code==404
    assert not any(j['id']==v['job']['id'] for j in b.get('/api/media/jobs').json)
    assert any(j['id']==v['job']['id'] for j in a.get('/api/media/jobs').json)
    assert client(queue,0).get(root).status_code==401
    assert client(queue,2).get(root).status_code==200
    assert client(queue,2).post(root+'/reopen',json={'expected_revision':closed['revision']}).status_code in (403,404)
    assert b.put('/api/recordings/access',json={'company_id':1,'user_id':4,'level':'editor'}).status_code==403
    assert a.get(root).headers['Cache-Control']=='private, no-store'

def test_resume_chunks_checksum_and_no_first_upload_trigger(queue):
    import models as m
    c=client(queue);r=create(c);u=init(c,r)
    assert init(c,r)['id']==u['id']
    root=f"/api/recordings/{r['id']}/uploads/{u['id']}"
    assert c.put(root+'?offset=3',data=PNG[:8]).status_code==409
    assert c.put(root+'?offset=0',data=PNG[:8]).status_code==200
    assert c.put(root+'?offset=0',data=PNG[:8]).json['received']==8
    assert c.put(root+'?offset=0',data=b'changed!').status_code==409
    assert c.post(root+'/complete').status_code==409
    partial=get(c,r)
    assert c.post(f"/api/recordings/{r['id']}/close",json={'expected_revision':partial['revision'],'upload_ids':[u['id']]}).status_code==409
    assert c.put(root+'?offset=8',data=PNG[8:]).status_code==200
    assert c.post(root+'/complete').status_code==200
    with queue.app_context():assert m.MediaJob.query.count()==0
    assert c.get(root+'/file').data==PNG
    closed,payload=close(c,r,[u['id']])
    assert closed['state']=='ready_to_edit'
    assert c.post(f"/api/recordings/{r['id']}/close",json=payload).status_code==200
    with queue.app_context():assert m.MediaJob.query.count()==1
    assert c.post(f"/api/recordings/{r['id']}/close",json={**payload,'photo_seconds':4}).status_code==409

def test_order_duplicates_and_excluded_incomplete_are_preserved(queue):
    c=client(queue);r=create(c);one=init(c,r,'one',0);two=init(c,r,'two',1);three=init(c,r,'three',2)
    finish(c,r,two);dupe=finish(c,r,one);assert dupe['duplicate_of']==two['id']
    fresh=get(c,r)
    moved=c.put(f"/api/recordings/{r['id']}/order",json={'expected_revision':fresh['revision'],'upload_ids':[two['id'],one['id'],three['id']]})
    assert moved.status_code==200,moved.data
    assert c.post(f"/api/recordings/{r['id']}/close",json={'expected_revision':moved.json['revision'],'upload_ids':[one['id'],two['id']]}).status_code==409
    assert c.post(f"/api/recordings/{r['id']}/uploads/{three['id']}/exclude").status_code==200
    assert c.post(f"/api/recordings/{r['id']}/uploads/{one['id']}/exclude").status_code==409
    closed,_=close(c,r,[one['id'],two['id']])
    assert [a['id'] for a in closed['versions'][0]['snapshot']['assets']]==[two['id'],one['id']]
    assert len(closed['uploads'])==3

def test_checksum_invalid_media_stale_revision_and_source_change(queue):
    import models as m
    from recordings_storage import private_path
    c=client(queue);r=create(c);u=init(c,r)
    root=f"/api/recordings/{r['id']}/uploads/{u['id']}"
    assert c.put(root+'?offset=0',data=b'x'*len(PNG)).status_code==200
    assert c.post(root+'/complete').status_code==422
    r2=create(c,origin='second');u2=init(c,r2);finish(c,r2,u2)
    assert c.post(f"/api/recordings/{r2['id']}/close",json={'expected_revision':0,'upload_ids':[u2['id']]}).status_code==409
    with queue.app_context():private_path(m.db.session.get(m.RecordingUpload,u2['id']).storage_path).write_bytes(b'changed')
    fresh=get(c,r2)
    assert c.post(f"/api/recordings/{r2['id']}/close",json={'expected_revision':fresh['revision'],'upload_ids':[u2['id']]}).status_code==409
    assert c.post(f"/api/recordings/{r['id']}/uploads",json={'client_key':'html','name':'bad.html','size':10,'position':1}).status_code==400

def test_feedback_text_audio_bound_to_version_without_transcription(queue):
    c=client(queue);r=create(c);u=init(c,r);finish(c,r,u);closed,_=close(c,r,[u['id']]);v=closed['versions'][0]
    root=f"/api/recordings/{r['id']}/versions/{v['id']}/feedback"
    response=c.post(root,data={'client_key':'voice1','text':'Cortar pausa','audio':(io.BytesIO(b'RIFF1234WAVE'+b'fake-wave'),'feedback.wav')})
    assert response.status_code==201,response.data
    assert response.json['transcribed'] is False
    assert c.post(root,json={'client_key':'voice1','text':'Cortar pausa'}).status_code==200
    fresh=get(c,r);assert len(fresh['feedback'])==1;item=fresh['feedback'][0]
    assert item['version_id']==v['id'];assert c.get(item['audio_url']).status_code==200
    assert client(queue,4).get(item['audio_url']).status_code==404
    other=create(c,origin='other')
    assert c.post(f"/api/recordings/{other['id']}/versions/{v['id']}/feedback",json={'client_key':'x','text':'x'}).status_code==404

def test_states_qa_and_superseding_version(queue,monkeypatch):
    import models as m
    import media_release
    from recordings_access import release_readiness_error
    c=client(queue);r=create(c);u=init(c,r);finish(c,r,u);closed,_=close(c,r,[u['id']]);v=closed['versions'][0]
    with queue.app_context():
        job=m.db.session.get(m.MediaJob,v['job']['id']);job.status='rendering';m.db.session.commit()
    assert get(c,r)['state']=='editing'
    with queue.app_context():
        job=m.db.session.get(m.MediaJob,v['job']['id']);job.status='ready_for_review';job.render_sha256='a'*64;m.db.session.commit()
        assert release_readiness_error(job)=='recording_requires_human_audio_caption_rights_qa'
    assert get(c,r)['state']=='in_review'
    monkeypatch.setattr(media_release,'render_binding',lambda job:{})
    qa=f"/api/recordings/{r['id']}/versions/{v['id']}/qa"
    checks={k:True for k in ('audio','captions','face','safe_zones','rights')}
    assert c.post(qa,json={'render_sha256':'a'*64,'checks':{}}).status_code==400
    assert c.post(qa,json={'render_sha256':'b'*64,'checks':checks}).status_code==409
    response=c.post(qa,json={'render_sha256':'a'*64,'checks':checks});assert response.status_code==200,response.data
    with queue.app_context():assert release_readiness_error(m.db.session.get(m.MediaJob,v['job']['id'])) is None
    fresh=get(c,r);assert c.post(f"/api/recordings/{r['id']}/reopen",json={'expected_revision':fresh['revision']}).status_code==200
    assert c.post(qa,json={'render_sha256':'a'*64,'checks':checks}).status_code==409
    assert c.post(f"/api/media/jobs/{v['job']['id']}/release/approve",json={}).status_code==409
    with queue.app_context():assert release_readiness_error(m.db.session.get(m.MediaJob,v['job']['id']))=='recording_version_superseded'
    assert get(c,r)['versions'][0]['id']==v['id']


def test_busy_release_blocks_reopen_and_script_changes(queue):
    import models as m
    c=client(queue);r=create(c);u=init(c,r);finish(c,r,u);closed,_=close(c,r,[u['id']]);v=closed['versions'][0]
    with queue.app_context():
        m.db.session.add(m.MediaRelease(job_id=v['job']['id'],snapshot_json='{}',digest='d'*64,progress_json='{}',busy=True));m.db.session.commit()
    for suffix,payload in [('reopen',{'expected_revision':closed['revision']}),('scripts',{'expected_revision':closed['revision'],'script':'Novo','references':[]})]:
        response=c.post(f"/api/recordings/{r['id']}/{suffix}",json=payload)
        assert response.status_code==409 and response.json['error']=='release_busy'


def test_states_require_per_channel_evidence():
    from types import SimpleNamespace
    from routes.recordings import state_for
    row=SimpleNamespace(batch=1,script_revision=1,closed=True)
    release={'snapshot':{'channels':[{},{}]},'approval_valid':True,'progress':{'channels':{}}}
    version={'batch':1,'script_revision':1,'job':{'status':'approved'},'release':release}
    assert state_for(row,[],[version])=='approved'
    release['progress']['channels']={'one':{'state':'scheduled'},'two':{'state':'pending'}}
    assert state_for(row,[],[version])=='partial_distribution'
    release['progress']['channels']['two']['state']='retryable_failure'
    assert state_for(row,[],[version])=='distribution_attention'
    release['progress']['channels']['two']['state']='scheduled'
    assert state_for(row,[],[version])=='scheduled'
    for entry in release['progress']['channels'].values():entry['state']='published'
    assert state_for(row,[],[version])=='published'


def test_human_qa_rejects_api_token_and_render_mutation(queue,monkeypatch):
    import models as m
    import media_release
    from flask import g,request
    @queue.before_request
    def simulate_service_auth():
        if request.headers.get('X-Test-Service'):g.auth_via_api_token=True
    c=client(queue);r=create(c);u=init(c,r);finish(c,r,u);closed,_=close(c,r,[u['id']]);v=closed['versions'][0]
    with queue.app_context():
        job=m.db.session.get(m.MediaJob,v['job']['id']);job.status='ready_for_review';job.render_sha256='a'*64;m.db.session.commit()
    path=f"/api/recordings/{r['id']}/versions/{v['id']}/qa"
    payload={'render_sha256':'a'*64,'checks':{k:True for k in ('audio','captions','face','safe_zones','rights')}}
    assert c.post(path,json=payload,headers={'X-Test-Service':'yes'}).status_code==403
    def changed(job):raise media_release.ReleaseError('bytes changed')
    monkeypatch.setattr(media_release,'render_binding',changed)
    assert c.post(path,json=payload).status_code==409


def test_orphan_chunk_recovery_and_feedback_key_conflict(queue):
    import models as m
    from recordings_storage import atomic_write,private_path
    c=client(queue);r=create(c);u=init(c,r)
    with queue.app_context():
        item=m.db.session.get(m.RecordingUpload,u['id']);atomic_write(private_path(item.storage_path).parent/'chunk-0',PNG)
    finish(c,r,u);closed,_=close(c,r,[u['id']]);v=closed['versions'][0]
    path=f"/api/recordings/{r['id']}/versions/{v['id']}/feedback"
    assert c.post(path,json={'client_key':'same','text':'Primeiro'}).status_code==201
    assert c.post(path,json={'client_key':'same','text':'Diferente'}).status_code==409


def test_closed_batch_worker_to_human_release_and_simulated_channels(queue,monkeypatch,tmp_path):
    """Full queue path with real local FFmpeg and an in-memory Postiz double."""
    import shutil
    import subprocess
    from pathlib import Path
    from datetime import datetime,timedelta,timezone
    if not shutil.which('ffmpeg'):pytest.skip('local FFmpeg required')
    source=tmp_path/'take.mp4'
    subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-f','lavfi','-i','color=green:s=160x120:r=30','-t','0.5','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,capture_output=True)
    c=client(queue);r=create(c);data=source.read_bytes()
    response=c.post(f"/api/recordings/{r['id']}/uploads",json={'client_key':'take','name':'take.mp4','size':len(data),'position':0})
    assert response.status_code==201
    u=response.json;finish(c,r,u,data);closed,_=close(c,r,[u['id']]);v=closed['versions'][0]
    path=f"/api/media/jobs/{v['job']['id']}"
    claimed=c.post(path+'/run',json={'agent':'local-test','recording_batch':'v1'});assert claimed.status_code==200
    spec=importlib.util.spec_from_file_location('recording_worker_test',Path(__file__).resolve().parents[2]/'media_worker/worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    def patch(job_id,**fields):
        response=c.patch(f'/api/media/jobs/{job_id}',json=fields)
        assert response.status_code==200,response.data
        return response.json
    monkeypatch.setattr(worker,'_patch',patch)
    monkeypatch.setattr(worker,'run_opencode_media_job',lambda *a,**k:pytest.fail('no model permitted'))
    worker.process_job(claimed.json)
    rendered=get(c,r);assert rendered['state']=='in_review',rendered
    job=rendered['versions'][0]['job'];assert job['render_has_audio'] is True
    assert c.get(path+'/video').status_code==200
    date=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
    body={'render_version':'Gravação v1','channels':[{'platform':'instagram','integration_id':'ig','content':'Copy IG','scheduled_at_utc':date},{'platform':'linkedin','integration_id':'li','content':'Copy LI','scheduled_at_utc':date}]}
    release=c.put(path+'/release',json=body);assert release.status_code==200,release.data
    assert c.post(path+'/release/approve',json={'digest':release.json['digest']}).status_code==409
    checks={k:True for k in ('audio','captions','face','safe_zones','rights')}
    assert c.post(f"/api/recordings/{r['id']}/versions/{v['id']}/qa",json={'render_sha256':job['render_sha256'],'checks':checks}).status_code==200
    assert c.post(path+'/release/approve',json={'digest':release.json['digest']}).status_code==200
    assert get(c,r)['state']=='approved'
    class FakePostiz:
        def __init__(self):self.posts={};self.created=[]
        def list_integrations(self):return [{'id':'ig','identifier':'instagram'},{'id':'li','identifier':'linkedin'}]
        def upload_file(self,path):return {'id':'local-media','path':'https://media.invalid/mock.mp4'}
        def create_draft(self,**kwargs):
            key=kwargs['integration_id'];self.created.append(key)
            self.posts[key]={'id':key,'state':'DRAFT','content':kwargs['content'],'publishDate':kwargs['now_iso_utc'],'integration':{'id':key}}
            return [{'postId':key}]
        def change_status(self,post_id,status):self.posts[post_id]['state']='QUEUE'
        def list_posts(self,window):return list(self.posts.values())
    fake=FakePostiz();import routes.media_jobs as routes
    monkeypatch.setattr(routes.PostizClient,'from_env',lambda:fake)
    response=c.post(path+'/release/distribute');assert response.status_code==200,response.data
    assert get(c,r)['state']=='scheduled'
    assert c.post(path+'/release/distribute').status_code==200
    assert sorted(fake.created)==['ig','li']
    for post in fake.posts.values():post.update(state='PUBLISHED',releaseURL='https://example.invalid/proof')
    assert c.post(path+'/release/refresh').status_code==200
    assert get(c,r)['state']=='published'


def test_worker_intent_is_frozen_and_render_cannot_cross_job(queue,tmp_path):
    import models as m
    c=client(queue);r=create(c);u=init(c,r);finish(c,r,u);closed,_=close(c,r,[u['id']]);v=closed['versions'][0];path='/api/media/jobs/'+v['job']['id']
    assert client(queue,3).patch(path,json={'result_json':'{"assets":[]}'}).status_code==403
    assert c.patch(path,json={'render_path':str(tmp_path/'other-job/output/final.mp4')}).status_code==400
    # Even service-writable diagnostic results cannot replace the approved closed batch intent.
    with queue.app_context():
        job=m.db.session.get(m.MediaJob,v['job']['id']);job.result_json='{"assets":[]}';m.db.session.commit()
    claimed=c.post(path+'/run',json={'recording_batch':'v1'});assert claimed.status_code==200
    assert claimed.json['result']['assets']==v['snapshot']['assets']


def test_legacy_worker_cannot_claim_recordings_but_new_worker_can(queue,monkeypatch):
    from flask import g,request
    from pathlib import Path
    @queue.before_request
    def service_auth():
        if request.headers.get('X-Test-Service'):g.auth_via_api_token=True
    c=client(queue);r=create(c);u=init(c,r);finish(c,r,u);closed,_=close(c,r,[u['id']]);v=closed['versions'][0]
    path='/api/media/jobs/'+v['job']['id'];headers={'X-Test-Service':'yes'}
    assert not any(j['id']==v['job']['id'] for j in c.get('/api/media/jobs?status=queued&eligible=true',headers=headers).json)
    assert c.post(path+'/run',json={'agent':'old-worker'},headers=headers).status_code==409
    assert get(c,r)['versions'][0]['job']['status']=='queued'
    spec=importlib.util.spec_from_file_location('capability_worker_test',Path(__file__).resolve().parents[2]/'media_worker/worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    class LocalAPI:
        def get(self,url,params):
            response=c.get(url,query_string=params,headers=headers);assert response.status_code==200
            return response.json
        def post(self,url,data):
            response=c.post(url,json=data,headers=headers);assert response.status_code==200,response.data
            return response.json
    monkeypatch.setattr(worker,'evo',LocalAPI())
    claimed=worker._claim_next_job()
    assert claimed['id']==v['job']['id'] and claimed['status']=='preparing'
    assert claimed['result']['assets']==v['snapshot']['assets']
