"""Local rough assembly of explicitly closed uploads; no model, transcript or publishing."""
import math
import subprocess
import time
from pathlib import Path
from recordings_storage import hash_file, private_path
from media_validation import extract_metadata
from recording_edits import video_trim, video_segments


class RecordingRenderError(ValueError): pass


def assemble_recording(snapshot, output, work, *, width=720, height=1280, timeout_seconds=1800):
    assets=snapshot.get('assets')
    if not isinstance(assets,list) or not assets:raise RecordingRenderError('lote fechado sem assets')
    output=Path(output);work=Path(work);work.mkdir(parents=True,exist_ok=True);output.parent.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();segments=[];time_map=[];cursor=0.0
    def run(command):
        remaining=timeout_seconds-(time.monotonic()-start)
        if remaining<=0:raise RecordingRenderError('montagem excedeu o limite')
        try: result=subprocess.run(command,capture_output=True,text=True,timeout=remaining)
        except (subprocess.TimeoutExpired,FileNotFoundError) as exc:raise RecordingRenderError(type(exc).__name__) from None
        if result.returncode:raise RecordingRenderError((result.stderr or '')[-1600:])
    expanded=[]
    for asset in assets:
        try: cuts=video_segments(asset.get('trim',{})) if asset.get('kind')=='video' else [None]
        except ValueError as exc:raise RecordingRenderError(str(exc)) from None
        if asset.get('kind')!='video' and 'trim' in asset:raise RecordingRenderError('corte exige vídeo')
        for cut in cuts:
            expanded.append({**asset,**({'trim':cut} if cut is not None else {})})
        if len(expanded)>200:raise RecordingRenderError('lote excedeu 200 segmentos')
    for index,asset in enumerate(expanded):
        source=private_path(asset['path'])
        if not source.is_file() or hash_file(source)!=asset.get('sha256'):raise RecordingRenderError('bruto mudou após fechar o lote')
        segment=work/f'{index:05d}.mp4'
        command=['ffmpeg','-nostdin','-y','-v','error','-threads','2']
        kind=asset.get('kind');source_start=0.0;source_end=None
        if 'trim' in asset and kind!='video':raise RecordingRenderError('corte exige vídeo')
        if kind=='image':
            duration=float(asset.get('photo_seconds',3))
            if not math.isfinite(duration) or not 1<=duration<=30:raise RecordingRenderError('duração de foto inválida')
            command+=['-loop','1','-i',str(source),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(duration),'-map','0:v:0','-map','1:a:0']
        elif kind=='audio':
            command+=['-f','lavfi','-i',f'color=c=black:s={width}x{height}:r=30','-i',str(source),'-map','0:v:0','-map','1:a:0','-shortest']
        elif kind=='video':
            meta=extract_metadata(source)
            try: trim=video_trim(asset.get('trim',{}))
            except ValueError as exc:raise RecordingRenderError(str(exc)) from None
            source_start=trim['start_seconds'];source_end=trim['end_seconds']
            if source_end is None:source_end=meta.duration_seconds
            if not math.isfinite(meta.duration_seconds) or not 0<=source_start<source_end<=meta.duration_seconds:
                raise RecordingRenderError('corte fora da duração do bruto')
            command+=['-ss',str(source_start),'-i',str(source)]
            if not meta.has_audio:command+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
            command+=['-map','0:v:0','-map','0:a:0' if meta.has_audio else '1:a:0','-t',str(source_end-source_start),'-shortest','-af','apad']
        else:raise RecordingRenderError('tipo de mídia não suportado')
        command+=['-vf',f'scale=trunc(iw*sar/2)*2:ih,setsar=1,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30',
                  '-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',str(segment)]
        run(command)
        meta=extract_metadata(segment)
        segments.append(segment)
        time_map.append({'asset_id':asset['id'],'source_start':source_start,'source_end':source_end if source_end is not None else meta.duration_seconds,
                         'edited_start':cursor,'edited_end':cursor+meta.duration_seconds})
        cursor+=meta.duration_seconds
    listing=work/'segments.txt';listing.write_text(''.join(f"file '{p.name}'\n" for p in segments))
    run(['ffmpeg','-nostdin','-y','-v','error','-f','concat','-safe','1','-i',str(listing),'-c','copy','-movflags','+faststart',str(output)])
    return {**snapshot,'assembly_time_map':time_map,'expected_duration':cursor,'stage':'rough_assembly',
            'time_map_kind':'rough_assembly_not_word_alignment','automatic_transcription':False,'captions_verified':False,'feedback_applied':False}
