"""Four combined entries and motion VSL; local fixtures, render/network mocked."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_recordings import queue,client,create,get  # noqa: F401
from video_project_spec import normalize_project
from video_project_render import build_composition


def spec():
    return {'entry_modes':['faceless','stickman','motion_vsl'],'script':'Roteiro original de fixture.',
        'brand_reference':'test/brand@fixture','audio_policy':'silent','scenes':[
            {'kind':'motion','title':'Primeiro argumento','text':'Explicação com fonte fornecida','duration':2,'metric':65,'metric_source':'Synthetic fixture, not a business claim'},
            {'kind':'stickman','title':'Conclusão','duration':2,'pose':'wave'}],
        'captions':[{'start':0,'end':2,'text':'Legenda temporizada'}]}


def test_combined_no_footage_composition_is_offline_deterministic(tmp_path):
    production=normalize_project(spec(),{})
    assert production['duration']==4
    snapshot={'production':production,'assets':[]}
    build_composition(snapshot,tmp_path/'a',width=720,height=1280)
    build_composition(snapshot,tmp_path/'b',width=720,height=1280)
    a=(tmp_path/'a/index.html').read_text();assert a==(tmp_path/'b/index.html').read_text()
    assert '<svg' in a and '.animate(' in a and 'caption-0' in a and 'data-no-timeline' in a
    assert 'http://' not in a and 'https://' not in a and 'setInterval' not in a


@pytest.mark.parametrize('change',[
    {'entry_modes':['unknown']},{'entry_modes':['long_cuts']},{'entry_modes':['enriched_edit']},{'audio_policy':'provided'},{'scenes':[]},
    {'scenes':[{'kind':'motion','duration':float('nan'),'title':'bad'}]},
    {'palette':{'background':'url(file:///etc/passwd)'}},
    {'captions':[{'start':3,'end':2,'text':'bad'}]},
])
def test_invalid_project_never_reaches_renderer(change):
    with pytest.raises(ValueError):normalize_project({**spec(),**change},{})


def test_long_cut_requires_semantic_evidence_and_authorized_asset():
    assets={'raw':{'id':'raw','kind':'video'}}
    value={**spec(),'entry_modes':['long_cuts','enriched_edit'],'scenes':[{'kind':'footage','title':'Trecho','duration':2,'asset_id':'raw','rights_reference':'Autoria da fixture','source_start':1}]}
    with pytest.raises(ValueError,match='semantic'):normalize_project(value,assets)
    value['scenes'][0]['selection']={'rationale':'Ideia completa revisada','transcript_excerpt':'Uma frase completa.','source_reference':'transcrição fornecida, 1–3s'}
    normalized=normalize_project(value,assets)
    assert normalized['scenes'][0]['selection']['rationale']=='Ideia completa revisada'
    with pytest.raises(ValueError):normalize_project(value,{})


def test_project_closure_without_uploads_is_versioned_and_old_workers_cannot_claim(queue):
    from flask import g,request
    @queue.before_request
    def service():
        if request.headers.get('X-Service'):g.auth_via_api_token=True
    c=client(queue);r=create(c);root='/api/recordings/'+r['id']
    body={'expected_revision':r['revision'],'uploads_confirmed':True,'upload_ids':[],'production':spec(),'format':'horizontal'}
    assert c.post(root+'/produce',json={**body,'uploads_confirmed':False}).status_code==400
    response=c.post(root+'/produce',json=body);assert response.status_code==201,response.data
    v=response.json['versions'][0];job=v['job'];assert v['snapshot']['production']['entry_modes']==spec()['entry_modes']
    assert job['width']==1280 and job['height']==720 and job['status']=='queued'
    assert c.post(root+'/produce',json=body).status_code==200
    summary=c.get('/api/recordings?company_id=1&summary=true').json[0]
    assert summary['version_count']==1 and summary['versions']==[] and summary['scripts']==[]
    assert c.post(root+'/produce',json={**body,'format':'vertical'}).status_code==409
    path='/api/media/jobs/'+job['id'];headers={'X-Service':'yes'}
    assert not c.get('/api/media/jobs?recording_batch=v1&recording_edits=v2',headers=headers).json
    assert c.post(path+'/run',json={'recording_batch':'v1','recording_edits':'v2'}).status_code==409
    assert c.post(path+'/run',json={'recording_batch':'v1','recording_edits':'v2','recording_project':'v1'}).status_code==200
    with queue.app_context():
        import models as m
        original=m.db.session.get(m.RecordingVersion,v['id']);source=json.loads(original.snapshot_json)
        assert source['creative_review_required'] is True
    reopened=c.post(root+'/reopen',json={'expected_revision':get(c,r)['revision']});assert reopened.status_code==200
    v2=c.post(root+'/produce',json={**body,'expected_revision':reopened.json['revision']});assert v2.status_code==201
    assert v2.json['versions'][1]['snapshot']==v['snapshot']
    assert v2.json['versions'][0]['creative_review'] is None


@pytest.mark.parametrize('distribute_before_update',[False,True])
def test_render_review_evidence_independence_and_common_release_gate(queue,monkeypatch,distribute_before_update):
    from flask import g,request
    @queue.before_request
    def service():
        if request.headers.get('X-Service'):g.auth_via_api_token=True
    import models as m
    from media_validation import VideoMetadata
    from media_workspace import job_dir
    from test_recording_editorial_review import worker_module
    from test_media_creative_review import sample
    c=client(queue);r=create(c);root='/api/recordings/'+r['id']
    response=c.post(root+'/produce',json={'expected_revision':r['revision'],'uploads_confirmed':True,'production':spec(),'upload_ids':[]})
    assert response.status_code==201,response.data
    v=response.json['versions'][0];url='/api/media/jobs/'+v['job']['id'];qa=root+f"/versions/{v['id']}/qa";review_url=root+f"/versions/{v['id']}/creative-review"
    with queue.app_context():
        m.db.session.add(m.User(id=5,username='independent-reviewer',role='admin',password_hash='test'));m.db.session.commit()
    reviewer=client(queue,5);worker=worker_module('project_gate_worker')
    def render(snapshot,output,work,**kwargs):
        output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(b'fake-video-not-a-real-render')
        frame=output.parent/'review-frame-0.png';frame.write_bytes(b'fake-frame-for-contract-test')
        return {**snapshot,'expected_duration':4,'review_evidence':{'render_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'frames':[{'ref':'output/review-frame-0.png','sha256':hashlib.sha256(frame.read_bytes()).hexdigest(),'at':1}]}}
    import video_project_render
    monkeypatch.setattr(video_project_render,'render_project',render)
    def patch(job_id,**fields):
        response=c.patch('/api/media/jobs/'+job_id,json=fields);assert response.status_code==200,response.data
        return response.json
    monkeypatch.setattr(worker,'_patch',patch)
    monkeypatch.setattr(worker,'validate_mp4',lambda *a,**k:VideoMetadata(4,720,1280,30,'h264',True,100,'mp4'))
    monkeypatch.setattr(worker,'run_opencode_media_job',lambda *a,**k:pytest.fail('model forbidden'))
    claimed=c.post(url+'/run',json={'recording_batch':'v1','recording_edits':'v2','recording_project':'v1'});assert claimed.status_code==200
    worker.process_job(claimed.json)
    current=get(c,r);job=current['versions'][0]['job'];assert job['status']=='ready_for_review'
    checks={key:True for key in ('audio','captions','face','safe_zones','rights')}
    assert c.post(qa,json={'render_sha256':job['render_sha256'],'checks':checks}).status_code==409
    review=sample();review.update(render_sha256=job['render_sha256'],version_id=v['id'],duration_seconds=4,brand_reference={'source':'test/brand','version':'fixture'})
    frame=job_dir(job['id'])/'output/review-frame-0.png';frame_sha=hashlib.sha256(frame.read_bytes()).hexdigest()
    for key,item in review['criteria'].items():
        item['evidence']=[{'kind':'audio_range' if key=='audio' else 'time_range','ref':'output/final.mp4','sha256':job['render_sha256'],'start':0,'end':1}] if key in ('audio','rhythm','transitions') else [{'kind':'frame','ref':'output/review-frame-0.png','sha256':frame_sha}]
    template=reviewer.get(review_url)
    assert template.status_code==200,template.data
    assert all(item['status']=='NOT_TESTED' for item in template.json['template']['criteria'].values())
    assert {item['id'] for item in template.json['guidance']}=={'anti_slop','taste'}
    assert all(len(item['text'])>100 for item in template.json['guidance'])
    body={'expected_revision':current['revision'],'review':review}
    assert c.post(review_url,json=body).status_code==403
    assert reviewer.post(review_url,json=body,headers={'X-Service':'yes'}).status_code==403
    unrelated=copy.deepcopy(body);unrelated['review']['criteria']['identity']['evidence'][0]['ref']='work/unrelated.png'
    assert reviewer.post(review_url,json=unrelated).status_code==400
    pending=copy.deepcopy(body);pending['review']['criteria']['audio'].update(status='NOT_TESTED',reason='No actual playback in this contract fixture')
    response=reviewer.post(review_url,json=pending);assert response.status_code==201,response.data
    assert not response.json['versions'][0]['creative_review']['eligible']
    assert c.post(qa,json={'render_sha256':job['render_sha256'],'checks':checks}).status_code==409
    body['expected_revision']=get(c,r)['revision']
    response=reviewer.post(review_url,json=body);assert response.status_code==201,response.data
    assert response.json['versions'][0]['creative_review']['eligible']
    assert c.get(root+f"/versions/{v['id']}/review-frames/0").data==frame.read_bytes()
    assert client(queue,4).get(root+f"/versions/{v['id']}/review-frames/0").status_code==404
    assert c.post(qa,json={'render_sha256':job['render_sha256'],'checks':checks}).status_code==200
    from datetime import datetime,timedelta,timezone
    channels=[{'platform':'instagram','integration_id':'ig','content':'fixture','scheduled_at_utc':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()}]
    release=c.put(url+'/release',json={'render_version':'mixed v1','channels':channels});assert release.status_code==200
    assert c.post(url+'/release/approve',json={'digest':release.json['digest']}).status_code==200
    assert get(c,r)['state']=='approved'
    if distribute_before_update:
        from test_media_release import FakePostiz
        import routes.media_jobs as routes
        fake=FakePostiz();monkeypatch.setattr(routes.PostizClient,'from_env',lambda:fake)
        fake.list_integrations=lambda:[{'id':'ig','identifier':'instagram'}]
        for _ in range(2):assert c.post(url+'/release/distribute').status_code==200
        assert fake.uploads==1 and len(fake.created)==len(fake.scheduled)==1
        assert get(c,r)['state']=='scheduled'
        body['expected_revision']=get(c,r)['revision']
        assert reviewer.post(review_url,json=body).status_code==409
        return
    with queue.app_context():
        release_row=m.db.session.get(m.MediaRelease,job['id']);release_row.busy=True;m.db.session.commit()
    body['expected_revision']=get(c,r)['revision']
    assert reviewer.post(review_url,json=body).status_code==409
    assert get(c,r)['versions'][0]['qa_valid'] is True
    with queue.app_context():
        release_row=m.db.session.get(m.MediaRelease,job['id']);release_row.busy=False;m.db.session.commit()
    # A new observation, or any re-edit, invalidates the final approval.
    body['expected_revision']=get(c,r)['revision']
    response=reviewer.post(review_url,json=body);assert response.status_code==201
    assert not response.json['versions'][0]['qa_valid'] and not response.json['versions'][0]['release']['approval_valid']
    assert c.post(url+'/release/distribute').status_code==409
    frame.write_bytes(b'changed-evidence')
    assert c.get(root+f"/versions/{v['id']}/review-frames/0").status_code==409
    body['expected_revision']=get(c,r)['revision']
    assert reviewer.post(review_url,json=body).status_code==400
    assert c.post(qa,json={'render_sha256':job['render_sha256'],'checks':checks}).status_code==409


@pytest.mark.parametrize('policy,has_audio,expected',[('silent',True,' muted'),('source',True,'data-has-audio="true"'),('source',False,' muted')])
def test_footage_audio_contract_is_explicit_and_offline(tmp_path,monkeypatch,policy,has_audio,expected):
    import video_project_render as renderer
    from recordings_storage import private_path,hash_file
    monkeypatch.setenv('MEDIA_WORKSPACE',str(tmp_path))
    raw=private_path('recordings/test.mp4');raw.parent.mkdir(parents=True);raw.write_bytes(b'contract fixture')
    asset={'id':'raw','kind':'video','path':'recordings/test.mp4','sha256':hash_file(raw)}
    value={**spec(),'entry_modes':['enriched_edit'],'audio_policy':policy,'scenes':[{'kind':'footage','duration':1,'title':'Original','asset_id':'raw','rights_reference':'Original test fixture'}]}
    value['captions']=[]
    normalized=normalize_project(value,{'raw':asset})
    monkeypatch.setattr(renderer,'extract_metadata',lambda path:SimpleNamespace(duration_seconds=2,has_audio=has_audio))
    renderer.build_composition({'production':normalized,'assets':[asset]},tmp_path/'project',width=320,height=568)
    html=(tmp_path/'project/index.html').read_text()
    assert expected in html and '</video>' in html and 'crossorigin' not in html


@pytest.mark.parametrize('policy',['source','provided'])
def test_missing_required_audio_never_becomes_silence(tmp_path,monkeypatch,policy):
    import video_project_render as renderer
    output=tmp_path/'output/final.mp4';output.parent.mkdir();output.write_bytes(b'fixture')
    work=tmp_path/'work';work.mkdir()
    monkeypatch.setattr(renderer,'build_composition',lambda *a,**k:work)
    monkeypatch.setattr(renderer,'_resolve_hyperframes_bin',lambda *a:'fixture-hyperframes')
    monkeypatch.setattr(renderer,'render_composition',lambda *a,**k:None)
    monkeypatch.setattr(renderer,'extract_metadata',lambda *a:SimpleNamespace(has_audio=False))
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(stdout='0.7.64')
    monkeypatch.setattr(renderer.subprocess,'run',run)
    with pytest.raises(ValueError,match='required_project_audio_missing'):
        renderer.render_project({'production':{'duration':1,'audio_policy':policy}},output,work)
    assert not any(call[0]=='ffmpeg' for call in calls)
