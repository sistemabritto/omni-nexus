"""One tiny real preview; generated sources only, Postiz strictly in memory."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from test_recordings import queue, client, create, finish, get  # noqa: F401


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='local codecs required')
def test_single_real_trim_preview_binding_and_mock_schedule(queue, monkeypatch, tmp_path):
    import models as m
    from media_validation import extract_metadata
    from media_workspace import job_dir

    def ffmpeg(*args):
        return subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-threads','1','-filter_threads','1',
                               *map(str,args)],check=True,capture_output=True,timeout=45).stdout

    frames=tmp_path/'frames';frames.mkdir()
    for index in range(30):
        pixel=bytes([255,0,0] if index<15 else [0,255,0])
        (frames/f'{index:03d}.ppm').write_bytes(b'P6\n160 120\n255\n'+pixel*(160*120))
    reuse=os.environ.get('RECORDING_SMOKE_REUSE_DIR')
    voiced=Path(reuse)/'voiced.mp4' if reuse else tmp_path/'voiced.mp4'
    silent=Path(reuse)/'silent.mp4' if reuse else tmp_path/'silent.mp4'
    if not reuse:ffmpeg('-framerate',30,'-i',frames/'%03d.ppm','-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
           '-map','0:v:0','-map','1:a:0','-t',1,'-c:v','libx264','-threads',1,'-pix_fmt','yuv420p','-c:a','aac',voiced,
           '-map','0:v:0','-an','-t',1,'-c:v','libx264','-threads',1,'-pix_fmt','yuv420p',silent)
    c=client(queue);r=create(c);root=f"/api/recordings/{r['id']}";uploads=[]
    for index,path in enumerate((voiced,silent)):
        binary=path.read_bytes()
        response=c.post(root+'/uploads',json={'client_key':path.stem,'name':path.name,'position':index,'size':len(binary)})
        assert response.status_code==201,response.data
        uploads.append(response.json);finish(c,r,response.json,binary)
    cuts={uploads[0]['id']:{'start_seconds':0.6,'end_seconds':0.9},
          uploads[1]['id']:{'start_seconds':0.1,'end_seconds':0.4}}
    closed=c.post(root+'/close',json={'expected_revision':get(c,r)['revision'],
                                    'upload_ids':[u['id'] for u in uploads],'edits':cuts})
    assert closed.status_code==201,closed.data
    version=closed.json['versions'][0];job_id=version['job']['id'];url='/api/media/jobs/'+job_id
    # Isolated in-memory test DB only: reduce render cost while exercising the actual worker.
    with queue.app_context():
        job=m.db.session.get(m.MediaJob,job_id);job.width=160;job.height=240;m.db.session.commit()
    claim=c.post(url+'/run',json={'recording_batch':'v1'});assert claim.status_code==200,claim.data
    spec=importlib.util.spec_from_file_location('tiny_real_trim_worker',Path(__file__).resolve().parents[2]/'media_worker/worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    def patch(job_id,**fields):
        response=c.patch('/api/media/jobs/'+job_id,json=fields)
        assert response.status_code==200,response.data
        return response.json
    monkeypatch.setattr(worker,'_patch',patch)
    monkeypatch.setattr(worker,'run_opencode_media_job',lambda *a,**k:pytest.fail('model forbidden'))
    if reuse:
        # Resume contract checks after a test-assertion failure without another render.
        cached_jobs=list((Path(reuse)/'media/jobs').iterdir())
        assert len(cached_jobs)==1
        cached=cached_jobs[0]
        def reuse_preview(snapshot,output,work,**kwargs):
            assert [asset['trim'] for asset in snapshot['assets']]==[{'start_seconds':.6,'end_seconds':.9},{'start_seconds':.1,'end_seconds':.4}]
            output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(cached/'output/final.mp4',output)
            mapping=[];cursor=0.0
            for index,asset in enumerate(snapshot['assets']):
                duration=extract_metadata(cached/f'work/{index:05d}.mp4').duration_seconds
                mapping.append({'asset_id':asset['id'],'source_start':asset['trim']['start_seconds'],
                    'source_end':asset['trim']['end_seconds'],'edited_start':cursor,'edited_end':cursor+duration})
                cursor+=duration
            return {**snapshot,'assembly_time_map':mapping,'expected_duration':cursor,'feedback_applied':False}
        monkeypatch.setattr(worker,'assemble_recording',reuse_preview)
    worker.process_job(claim.json)
    ready=get(c,r);job=ready['versions'][0]['job']
    assert job['status']=='ready_for_review',job
    output=job_dir(job_id)/'output/final.mp4';meta=extract_metadata(output)
    assert abs(meta.duration_seconds-0.6)<0.12 and meta.has_audio
    result=job['result'];time_map=result['assembly_time_map']
    assert [(item['source_start'],item['source_end']) for item in time_map]==[(0.6,0.9),(0.1,0.4)]
    def pixel(at):
        return list(ffmpeg('-ss',at,'-i',output,'-frames:v',1,'-vf','crop=2:2:80:120,scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'))
    green,red=pixel(0.15),pixel(0.45)
    assert green[1]>green[0]+100 and red[0]>red[1]+100
    pcm=ffmpeg('-i',output,'-vn','-ac',1,'-ar',48000,'-f','s16le','pipe:1')
    samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
    def rms(start,end):
        portion=samples[int(start*48000):int(end*48000)]
        return math.sqrt(sum(sample*sample for sample in portion)/len(portion))
    voiced_rms,silent_rms=rms(.06,.22),rms(.4,.55)
    assert voiced_rms>300 and silent_rms<100
    rendered_hash=hashlib.sha256(output.read_bytes()).hexdigest()
    assert job['render_sha256']==rendered_hash
    assert c.get(url+'/video').data==output.read_bytes()
    checks={key:True for key in ('audio','captions','face','safe_zones','rights')}
    qa=root+f"/versions/{version['id']}/qa"
    assert c.post(qa,json={'render_sha256':'a'*64,'checks':checks}).status_code==409
    assert c.post(qa,json={'render_sha256':rendered_hash,'checks':checks}).status_code==200
    channels=[{'platform':platform,'integration_id':key,'content':'Synthetic fixture only',
               'scheduled_at_utc':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()}
              for platform,key in [('instagram','ig'),('linkedin','li')]]
    release=c.put(url+'/release',json={'render_version':'synthetic v1','channels':channels})
    assert release.status_code==200,release.data
    assert release.json['snapshot']['binding']['render_sha256']==rendered_hash
    assert c.post(url+'/release/approve',json={'digest':release.json['digest']}).status_code==200
    class FakePostiz:
        def __init__(self):self.posts={};self.created=[];self.uploads=0;self.scheduled=[]
        def list_integrations(self):return [{'id':'ig','identifier':'instagram'},{'id':'li','identifier':'linkedin'}]
        def upload_file(self,path):self.uploads+=1;return {'id':'fixture','path':'https://invalid.example/fixture.mp4'}
        def create_draft(self,**kwargs):
            key=kwargs['integration_id'];self.created.append(key)
            self.posts[key]={'id':key,'state':'DRAFT','content':kwargs['content'],'publishDate':kwargs['now_iso_utc'],'integration':{'id':key}}
            return [{'postId':key}]
        def change_status(self,post_id,status):self.scheduled.append(post_id);self.posts[post_id]['state']='QUEUE'
        def list_posts(self,window):return list(self.posts.values())
    fake=FakePostiz();import routes.media_jobs as routes
    monkeypatch.setattr(routes.PostizClient,'from_env',lambda:fake)
    for _ in range(2):assert c.post(url+'/release/distribute').status_code==200
    assert fake.uploads==1 and sorted(fake.created)==['ig','li'] and sorted(fake.scheduled)==['ig','li']
    assert get(c,r)['state']=='scheduled'
    # Reopening invalidates the approved version before any new preview/render is needed.
    reopened=c.post(root+'/reopen',json={'expected_revision':get(c,r)['revision']});assert reopened.status_code==200
    assert c.post(qa,json={'render_sha256':rendered_hash,'checks':checks}).status_code==409
    assert c.post(url+'/release/distribute').status_code==409
    next_version=c.post(root+'/close',json={'expected_revision':reopened.json['revision'],
        'upload_ids':[u['id'] for u in uploads],'edits':{uploads[0]['id']:{'start_seconds':.5,'end_seconds':.9}}})
    assert next_version.status_code==201 and not next_version.json['versions'][0]['qa_valid']
    assert next_version.json['versions'][1]['snapshot']==version['snapshot']
    assert fake.uploads==1 and len(fake.created)==len(fake.scheduled)==2
    evidence={'fixture_only':True,'render_count':1,'reused_existing_render_for_contract_resume':bool(reuse),'dimensions':[meta.width,meta.height],
        'duration_seconds':meta.duration_seconds,'expected_duration':.6,'has_audio':meta.has_audio,
        'time_map':time_map,'pixels_rgb':{'edited_.15':green,'edited_.45':red},
        'rms':{'voiced':voiced_rms,'silent':silent_rms},'render_sha256':rendered_hash,
        'version_id':version['id'],'approved_digest':release.json['digest'],
        'mock_postiz':{'uploads':fake.uploads,'created':fake.created,'scheduled':fake.scheduled},
        'old_approval_blocked_after_reopen':True,'new_version_requires_qa':True}
    destination=os.environ.get('RECORDING_SMOKE_EVIDENCE_DIR')
    if destination:
        directory=Path(destination);directory.mkdir(parents=True,exist_ok=True)
        (directory/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
        shutil.copyfile(output,directory/'synthetic-preview.mp4')
    print(json.dumps(evidence,sort_keys=True))
