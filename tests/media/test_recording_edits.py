"""Manual edit contracts. Synthetic bytes, mocked FFmpeg/ffprobe/Postiz only."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_recordings import queue, client, create, finish, get, init  # noqa: F401
from recording_edits import video_trim

MP4 = b'\x00\x00\x00\x18ftypisom' + b'synthetic-not-playable' * 4


def upload_video(c, r, key, position):
    response = c.post(f"/api/recordings/{r['id']}/uploads", json={
        'client_key': key, 'name': key+'.mp4', 'size': len(MP4), 'position': position})
    assert response.status_code == 201, response.data
    finish(c, r, response.json, MP4)
    return response.json


@pytest.mark.parametrize('trim', [None, [], {'start_seconds': True}, {'start_seconds': None},
    {'start_seconds': -1}, {'end_seconds': 0}, {'start_seconds': 2, 'end_seconds': 1},
    {'end_seconds': float('inf')}, {'start_seconds': float('nan')}, {'end_seconds': 10**1000}, {'path': '/tmp/raw'}])
def test_invalid_trim(trim):
    with pytest.raises(ValueError): video_trim(trim)


def test_close_freezes_cuts_and_retries_require_same_decisions(queue):
    c=client(queue); r=create(c); a=upload_video(c,r,'a',0); b=upload_video(c,r,'b',1)
    root=f"/api/recordings/{r['id']}"
    payload={'expected_revision':get(c,r)['revision'],'upload_ids':[a['id'],b['id']],
             'edits':{a['id']:{'start_seconds':1,'end_seconds':3}}}
    for invalid in ({'foreign':{}}, {a['id']:{'path':'elsewhere'}}):
        assert c.post(root+'/close',json={**payload,'edits':invalid}).status_code==400
    response=c.post(root+'/close',json=payload);assert response.status_code==201,response.data
    v1=response.json['versions'][0]
    assert v1['snapshot']['assets'][0]['trim']=={'start_seconds':1.0,'end_seconds':3.0}
    assert 'trim' not in v1['snapshot']['assets'][1]
    assert c.post(root+'/close',json=payload).status_code==200
    assert c.post(root+'/close',json={**payload,'edits':{a['id']:{'start_seconds':2}}}).status_code==409
    assert c.post(root+f"/versions/{v1['id']}/feedback",json={'client_key':'feedback','text':'Tirar começo do segundo take'}).status_code==201
    reopened=c.post(root+'/reopen',json={'expected_revision':response.json['revision']});assert reopened.status_code==200
    v2=c.post(root+'/close',json={**payload,'expected_revision':reopened.json['revision'],
        'edits':{b['id']:{'start_seconds':2}}})
    assert v2.status_code==201,v2.data
    latest,old=v2.json['versions']
    assert latest['number']==2 and old['snapshot']==v1['snapshot']
    assert latest['job']['id']!=old['job']['id'] and not latest['qa_valid']
    assert v2.json['feedback'][0]['version_id']==old['id']


def test_image_cannot_receive_video_trim(queue):
    c=client(queue);r=create(c);u=init(c,r);finish(c,r,u)
    response=c.post(f"/api/recordings/{r['id']}/close",json={'expected_revision':get(c,r)['revision'],
        'upload_ids':[u['id']],'edits':{u['id']:{}}})
    assert response.status_code==400


@pytest.mark.parametrize('has_audio',[True,False])
def test_renderer_seeks_and_maps_original_time_without_running_ffmpeg(tmp_path,monkeypatch,has_audio):
    import recording_render as renderer
    from recordings_storage import private_path,hash_file
    monkeypatch.setenv('MEDIA_WORKSPACE',str(tmp_path))
    source=private_path('recordings/1/raw.mp4');source.parent.mkdir(parents=True);source.write_bytes(MP4)
    commands=[]
    def metadata(path):return SimpleNamespace(duration_seconds=10 if Path(path)==source else 2,has_audio=has_audio)
    monkeypatch.setattr(renderer,'extract_metadata',metadata)
    monkeypatch.setattr(renderer.subprocess,'run',lambda command,**kwargs: commands.append(command) or SimpleNamespace(returncode=0))
    asset={'id':'raw','path':'recordings/1/raw.mp4','sha256':hash_file(source),'kind':'video','trim':{'start_seconds':2,'end_seconds':4}}
    result=renderer.assemble_recording({'assets':[asset]},tmp_path/'final.mp4',tmp_path/'work')
    command=commands[0]
    assert command[command.index('-ss')+1]=='2.0' and command.index('-ss')<command.index('-i')
    assert command[command.index('-t')+1]=='2.0'
    assert ('anullsrc=r=48000:cl=stereo' in command)==(not has_audio)
    assert result['assembly_time_map']==[{'asset_id':'raw','source_start':2.0,'source_end':4.0,'edited_start':0.0,'edited_end':2.0}]
    assert result['feedback_applied'] is False
    commands.clear();asset['trim']={'start_seconds':9,'end_seconds':11}
    with pytest.raises(renderer.RecordingRenderError,match='duração'):renderer.assemble_recording({'assets':[asset]},tmp_path/'bad.mp4',tmp_path/'bad')
    assert not commands


def test_two_raws_feedback_v2_human_release_mocked_channels(queue,monkeypatch,tmp_path):
    """Full workflow contract with synthetic bytes and all execution boundaries mocked."""
    import importlib
    from datetime import datetime,timedelta,timezone
    from media_validation import VideoMetadata
    source=tmp_path/'take.mp4';source.write_bytes(MP4)
    c=client(queue);r=create(c);data=source.read_bytes()
    response=c.post(f"/api/recordings/{r['id']}/uploads",json={'client_key':'take','name':'take.mp4','size':len(data),'position':0})
    assert response.status_code==201
    u=response.json;finish(c,r,u,data)
    second=upload_video(c,r,'second',1)
    fresh=get(c,r)
    closed_response=c.post(f"/api/recordings/{r['id']}/close",json={'expected_revision':fresh['revision'],'upload_ids':[u['id'],second['id']]})
    assert closed_response.status_code==201
    closed=closed_response.json;v=closed['versions'][0]
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
    def assemble(snapshot,output,work,**kwargs):
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(MP4 + snapshot['version_id'].encode())
        return {**snapshot,'expected_duration':4,'feedback_applied':False}
    monkeypatch.setattr(worker,'assemble_recording',assemble)
    monkeypatch.setattr(worker,'validate_mp4',lambda *a,**k:VideoMetadata(4,720,1280,30,'h264',True,128,'mp4'))
    worker.process_job(claimed.json)
    old=v
    root=f"/api/recordings/{r['id']}"
    assert c.post(root+f"/versions/{old['id']}/feedback",json={'client_key':'cut','text':'Cortar início do segundo'}).status_code==201
    refreshed=get(c,r)
    reopened=c.post(root+'/reopen',json={'expected_revision':refreshed['revision']});assert reopened.status_code==200
    next_version=c.post(root+'/close',json={'expected_revision':reopened.json['revision'],
        'upload_ids':[u['id'],second['id']],'edits':{second['id']:{'start_seconds':2,'end_seconds':4}}})
    assert next_version.status_code==201,next_version.data
    v=next_version.json['versions'][0]
    assert next_version.json['versions'][1]['snapshot']==old['snapshot']
    path=f"/api/media/jobs/{v['job']['id']}"
    claimed=c.post(path+'/run',json={'recording_batch':'v1'});assert claimed.status_code==200
    assert claimed.json['result']['assets'][1]['trim']=={'start_seconds':2.0,'end_seconds':4.0}
    worker.process_job(claimed.json)
    checks={k:True for k in ('audio','captions','face','safe_zones','rights')}
    old_hash=get(c,r)['versions'][1]['job']['render_sha256']
    assert c.post(root+f"/versions/{old['id']}/qa",json={'render_sha256':old_hash,'checks':checks}).status_code==409
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

