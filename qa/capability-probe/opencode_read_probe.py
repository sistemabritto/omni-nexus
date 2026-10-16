"""Actual installed OpenCode + local fake model transport; never paid inference.

Isolated config/cwd/env, pure mode, only native read permission. Captures the
schema actually sent by this binary, not an invented tools fixture.
"""
import hashlib,json,os,shutil,subprocess,tempfile,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

out=Path(__file__).resolve().parents[2]/'capability-probe-evidence';out.mkdir(exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='omni-opencode-read-'));source=root/'fixture.txt';source.write_text('OMNI_LOCAL_READ_PROOF_716\n')
requests=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  body=json.dumps({'object':'list','data':[{'id':'fixture','object':'model'}]}).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));requests.append(body)
  tool_messages=[m for m in body.get('messages',[]) if m.get('role')=='tool']
  tools=body.get('tools',[])
  read=next((t['function']['name'] for t in tools if t.get('function',{}).get('name')=='read'),None)
  if not tool_messages and read:
   delta={'role':'assistant','tool_calls':[{'index':0,'id':'fixture-read-1','type':'function','function':{'name':read,'arguments':json.dumps({'filePath':str(source)})}}]};finish='tool_calls'
  else:delta={'role':'assistant','content':'Leitura local concluída.'};finish='stop'
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
  for data in [{'id':'fixture','object':'chat.completion.chunk','created':1,'model':'fixture','choices':[{'index':0,'delta':delta,'finish_reason':None}]},{'id':'fixture','object':'chat.completion.chunk','created':1,'model':'fixture','choices':[{'index':0,'delta':{},'finish_reason':finish}],'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}}]:
   self.wfile.write(('data: '+json.dumps(data)+'\n\n').encode())
  self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
config={'provider':{'local-proof':{'npm':'@ai-sdk/openai-compatible','options':{'baseURL':f'http://127.0.0.1:{server.server_port}/v1','apiKey':'fixture-only'},'models':{'fixture':{'name':'fixture','limit':{'context':32000,'output':2000}}}}},'enabled_providers':['local-proof'],'model':'local-proof/fixture','small_model':'local-proof/fixture','plugin':[],'mcp':{},'instructions':[],'autoupdate':False,'share':'disabled','snapshot':False,'permission':{'*':'deny','read':'allow'},'tools':{'*':False,'read':True},'agent':{'build':{'steps':3,'permission':{'*':'deny','read':'allow'},'tools':{'*':False,'read':True}}}}
env={'PATH':os.environ['PATH'],'LANG':'C.UTF-8','XDG_CONFIG_HOME':str(root/'config'),'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),'XDG_STATE_HOME':str(root/'state'),'OPENCODE_CONFIG_CONTENT':json.dumps(config),'OPENCODE_DISABLE_MODELS_FETCH':'true'}
started=time.monotonic();binary=shutil.which('opencode');report={}
try:
 result=subprocess.run([binary,'--pure','run','Leia fixture.txt e reporte o marcador encontrado.','-m','local-proof/fixture','--format','json'],cwd=root,env=env,capture_output=True,text=True,timeout=60)
 tools=next((b['tools'] for b in requests if b.get('tools')),[])
 tool_messages=[m for b in requests for m in b.get('messages',[]) if m.get('role')=='tool']
 marker=any('OMNI_LOCAL_READ_PROOF_716' in json.dumps(m) for m in tool_messages)
 report={'binary_sha256':hashlib.sha256(Path(binary).read_bytes()).hexdigest(),'exit_code':result.returncode,'elapsed_seconds':round(time.monotonic()-started,2),'model_transport':'local_fake_no_paid_inference','tool_schemas_source':'captured_from_actual_binary_request','tools':tools,'request_count':len(requests),'real_native_read_result_observed_by_next_request':marker,'external_mcp_activated':False,'permission':'deny_all_except_read','stderr_tail':result.stderr[-1200:],'stdout_tail':result.stdout[-2500:]}
except subprocess.TimeoutExpired as exc:report={'error':'timeout','request_count':len(requests),'elapsed_seconds':time.monotonic()-started}
finally:server.shutdown();server.server_close()
(out/'opencode-read-proof.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('tools','stderr_tail','stdout_tail')}))
if not report.get('real_native_read_result_observed_by_next_request') or {t.get('function',{}).get('name') for t in report.get('tools',[])} != {'read'}:raise SystemExit(1)
