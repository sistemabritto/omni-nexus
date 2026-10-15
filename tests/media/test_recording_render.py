"""Actual local FFmpeg smoke test: ordered still/video/audio, zero paid/media APIs."""
import shutil
import subprocess
import pytest
from recording_render import assemble_recording, RecordingRenderError
from recordings_storage import private_path, hash_file
from media_validation import validate_mp4

@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg required for local render smoke')
def test_real_ffmpeg_preserves_order_audio_and_normalizes(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDIA_WORKSPACE',str(tmp_path))
    def ffmpeg(*args):
        subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-threads','1',*map(str,args)],check=True,capture_output=True)
    video=private_path('recordings/1/reel/video.mp4');video.parent.mkdir(parents=True)
    ffmpeg('-f','lavfi','-i','color=red:s=160x120:r=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',video)
    # PPM uses no optional Pillow; input image format is local test-only, not an upload extension.
    image=video.parent/'blue.ppm';image.write_bytes(b'P6\n16 16\n255\n'+bytes([0,0,255])*256)
    audio=video.parent/'voice.wav';ffmpeg('-f','lavfi','-i','sine=frequency=880:sample_rate=48000','-t','0.5',audio)
    assets=[{'id':name,'kind':kind,'path':str(path.relative_to(tmp_path)),'sha256':hash_file(path),'photo_seconds':1}
            for name,kind,path in [('blue','image',image),('red','video',video),('voice','audio',audio)]]
    output=tmp_path/'jobs/preview.mp4'
    result=assemble_recording({'assets':assets},output,tmp_path/'work',width=160,height=240,timeout_seconds=60)
    meta=validate_mp4(output,expected_width=160,expected_height=240,expected_fps=30,expected_duration_seconds=result['expected_duration'],require_audio=True,workspace_root=tmp_path)
    assert 2.4<meta.duration_seconds<3.2
    assert [part['asset_id'] for part in result['assembly_time_map']]==['blue','red','voice']
    assert result['time_map_kind']=='rough_assembly_not_word_alignment'
    assert result['automatic_transcription'] is False and result['feedback_applied'] is False
    # Sample actual center pixels: concat order must be blue then red, no crop.
    def pixel(at):
        return subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(output),'-frames:v','1','-vf','crop=2:2:80:120,scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,capture_output=True).stdout
    blue,red=pixel(.4),pixel(1.4)
    assert blue[2]>blue[0]+100
    assert red[0]>red[2]+100
    video.write_bytes(b'changed')
    with pytest.raises(RecordingRenderError,match='mudou'):
        assemble_recording({'assets':assets},tmp_path/'other.mp4',tmp_path/'other',width=160,height=240)


def test_storage_path_cannot_escape(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDIA_WORKSPACE',str(tmp_path))
    with pytest.raises(ValueError):private_path('recordings/../../outside')
