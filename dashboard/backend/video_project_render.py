"""Offline HyperFrames/WAAPI composer: no model, network, stock library or asset spend."""
from html import escape
import json
from pathlib import Path
import shutil
import subprocess

from recordings_storage import private_path, hash_file
from media_validation import extract_metadata
from media_render import render_composition, _resolve_hyperframes_bin, RenderError


def build_composition(snapshot, project, *, width, height):
    spec=snapshot['production'];project=Path(project);project.mkdir(parents=True,exist_ok=True)
    media=project/'assets';media.mkdir(exist_ok=True);paths={};assets={asset['id']:asset for asset in snapshot['assets']}
    used={scene[key] for scene in spec['scenes'] for key in ('asset_id','overlay_asset_id') if key in scene}
    if spec.get('audio_upload_id'):used.add(spec['audio_upload_id'])
    for key in used:
        asset=assets[key];source=private_path(asset['path'])
        if not source.is_file() or hash_file(source)!=asset['sha256']:raise ValueError('project_source_changed')
        name=key+source.suffix;shutil.copyfile(source,media/name);paths[key]='assets/'+name
    elements=[];animations=[]
    for index,scene in enumerate(spec['scenes']):
        sid=f'scene-{index}';start=scene['start'];duration=scene['duration'];timing=f'data-start="{start}" data-duration="{duration}"'
        if scene['kind'] in ('footage','image'):
            asset=assets[scene['asset_id']];source=private_path(asset['path'])
            if scene['kind']=='footage':
                meta=extract_metadata(source)
                if scene['source_start']+duration>meta.duration_seconds+.001:raise ValueError('scene_outside_source_duration')
            tag='video' if scene['kind']=='footage' else 'img'
            attrs=(f' data-media-start="{scene.get("source_start",0)}" data-volume="{1 if spec["audio_policy"]=="source" else 0}"'+(' data-has-audio="true"' if spec['audio_policy']=='source' and meta.has_audio else ' muted')) if tag=='video' else ''
            grade={'none':'none','warm':'sepia(.15) saturate(1.08)','cool':'saturate(.9) hue-rotate(8deg)'}[scene['grade']]
            elements.append(f'<{tag} id="{sid}-media" class="clip media" {timing} src="{escape(paths[scene["asset_id"]])}"{attrs} style="object-fit:{scene["frame"]};filter:{grade}">{"</video>" if tag=="video" else ""}')
        figure=''
        if scene['kind']=='stickman':
            figure=f'<svg class="figure" viewBox="0 0 200 200" aria-label="Boneco palito"><g stroke="currentColor" stroke-width="7" fill="none" stroke-linecap="round"><circle cx="100" cy="40" r="22"/><path d="M100 62 V125 M100 125 L65 180 M100 125 L135 180 M100 80 L55 110"/><g id="{sid}-arm"><path d="M100 80 L145 40"/></g></g></svg>'
            animations.append({'id':sid+'-arm','start':start,'duration':duration,'type':'wave' if scene['pose']=='wave' else 'move'})
        if 'metric' in scene:
            figure+=f'<div class="chart"><div id="{sid}-bar" class="bar" style="width:{scene["metric"]}%"></div><strong>{scene["metric"]:g}%</strong></div>'
            animations.append({'id':sid+'-bar','start':start,'duration':min(duration,.8),'type':'bar'})
        overlay=f'<img class="overlay" src="{escape(paths[scene["overlay_asset_id"]])}">' if 'overlay_asset_id' in scene else ''
        copy=''
        if scene.get('show_title',scene['kind'] not in ('footage','image')):
            backed=' backed' if scene['kind'] in ('footage','image') else ''
            copy=f'<div id="{sid}-copy" class="copy{backed}"><h1>{escape(scene["title"])}</h1><p>{escape(scene["text"])}</p></div>'
            animations.append({'id':sid+'-copy','start':start,'duration':min(duration,.5),'type':'enter'})
        elements.append(f'<section id="{sid}" class="clip scene" {timing}>{copy}{figure}{overlay}</section>')
    for index,caption in enumerate(spec['captions']):
        elements.append(f'<div id="caption-{index}" class="clip caption" data-start="{caption["start"]}" data-duration="{caption["end"]-caption["start"]}" data-track-index="3">{escape(caption["text"])}</div>')
    if spec.get('audio_upload_id'):
        elements.append(f'<audio id="narration" class="clip" data-start="0" data-duration="{spec["duration"]}" src="{escape(paths[spec["audio_upload_id"]])}"></audio>')
    palette=spec['palette']
    html=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Prévia do projeto</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:{palette['background']};color:{palette['foreground']};font-family:sans-serif}}#root{{position:relative;width:100%;height:100%;overflow:hidden;background:{palette['background']}}}.clip{{position:absolute;inset:0}}.media{{width:100%;height:100%}}.scene{{padding:8%;}}.copy{{position:absolute;top:9%;left:8%;width:84%;text-shadow:0 2px 4px #000}}.backed{{background:{palette['background']};padding:3%}}h1{{font-size:{width*.063}px;line-height:1.12;margin:0 0 5%}}p{{font-size:{width*.038}px;line-height:1.3;margin:0;white-space:pre-wrap}}.figure{{position:absolute;top:38%;left:24%;width:52%;height:40%;color:{palette['accent']}}}.figure g[id$="-arm"]{{transform-box:fill-box;transform-origin:left bottom}}.chart{{position:absolute;left:10%;top:55%;width:80%;font-size:{width*.05}px}}.bar{{height:{height*.04}px;background:{palette['accent']};transform-origin:left}}.overlay{{position:absolute;right:8%;bottom:22%;width:28%;height:22%;object-fit:contain}}.caption{{inset:auto 8% 10%;padding:2%;background:#000;color:#fff;text-align:center;font-size:{width*.043}px;line-height:1.25}}</style></head><body>
<div id="root" data-composition-id="main" data-no-timeline data-start="0" data-width="{width}" data-height="{height}" data-duration="{spec['duration']}">{''.join(elements)}</div>
<script>const effects={json.dumps(animations)};for(const e of effects){{const node=document.getElementById(e.id);let frames=e.type==='bar'?[{{transform:'scaleX(0)'}},{{transform:'scaleX(1)'}}]:e.type==='wave'?[{{transform:'rotate(-12deg)'}},{{transform:'rotate(12deg)'}},{{transform:'rotate(-12deg)'}}]:e.type==='move'?[{{transform:'translateX(-8px)'}},{{transform:'translateX(8px)'}}]:[{{opacity:0,transform:'translateY(18px)'}},{{opacity:1,transform:'translateY(0)'}}];node.animate(frames,{{duration:e.duration*1000,delay:e.start*1000,fill:'both',iterations:1,easing:'ease-out'}}).pause();}}</script></body></html>'''
    (project/'index.html').write_text(html)
    return project


def render_project(snapshot,output,work,*,width=720,height=1280,timeout_seconds=1800):
    project=build_composition(snapshot,Path(work)/'project',width=width,height=height)
    runtime=subprocess.run([_resolve_hyperframes_bin(project),'--version'],check=True,capture_output=True,text=True,timeout=20).stdout.strip()
    try:render_composition(project,output,fps=30,quality='standard',timeout_seconds=timeout_seconds,strict=True,workers=1)
    except RenderError as exc:
        (Path(work)/'hyperframes-render.log').write_text(exc.log)
        raise
    meta=extract_metadata(output)
    if not meta.has_audio:
        # Explicit silence policy still produces a standard audio stream for common validation.
        silent=Path(output).with_name('with-audio.mp4')
        subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(output),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-t',str(snapshot['production']['duration']),str(silent)],check=True,capture_output=True,timeout=timeout_seconds)
        silent.replace(output)
    checksum=hash_file(Path(output));frames=[]
    for index,fraction in enumerate((.15,.5,.85)):
        at=snapshot['production']['duration']*fraction;frame=Path(output).parent/f'review-frame-{index}.png'
        subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-threads','1','-ss',str(at),'-i',str(output),'-frames:v','1',str(frame)],check=True,capture_output=True,timeout=60)
        frames.append({'ref':'output/'+frame.name,'sha256':hash_file(frame),'at':at})
    return {**snapshot,'engine':{'name':'hyperframes','version':runtime,'animation':'WAAPI','workers':1},'review_evidence':{'render_sha256':checksum,'frames':frames},'expected_duration':snapshot['production']['duration'],'stage':'project_preview','creative_review_required':True,'automatic_transcription':False,'feedback_applied':False}
