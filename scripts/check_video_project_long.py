import argparse,json,sys,os,time,resource
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dashboard/backend'))
from video_project_spec import normalize_project
from video_project_render import render_project,build_composition
from media_validation import validate_mp4
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
parser=argparse.ArgumentParser(description='Original10min technical fixture. Default prepares HTML only; --render explicitly starts local capture.')
parser.add_argument('--output',type=Path,required=True);parser.add_argument('--render',action='store_true');args=parser.parse_args()
root=args.output.resolve();root.mkdir(parents=True,exist_ok=True);os.environ['MEDIA_WORKSPACE']=str(root)
value={'entry_modes':['faceless','stickman','motion_vsl'],'script':'Fixture técnica original de dez minutos. Não é VSL comercial nem seleção semântica.','brand_reference':'fixture/original@1','audio_policy':'silent','scenes':[{'kind':'motion' if n%2==0 else 'stickman','duration':60,'title':f'Etapa {n+1} de 10','text':'Teste de duração e continuidade. Sem aprovação comercial.','pose':'wave'} for n in range(10)],'captions':[{'start':n*60,'end':n*60+10,'text':f'Fixture técnica • minuto {n+1}'} for n in range(10)]}
spec=normalize_project(value,{})
(root/'spec.json').write_text(json.dumps(spec,indent=2)+'\n')
if not args.render:
 build_composition({'production':spec,'assets':[]},root/'work/project',width=160,height=90)
 print('Prepared600s/18000frames at160x90; no render started. Coordinate resources before --render.');sys.exit(0)
started=time.monotonic()
try:
 result=render_project({'production':spec,'assets':[]},root/'preview.mp4',root/'work',width=160,height=90,timeout_seconds=1800)
 meta=validate_mp4(root/'preview.mp4',expected_width=160,expected_height=90,expected_fps=30,expected_duration_seconds=600,require_audio=True,workspace_root=root)
 report={'metadata':meta.to_dict(),'result':result,'elapsed_seconds':round(time.monotonic()-started,2),'maxrss_kib_parent_and_reaped_children':max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss),'limits':'1core,1worker,nice19;160x90 technical timeline only; CLI0.7.64 with existing local dependencies/Chrome131; no independent aesthetic/audio QA'}
 (root/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['metadata']),flush=True)
except Exception as exc:
 (root/'failure.json').write_text(json.dumps({'error':str(exc),'elapsed_seconds':time.monotonic()-started},indent=2));raise
