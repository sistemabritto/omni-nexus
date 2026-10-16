"""Capture actual Codex request schemas with local fake Responses API; no model."""
import hashlib,json,os,shutil,subprocess,tempfile,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
out=Path(__file__).resolve().parents[2]/'capability-probe-evidence';out.mkdir(exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='omni-codex-schema-'));captures=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));captures.append(data.get('tools',[]))
  msg={'type':'message','id':'msg_fixture','role':'assistant','status':'completed','content':[{'type':'output_text','text':'Fixture local de schema.','annotations':[]}]}
  response={'id':'resp_fixture','object':'response','created_at':1,'model':'fixture','status':'completed','output':[msg],'usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0}}
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
  for event in [{'type':'response.created','response':{**response,'status':'in_progress','output':[]}},{'type':'response.output_item.added','output_index':0,'item':{**msg,'content':[]}},{'type':'response.content_part.added','item_id':'msg_fixture','output_index':0,'content_index':0,'part':{'type':'output_text','text':'','annotations':[]}},{'type':'response.output_text.delta','item_id':'msg_fixture','output_index':0,'content_index':0,'delta':'Fixture local de schema.'},{'type':'response.output_item.done','output_index':0,'item':msg},{'type':'response.completed','response':response}]:
   self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode())
  self.wfile.flush()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
binary=shutil.which('codex');started=time.monotonic()
args=[binary,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','read-only','-C',str(root),'-c','model_provider="local-proof"','-c','model="fixture"','-c','analytics.enabled=false','-c','model_providers.local-proof.name="Local fixture"','-c',f'model_providers.local-proof.base_url="http://127.0.0.1:{server.server_port}/v1"','-c','model_providers.local-proof.wire_api="responses"','-c','model_providers.local-proof.requires_openai_auth=false','-c','model_providers.local-proof.request_max_retries=0','-c','model_providers.local-proof.stream_max_retries=0','--json','Responda apenas à fixture local; não execute nenhuma ferramenta.']
env={'PATH':os.environ['PATH'],'LANG':'C.UTF-8'}
try:
 r=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=45)
 report={'binary_sha256':hashlib.sha256(Path(binary).read_bytes()).hexdigest(),'exit_code':r.returncode,'elapsed_seconds':round(time.monotonic()-started,2),'model_transport':'local_fake_no_paid_inference','schema_source':'captured_from_actual_binary_request','tools':captures[0] if captures else [],'request_count':len(captures),'tool_execution':'not_requested_or_proven','upstream_real_model':'not_called','sandbox':'read-only','user_config':'ignored_for_this_process','external_mcp_activation':'not_attested','external_tool_calls':0,'eligible_for_scoped_read_only':False,'no_tools_isolation_proven':False,'stderr_tail':r.stderr[-1200:]}
except subprocess.TimeoutExpired:report={'error':'timeout','request_count':len(captures),'tools':captures[0] if captures else []}
finally:server.shutdown();server.server_close()
(out/'codex-schema-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('tools','stderr_tail')}))
if not report.get('tools'):raise SystemExit(1)
