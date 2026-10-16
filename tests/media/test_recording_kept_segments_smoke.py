"""Tiny opt-in local render: no user media, paid API or network."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import math
import pytest
from recording_render import assemble_recording
from recordings_storage import private_path, hash_file
from media_validation import validate_mp4


@pytest.mark.skipif(os.environ.get('RECORDING_SEGMENTS_SMOKE')!='1',reason='explicit local resource window required')
def test_real_internal_cuts_from_two_synthetic_raws(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDIA_WORKSPACE',str(tmp_path))
    def ffmpeg(*args):
        return subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-threads','1','-filter_threads','1','-filter_complex_threads','1',*map(str,args)],check=True,capture_output=True,timeout=45).stdout
    voiced=private_path('recordings/voiced.mp4');voiced.parent.mkdir(parents=True)
    silent=private_path('recordings/silent.mp4')
    ffmpeg('-f','lavfi','-i','color=red:s=160x120:r=30:d=0.5','-f','lavfi','-i','color=lime:s=160x120:r=30:d=0.5',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1',
        '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0,split=2[v][silent]',
        '-map','[v]','-map','2:a','-t',1,'-c:v','libx264','-threads',1,'-pix_fmt','yuv420p','-c:a','aac',voiced,
        '-map','[silent]','-an','-t',1,'-c:v','libx264','-threads',1,'-pix_fmt','yuv420p',silent)
    assets=[{'id':'voiced','kind':'video','path':'recordings/voiced.mp4','sha256':hash_file(voiced),
        'trim':{'keep_segments':[{'start_seconds':.1,'end_seconds':.3},{'start_seconds':.6,'end_seconds':.8}]}},
        {'id':'silent','kind':'video','path':'recordings/silent.mp4','sha256':hash_file(silent),
         'trim':{'start_seconds':.1,'end_seconds':.3}}]
    output=tmp_path/'preview.mp4';result=assemble_recording({'assets':assets,'edit_plan_version':2},output,tmp_path/'work',width=160,height=240,timeout_seconds=45)
    meta=validate_mp4(output,expected_width=160,expected_height=240,expected_fps=30,expected_duration_seconds=.6,require_audio=True,workspace_root=tmp_path)
    assert abs(meta.duration_seconds-.6)<.12
    mapping=result['assembly_time_map']
    assert [(x['asset_id'],x['source_start'],x['source_end']) for x in mapping]==[('voiced',.1,.3),('voiced',.6,.8),('silent',.1,.3)]
    pixels=[]
    for at in (.1,.3,.5):
        pixels.append(list(ffmpeg('-ss',at,'-i',output,'-frames:v',1,'-vf','crop=2:2:80:120,scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1')))
    assert pixels[0][0]>200 and pixels[1][1]>200 and pixels[2][0]>200
    pcm=ffmpeg('-i',output,'-vn','-ac',1,'-ar',48000,'-f','s16le','pipe:1');samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
    def rms(a,b):
        values=samples[int(a*48000):int(b*48000)]
        return math.sqrt(sum(x*x for x in values)/len(values))
    levels=[rms(.06,.15),rms(.26,.35),rms(.48,.56)]
    assert levels[0]>300 and levels[1]>300 and levels[2]<100
    evidence={'render_count':1,'synthetic_only':True,'duration_seconds':meta.duration_seconds,
        'expected_seconds':.6,'time_map':mapping,'pixels_rgb':pixels,'rms':levels,'sha256':hash_file(output)}
    directory=os.environ.get('RECORDING_SEGMENTS_EVIDENCE')
    if directory:
        dest=Path(directory);dest.mkdir(parents=True,exist_ok=True)
        (dest/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n');shutil.copyfile(output,dest/'preview.mp4')
    print(json.dumps(evidence))
