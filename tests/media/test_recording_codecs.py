"""Real local codec probes; synthetic files only, no accounts/providers/production."""
import json
import shutil
import subprocess
import struct
import math
import pytest
from recording_render import assemble_recording, RecordingRenderError
from recordings_storage import private_path, hash_file
from media_validation import validate_mp4

pytestmark=pytest.mark.skipif(not shutil.which('ffmpeg'),reason='local FFmpeg required')


def ffmpeg(*args):
    subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-threads','1',*map(str,args)],check=True,capture_output=True,timeout=40)


def probe(path):
    return json.loads(subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],check=True,capture_output=True,timeout=10).stdout)


@pytest.fixture
def folder(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDIA_WORKSPACE',str(tmp_path))
    path=private_path('recordings/1/local-codecs/source.mp4');path.parent.mkdir(parents=True)
    return path.parent


def assemble(folder,source,kind='video'):
    asset={'id':'local-codec','path':str(source.relative_to(folder.parents[2])),'kind':kind,'sha256':hash_file(source)}
    output=folder/'render/final.mp4'
    result=assemble_recording({'assets':[asset]},output,folder/'work',width=160,height=240,timeout_seconds=40)
    meta=validate_mp4(output,expected_width=160,expected_height=240,expected_duration_seconds=result['expected_duration'],expected_fps=30,require_audio=True,workspace_root=folder.parents[2])
    return output,meta


def pixel(path,x,y,at=.2):
    return subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(path),'-frames:v','1','-vf',f'crop=2:2:{x}:{y},scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,capture_output=True,timeout=10).stdout


def test_short_audio_must_not_truncate_longer_video(folder):
    source=folder/'short-audio.mp4'
    ffmpeg('-f','lavfi','-i','color=red:s=160x120:r=30:d=1.4','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=0.2','-c:v','libx264','-c:a','aac',source)
    output,meta=assemble(folder,source)
    assert meta.duration_seconds>=1.3,'short source audio truncated the picture'
    assert pixel(output,80,120,at=1.2)[0]>150
    def rms(at):
        pcm=subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(output),'-t','0.1','-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'],check=True,capture_output=True,timeout=10).stdout
        values=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
        return math.sqrt(sum(v*v for v in values)/len(values))
    assert rms(.05)>200  # original tone stays at its original time
    assert rms(1.1)<30   # padding is silence, not stretched speech


def test_anamorphic_display_aspect_is_preserved(folder):
    source=folder/'wide-pixels.mp4'
    ffmpeg('-f','lavfi','-i','color=red:s=160x120:r=30:d=0.6','-vf','setsar=2','-c:v','libx264',source)
    output,_=assemble(folder,source)
    # Display is 320x120, therefore 160x60 centered at y=90..150, not 160x120.
    assert max(pixel(output,80,70))<20,'sample aspect ratio was discarded before display normalization'
    assert pixel(output,80,120)[0]>150


@pytest.mark.parametrize('container,codec,pix_fmt,audio',[('mov','libx265','yuv420p10le','aac'),('webm','libvpx-vp9','yuv420p','libopus')])
def test_mobile_hevc10_and_webm_vp9_opus(folder,container,codec,pix_fmt,audio):
    source=folder/('mobile.'+container)
    options=['-f','lavfi','-i','color=green:s=160x120:r=24:d=0.7','-f','lavfi','-i','sine=frequency=440:sample_rate=44100:duration=0.7','-c:v',codec,'-pix_fmt',pix_fmt,'-c:a',audio]
    if codec=='libx265':options+=['-x265-params','pools=1:frame-threads=1:log-level=error','-tag:v','hvc1']
    ffmpeg(*options,source)
    output,meta=assemble(folder,source)
    streams=probe(output)['streams'];video=next(s for s in streams if s['codec_type']=='video');sound=next(s for s in streams if s['codec_type']=='audio')
    assert video['codec_name']=='h264' and video['pix_fmt']=='yuv420p'
    assert video['sample_aspect_ratio']=='1:1' and sound['codec_name']=='aac'
    assert sound['sample_rate']=='48000' and sound['channels']==2
    assert .6<=meta.duration_seconds<=1.0


def test_mov_rotation_is_applied_once(folder):
    base=folder/'landscape.mp4';source=folder/'rotated.mov'
    ffmpeg('-f','lavfi','-i','color=red:s=160x80:r=30:d=0.6','-c:v','libx264',base)
    # Patch only this synthetic ISO-BMFF track matrix. Works on FFmpeg 5/6,
    # unlike fixture creation with the FFmpeg-6-only -display_rotation option.
    payload=bytearray(base.read_bytes());track=payload.index(b'tkhd')
    assert payload[track+4]==0  # version-0 track header
    payload[track+44:track+80]=struct.pack('>9i',0,-65536,0,65536,0,0,0,0,1073741824)
    source.write_bytes(payload)
    assert any(abs(s.get('rotation',0))==90 for s in probe(source)['streams'][0].get('side_data_list',[]))
    output,_=assemble(folder,source)
    assert max(pixel(output,4,120))<20  # portrait picture has side bars
    assert pixel(output,80,30)[0]>150  # full-height portrait, no second rotation
    assert all(s.get('rotation',0)==0 for s in probe(output)['streams'][0].get('side_data_list',[]))


def test_variable_frame_rate_becomes_constant_30fps(folder):
    source=folder/'vfr.mp4'
    ffmpeg('-f','lavfi','-i','testsrc2=s=160x120:r=30:d=1.2','-vf',"select='if(lt(n,12),not(mod(n,2)),1)'",'-fps_mode','vfr','-c:v','libx264',source)
    output,meta=assemble(folder,source)
    video=next(s for s in probe(output)['streams'] if s['codec_type']=='video')
    assert video['avg_frame_rate']=='30/1' and meta.fps==30
    assert 1.1<=meta.duration_seconds<=1.4


def test_audio_only_aac_mono_gets_finite_black_preview(folder):
    source=folder/'voice.m4a'
    ffmpeg('-f','lavfi','-i','sine=frequency=440:sample_rate=44100:duration=0.5','-c:a','aac','-ac','1',source)
    output,meta=assemble(folder,source,'audio')
    assert .4<=meta.duration_seconds<=1.0
    assert max(pixel(output,80,120))<20
