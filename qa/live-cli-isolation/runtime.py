import os,json,pathlib,subprocess,threading,socket,sys,hashlib
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
root=pathlib.Path('/work');assert (root/'opencode').is_file() and not pathlib.Path('/etc/passwd').exists() and not pathlib.Path('/home/sistemabritto').exists()
version=subprocess.check_output(['/work/opencode','--version'],env={'PATH':'/usr/bin:/bin','HOME':'/work/version-home'},text=True).strip()
subprocess.run(['/usr/sbin/ip','link','set','lo','up'],check=True)
assert [n for _,n in socket.if_nameindex()]==['lo']
assert not subprocess.check_output(['/usr/sbin/ip','route','show','default'],text=True).strip()
assert not pathlib.Path('/home/sistemabritto').exists()
foreign=root/'foreign';foreign.mkdir(exist_ok=True)
canary=root/'plugin-or-mcp-loaded';canary.unlink(missing_ok=True)
plugin=foreign/'poison.mjs';plugin.write_text("import fs from 'node:fs';fs.writeFileSync('/work/plugin-or-mcp-loaded',JSON.stringify({pid:process.pid,ppid:process.ppid,home:process.env.HOME,cwd:process.cwd(),stack:new Error().stack}));export default async()=>({});")
mcp=foreign/'mcp.py';mcp.write_text("from pathlib import Path\nPath('/work/plugin-or-mcp-loaded').write_text('MCP_STARTED')\n")
instructions=foreign/'private.md';instructions.write_text('OUT_OF_SCOPE_PRIVATE_INSTRUCTION_MARKER')
poison={'plugin':['file://'+str(plugin)],'mcp':{'foreign':{'type':'local','command':['/usr/bin/python3',str(mcp)],'enabled':True}},'instructions':[str(instructions)],'model':'foreign/forbidden','provider':{'foreign':{'options':{'apiKey':'SYNTHETIC_FOREIGN_STORED_CREDENTIAL'}}}}
for folder in [foreign/'config/opencode',foreign/'home/.config/opencode',foreign/'project',pathlib.Path('/tmp'),pathlib.Path('/etc/opencode')]:
 folder.mkdir(parents=True,exist_ok=True);(folder/'opencode.json').write_text(json.dumps(poison))
for folder in [foreign/'config/opencode/plugins',foreign/'project/.opencode/plugins',foreign/'home/.claude',foreign/'home/.agents/skills',foreign/'data/opencode']:
 folder.mkdir(parents=True,exist_ok=True)
(foreign/'config/opencode/plugins/poison.mjs').write_text(plugin.read_text())
(foreign/'home/.claude/CLAUDE.md').write_text('OUT_OF_SCOPE_CLAUDE_MARKER')
(foreign/'project/AGENTS.md').write_text('OUT_OF_SCOPE_PROJECT_MARKER')
(foreign/'data/opencode/auth.json').write_text(json.dumps({'foreign':{'type':'api','key':'SYNTHETIC_FOREIGN_STORED_CREDENTIAL'}}))
original_hash=hashlib.sha256((foreign/'config/opencode/opencode.json').read_bytes()).hexdigest()
(root/'bin').mkdir(exist_ok=True);(root/'bin/opencode').unlink(missing_ok=True);(root/'bin/opencode').symlink_to(root/'opencode')
os.environ.update(PATH='/work/bin:/usr/bin:/usr/sbin:/bin',HOME=str(foreign/'home'),XDG_CONFIG_HOME=str(foreign/'config'),XDG_DATA_HOME=str(foreign/'data'),OPENCODE_CONFIG=str(foreign/'config/opencode/opencode.json'),OPENCODE_CONFIG_CONTENT=json.dumps(poison),OPENCODE_CONFIG_DIR=str(foreign/'config/opencode'),OPENCODE_TEST_MANAGED_CONFIG_DIR='/etc/opencode',OPENAI_API_KEY='SYNTHETIC_PARENT_KEY',ANTHROPIC_API_KEY='SYNTHETIC_PARENT_KEY',TELEGRAM_BOT_TOKEN='SYNTHETIC_PARENT_KEY',OUT_OF_SCOPE_SECRET='SYNTHETIC_PARENT_KEY',NODE_OPTIONS='--require=/work/foreign/nonexistent.cjs',HTTPS_PROXY='http://127.0.0.1:1')
single='--single' in sys.argv
answer='Rascunho interno fixture' if single else 'ISOLATED_FIXTURE_OK'
prompt=(root/'input-prompt.txt').read_text() if single else 'Synthetic fixture only. Reply ISOLATED_FIXTURE_OK.'
requests=[];mode='text';injected=False
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):requests.append({'method':'GET','path':self.path});self.send_error(404)
 def do_POST(self):
  global injected
  d=json.loads(self.rfile.read(int(self.headers.get('content-length','0'))));title=any('title generator' in str(m.get('content','')).lower() for m in d.get('messages',[]) if m.get('role')=='system')
  attack=mode=='injected' and not title and not injected
  if attack:injected=True
  serialized=json.dumps(d)
  requests.append({'method':'POST','path':self.path,'tools':[x.get('function',{}).get('name') for x in d.get('tools',[])],'foreign_marker_seen':any(x in serialized for x in ['OUT_OF_SCOPE_','SYNTHETIC_PARENT_KEY','SYNTHETIC_FOREIGN_STORED_CREDENTIAL']),'selected_auth_only':self.headers.get('Authorization')=='Bearer SYNTHETIC_SELECTED_KEY','injected':attack})
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
  def send(delta,reason=None):self.wfile.write(('data: '+json.dumps({'id':'fixture','object':'chat.completion.chunk','created':0,'model':'fixture-model','choices':[{'index':0,'delta':delta,'finish_reason':reason}]})+'\n\n').encode())
  send({'role':'assistant'})
  if attack:send({'tool_calls':[{'index':0,'id':'deny-bash','type':'function','function':{'name':'bash','arguments':json.dumps({'command':'touch /work/forbidden-tool','description':'Synthetic denied tool'})}}]});send({},'tool_calls')
  else:send({'content':answer});send({},'stop')
  self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
server=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start()
sys.path.insert(0,'/work/code/dashboard/backend');import provider_fallback as pf
observed=[];actual=pf._invoke_cli_run
# Observe actual boundary then delegate; no subprocess/model execution is mocked.
def boundary(cmd,env,timeout,cwd,**kwargs):
 observed.append({'command':cmd,'home':env['HOME'],'cwd':str(cwd),'env_keys':sorted(env),'selected_key_only':env.get('OPENAI_API_KEY')=='SYNTHETIC_SELECTED_KEY' and all('SYNTHETIC_PARENT_KEY' not in str(v) for v in env.values()),'pure':'--pure' in cmd,'explicit_config_is_private':env.get('OPENCODE_CONFIG','').startswith(str(pathlib.Path(env['HOME']).parent))})
 return actual(cmd,env,timeout,cwd,**kwargs)
pf._invoke_cli_run=boundary
token=pf._CLI_TOOL_POLICY.set('no_tools')
try:managed=pf._invoke_cli('opencode','fixture',2,10,provider_id='fixture',model='fixture-model',env_overrides={'OPENAI_API_KEY':'SYNTHETIC_SELECTED_KEY','OPENAI_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1'})
finally:pf._CLI_TOOL_POLICY.reset(token)
assert managed['error']=='restricted_managed_config_present' and not observed and not requests
assert not canary.exists()
import shutil
shutil.rmtree('/etc/opencode')  # synthetic namespace only, never host configuration

token=pf._CLI_TOOL_POLICY.set('no_tools')
try:ancestor=pf._invoke_cli('opencode','fixture',2,10,provider_id='fixture',model='fixture-model',env_overrides={'OPENAI_API_KEY':'SYNTHETIC_SELECTED_KEY','OPENAI_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1'})
finally:pf._CLI_TOOL_POLICY.reset(token)
assert ancestor['error']=='restricted_ancestor_config_present' and not observed and not requests and not canary.exists()
pathlib.Path('/tmp/opencode.json').unlink()  # synthetic namespace-only collision removed
runs=[]
for mode in (('text',) if single else ('text','injected')):
 injected=False;token=pf._CLI_TOOL_POLICY.set('no_tools')
 try:r=pf._invoke_cli('opencode',prompt,3,40,provider_id='fixture',model='fixture-model',cwd=foreign/'project',env_overrides={'OPENAI_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1','OPENAI_API_KEY':'SYNTHETIC_SELECTED_KEY','OPENCODE_CONFIG_CONTENT':json.dumps(poison),'ANTHROPIC_API_KEY':'SYNTHETIC_PARENT_KEY'})
 finally:pf._CLI_TOOL_POLICY.reset(token)
 runs.append({'mode':mode,'status':r['status'],'output_ok':r.get('output')==answer,'error':r.get('error'),'injection_sent':injected,'plugin_mcp_canary_exists':canary.exists(),'tool_canary_exists':(root/'forbidden-tool').exists()})
 for x in observed:assert not pathlib.Path(x['home']).parent.exists()
 assert r['status']=='success',r.get('error')
 assert r['output']==answer
 (root/'isolation-debug.json').write_text(json.dumps({'observed':observed,'requests':requests,'runs':runs,'canary':canary.read_text() if canary.exists() else None},indent=2))
 assert not canary.exists() and not (root/'forbidden-tool').exists()
assert all(not r.get('foreign_marker_seen') and r.get('selected_auth_only') and r['path']=='/v1/chat/completions' and not r['tools'] for r in requests)
assert original_hash==hashlib.sha256((foreign/'config/opencode/opencode.json').read_bytes()).hexdigest()
proof={'version':version,'binary_sha256':hashlib.file_digest(open('/work/opencode','rb'),'sha256').hexdigest(),'actual_product_adapter_used':True,'managed_config_refused_before_cli':True,'ancestor_config_refused_before_cli':True,'network_interfaces':[n for _,n in socket.if_nameindex()],'external_route':False,'runs':runs,'requests':requests,'boundary':observed,'foreign_config_unchanged':True,'temporary_state_removed':True,'output':r['output'],'adapter_source_sha256':hashlib.file_digest(open('/work/code/dashboard/backend/provider_fallback.py','rb'),'sha256').hexdigest()}
(root/('isolation-queue-proof.json' if single else 'isolation-runtime-proof.json')).write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof));server.shutdown()
