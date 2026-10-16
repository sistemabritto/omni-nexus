"""Internal cuts and immutable human rejection; network/render boundaries mocked."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from flask import g, request
from test_recordings import queue, client, create, get, finish  # noqa: F401
from test_recording_edits import upload_video
from recording_edits import video_segments


@pytest.mark.parametrize('value',[
    {'keep_segments':[]},{'keep_segments':[{}]*21},{'keep_segments':[{},{}]},
    {'keep_segments':[{'end_seconds':3},{'start_seconds':2}]},
    {'keep_segments':[{'start_seconds':4,'end_seconds':5},{'end_seconds':2}]},
    {'keep_segments':[{'end_seconds':1}], 'path':'injected'},
])
def test_reject_ambiguous_kept_intervals(value):
    with pytest.raises(ValueError):video_segments(value)


def make_batch(queue):
    c=client(queue);r=create(c);u=upload_video(c,r,'take',0);root=f"/api/recordings/{r['id']}"
    edits={u['id']:{'keep_segments':[{'start_seconds':0,'end_seconds':1},{'start_seconds':2,'end_seconds':3}]}}
    body={'expected_revision':get(c,r)['revision'],'upload_ids':[u['id']],'edits':edits}
    response=c.post(root+'/close',json=body);assert response.status_code==201,response.data
    return c,r,u,response.json,body


def worker_module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[2]/'media_worker/worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    return worker


def test_v1_worker_protocol_cannot_list_or_claim_v2_new_worker_claims_both(queue,monkeypatch):
    @queue.before_request
    def service():
        if request.headers.get('X-Service'):g.auth_via_api_token=True
    c,r,u,closed,body=make_batch(queue);v=closed['versions'][0];url='/api/media/jobs/'+v['job']['id'];headers={'X-Service':'yes'}
    assert v['snapshot']['edit_plan_version']==2
    assert c.post(f"/api/recordings/{r['id']}/close",json=body).status_code==200
    # Exact list/claim capability advertised by worker at base 149c649.
    assert not c.get('/api/media/jobs?status=queued&recording_batch=v1',headers=headers).json
    assert c.post(url+'/run',json={'recording_batch':'v1'},headers=headers).status_code==409
    assert get(c,r)['versions'][0]['job']['status']=='queued'
    old=create(c,origin='legacy');legacy=upload_video(c,old,'legacy',0)
    legacy_closed=c.post(f"/api/recordings/{old['id']}/close",json={'expected_revision':get(c,old)['revision'],'upload_ids':[legacy['id']], 'edits':{legacy['id']:{'start_seconds':0,'end_seconds':1}}})
    assert legacy_closed.status_code==201
    old_version=legacy_closed.json['versions'][0];assert old_version['snapshot']['edit_plan_version']==1
    assert [j['id'] for j in c.get('/api/media/jobs?status=queued&recording_batch=v1',headers=headers).json]==[old_version['job']['id']]
    worker=worker_module('segments_capability_worker')
    class LocalAPI:
        def get(self,url,params):
            assert params['recording_batch']=='v1' and params['recording_edits']=='v2'
            response=c.get(url,query_string=params,headers=headers);assert response.status_code==200
            return response.json
        def post(self,url,data):
            assert data['recording_edits']=='v2'
            response=c.post(url,json=data,headers=headers);assert response.status_code==200,response.data
            return response.json
    monkeypatch.setattr(worker,'evo',LocalAPI())
    jobs=[worker._claim_next_job(),worker._claim_next_job()]
    assert {job['id'] for job in jobs}=={v['job']['id'],old_version['job']['id']}
    assert {job['result']['edit_plan_version'] for job in jobs}=={1,2}


def test_internal_intervals_render_order_and_map_mocked(tmp_path,monkeypatch):
    import recording_render as renderer
    from recordings_storage import private_path,hash_file
    monkeypatch.setenv('MEDIA_WORKSPACE',str(tmp_path))
    source=private_path('recordings/raw.mp4');source.parent.mkdir(parents=True);source.write_bytes(b'fixture')
    commands=[]
    monkeypatch.setattr(renderer,'extract_metadata',lambda path:SimpleNamespace(duration_seconds=5 if Path(path)==source else 1,has_audio=True))
    monkeypatch.setattr(renderer.subprocess,'run',lambda command,**kwargs:commands.append(command) or SimpleNamespace(returncode=0))
    asset={'id':'raw','path':'recordings/raw.mp4','kind':'video','sha256':hash_file(source),
           'trim':{'keep_segments':[{'start_seconds':0,'end_seconds':1},{'start_seconds':3,'end_seconds':4}]}}
    result=renderer.assemble_recording({'assets':[asset]},tmp_path/'final.mp4',tmp_path/'work')
    assert [command[command.index('-ss')+1] for command in commands[:-1]]==['0.0','3.0']
    assert [(x['source_start'],x['source_end'],x['edited_start'],x['edited_end']) for x in result['assembly_time_map']]==[(0,1,0,1),(3,4,1,2)]
    assert result['expected_duration']==2 and result['feedback_applied'] is False


def test_rejection_revokes_release_and_is_immutable_until_new_version(queue,monkeypatch,tmp_path):
    @queue.before_request
    def service():
        if request.headers.get('X-Service'):g.auth_via_api_token=True
    import models as m
    from media_validation import VideoMetadata
    c,r,u,closed,body=make_batch(queue);v=closed['versions'][0];root=f"/api/recordings/{r['id']}";url='/api/media/jobs/'+v['job']['id']
    worker=worker_module('review_loop_worker')
    def patch(job_id,**fields):
        response=c.patch('/api/media/jobs/'+job_id,json=fields);assert response.status_code==200,response.data
        return response.json
    def assemble(snapshot,output,work,**kwargs):
        output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(b'synthetic-'+snapshot['version_id'].encode())
        return {**snapshot,'expected_duration':2}
    monkeypatch.setattr(worker,'_patch',patch);monkeypatch.setattr(worker,'assemble_recording',assemble)
    monkeypatch.setattr(worker,'validate_mp4',lambda *a,**k:VideoMetadata(2,720,1280,30,'h264',True,100,'mp4'))
    monkeypatch.setattr(worker,'run_opencode_media_job',lambda *a,**k:pytest.fail('no model calls'))
    def render(version):
        claim=c.post('/api/media/jobs/'+version['job']['id']+'/run',json={'recording_batch':'v1','recording_edits':'v2'});assert claim.status_code==200
        worker.process_job(claim.json)
        return get(c,r)['versions'][0]
    v=render(v);sha=v['job']['render_sha256'];checks={key:True for key in ('audio','captions','face','safe_zones','rights')}
    qa=root+f"/versions/{v['id']}/qa";reject=root+f"/versions/{v['id']}/reject"
    assert c.post(qa,json={'render_sha256':sha,'checks':checks}).status_code==200
    from datetime import datetime,timedelta,timezone
    channels=[{'platform':'instagram','integration_id':'ig','content':'fixture','scheduled_at_utc':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()}]
    release=c.put(url+'/release',json={'render_version':'v1','channels':channels});assert release.status_code==200
    assert c.post(url+'/release/approve',json={'digest':release.json['digest']}).status_code==200
    with queue.app_context():
        item=m.db.session.get(m.MediaJob,v['job']['id']);assert item.status=='approved'
    reject_body={'reason':'Retirar erro no meio do take','render_sha256':sha,'expected_revision':get(c,r)['revision']}
    assert c.post(reject,json=reject_body,headers={'X-Service':'yes'}).status_code==403
    assert client(queue,4).post(reject,json=reject_body).status_code==404
    assert client(queue,2).post(reject,json=reject_body).status_code in (403,404)
    with queue.app_context():
        item=m.db.session.get(m.MediaRelease,v['job']['id']);item.busy=True;m.db.session.commit()
    assert c.post(reject,json=reject_body).status_code==409
    with queue.app_context():
        item=m.db.session.get(m.MediaRelease,v['job']['id']);item.busy=False;m.db.session.commit()
    assert c.post(reject,json={**reject_body,'expected_revision':0}).status_code==409
    response=c.post(reject,json=reject_body);assert response.status_code==201,response.data
    assert response.json['state']=='changes_requested'
    assert response.json['versions'][0]['job']['status']=='cancelled'
    assert c.get(url+'/video').status_code==200
    assert c.post(url+'/run',json={'recording_batch':'v1','recording_edits':'v2'}).status_code==409
    assert response.json['versions'][0]['rejection']['by']=='admin'
    assert not response.json['versions'][0]['qa_valid'] and not response.json['versions'][0]['release']['approval_valid']
    assert c.post(reject,json=reject_body).status_code==200
    assert c.post(reject,json={**reject_body,'reason':'overwrite'}).status_code==409
    assert c.post(qa,json={'render_sha256':sha,'checks':checks}).status_code==409
    assert c.post(url+'/release/approve',json={'digest':release.json['digest']}).status_code==409
    assert c.post(url+'/release/distribute').status_code==409
    # A re-edit creates an immutable new snapshot without silently scheduling/reprocessing old content.
    reopened=c.post(root+'/reopen',json={'expected_revision':get(c,r)['revision']});assert reopened.status_code==200
    fresh=c.post(root+'/close',json={**body,'expected_revision':reopened.json['revision'],
        'edits':{u['id']:{'keep_segments':[{'start_seconds':0,'end_seconds':.5},{'start_seconds':2.5,'end_seconds':3}]}}})
    assert fresh.status_code==201 and fresh.json['versions'][1]['rejection']
    assert fresh.json['versions'][1]['snapshot']==v['snapshot']
    v2=render(fresh.json['versions'][0]);assert not v2['rejection'] and not v2['qa_valid']
    url2='/api/media/jobs/'+v2['job']['id']
    assert c.post(root+f"/versions/{v2['id']}/qa",json={'render_sha256':v2['job']['render_sha256'],'checks':checks}).status_code==200
    release2=c.put(url2+'/release',json={'render_version':'v2','channels':channels});assert release2.status_code==200
    assert c.post(url2+'/release/approve',json={'digest':release2.json['digest']}).status_code==200
    assert c.post(url+'/release/distribute').status_code==409
    # Use the established fake Postiz contract for two idempotent retries.
    class Fake:
        def __init__(self):self.posts={};self.created=0;self.uploaded=0;self.scheduled=0
        def list_integrations(self):return [{'id':'ig','identifier':'instagram'}]
        def upload_file(self,path):self.uploaded+=1;return {'id':'fixture','path':'https://invalid.example/fixture.mp4'}
        def create_draft(self,**kwargs):
            self.created+=1;self.posts['p']={'id':'p','state':'DRAFT','content':kwargs['content'],'publishDate':kwargs['now_iso_utc'],'integration':{'id':'ig'}}
            return [{'postId':'p'}]
        def change_status(self,post_id,status):self.scheduled+=1;self.posts[post_id]['state']='QUEUE'
        def list_posts(self,window):return list(self.posts.values())
    import routes.media_jobs as routes
    fake=Fake();monkeypatch.setattr(routes.PostizClient,'from_env',lambda:fake)
    for _ in range(2):assert c.post(url2+'/release/distribute').status_code==200
    assert (fake.uploaded,fake.created,fake.scheduled)==(1,1,1)
    assert c.post(root+f"/versions/{v2['id']}/reject",json={'reason':'after delivery','render_sha256':v2['job']['render_sha256'],'expected_revision':get(c,r)['revision']}).status_code==409
