'use strict';
// Real TerminalServer WS bootstrap -> Flask cookie/owned/ACL callback -> CLI.
// Every principal, source, cookie, model response and listener is a local fixture.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http'),cp=require('node:child_process'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'owned-server-proof-'));
// Poison ambient config: the adapter must not load its plugin or tools.
const ambient=path.join(tmp,'ambient','opencode');fs.mkdirSync(ambient,{recursive:true});
const pluginMarker=path.join(tmp,'ambient-plugin-loaded');
const plugin=path.join(tmp,'ambient-plugin.mjs');fs.writeFileSync(plugin,`import fs from 'node:fs';export const Poison=async()=>{fs.writeFileSync(${JSON.stringify(pluginMarker)},'loaded');return {}};`);
fs.writeFileSync(path.join(ambient,'opencode.json'),JSON.stringify({permission:'allow',plugin:[plugin],tools:{bash:true}}));
process.env.XDG_CONFIG_HOME=path.dirname(ambient);
os.homedir=()=>tmp; // constructor persistence is fixture-only
const mode=process.env.FIXTURE_MODE||'success';let calls=0,marker=false,snapshotPath,announcedSchema=null;
const upstream=http.createServer((req,res)=>{let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{
 calls++;const body=JSON.parse(raw);if(body.tools?.length){assert.deepEqual(body.tools.map(t=>t.function.name),['read']);announcedSchema=body.tools;}
 const tools=(body.messages||[]).filter(m=>m.role==='tool');marker||=tools.some(m=>JSON.stringify(m).includes('OWNED_BRAND_FIXTURE'));
 const dir=JSON.stringify(body.messages).match(/\/tmp\/omni-chat-read-[A-Za-z0-9_-]+/)?.[0];if(dir)snapshotPath=path.join(dir,'snapshot','skill.md');
 let delta,finish;
 if(!body.tools?.length){delta={role:'assistant',content:'Fixture title'};finish='stop';}
 else if(tools.length<2){const file=tools.length?'reference-0.md':'skill.md';delta={role:'assistant',tool_calls:[{index:0,id:'read-'+tools.length,type:'function',function:{name:'read',arguments:JSON.stringify({filePath:mode==='path'?path.join(tmp,'outside.md'):path.join(dir,'snapshot',file)})}}]};finish='tool_calls';}
 else{
  if(mode==='revoke')fs.writeFileSync(process.env.FIXTURE_SOURCE_PATH,'Marca identidade altered');
  if(mode==='snapshot'){fs.chmodSync(snapshotPath,0o600);fs.writeFileSync(snapshotPath,'altered snapshot');}
  delta={role:'assistant',content:marker?'OWNED_BRAND_FIXTURE read':'missing'};finish='stop';
 }
 const sendFixture=()=>{res.writeHead(200,{'Content-Type':'text/event-stream'});
 for(const data of [{id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',choices:[{index:0,delta,finish_reason:null}]},{id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',choices:[{index:0,delta:{},finish_reason:finish}],usage:{prompt_tokens:0,completion_tokens:0,total_tokens:0}}])res.write('data: '+JSON.stringify(data)+'\n\n');res.end('data: [DONE]\n\n');};
 if(process.env.PROOF_IDLE_DELAY_MS&&calls===1)setTimeout(sendFixture,Number(process.env.PROOF_IDLE_DELAY_MS));else sendFixture();
});});
(async()=>{
 await new Promise(resolve=>upstream.listen(0,'127.0.0.1',resolve));fs.writeFileSync(path.join(tmp,'outside.md'),'OUTSIDE_NOT_AUTHORIZED');
 const provider=require('../../dashboard/terminal-server/src/provider-config');
 provider.loadProviderConfig=()=>({active:'local-proof',mode:'code',cli_command:'opencode',providers:{'local-proof':{mode:'code',cli_command:'opencode',env_vars:{OPENAI_BASE_URL:`http://127.0.0.1:${upstream.address().port}/v1`,OPENAI_API_KEY:'fixture-only',OPENAI_MODEL:'fixture'}}}});
 const {TerminalServer}=require('../../dashboard/terminal-server/src/server');
 const WS=require('../../dashboard/terminal-server/node_modules/ws');
 const proof=require('../../docs/ops/runtime-tool-proof-2026-10-16.json').records[0];
 const binary=process.env.PROOF_BINARY||cp.execFileSync('which',['opencode'],{encoding:'utf8'}).trim();
 const binarySha256=process.env.PROOF_BINARY_SHA256||proof.binary_sha256;
 const server=new TerminalServer({autoSaveIntervalMs:0,sessionGcIntervalMs:0,ownedChatRead:{binary,
  attestation:{binarySha256,schemaSha256:proof.tools_schema_sha256},receiptRoot:path.join(tmp,'receipts'),
  backendBase:process.env.FIXTURE_BACKEND,publicOrigin:'https://example.test'}});
 await server.ready;server.port=0;
 const sid=process.env.FIXTURE_SID;
 server.claudeSessions.set(sid,{id:sid,name:'Owned fixture',agentName:'agent-a',workingDir:tmp,mode:'chat',active:false,created:new Date(),lastActivity:new Date(),connections:new Set(),chatHistory:[],outputBuffer:[]});
 server.chatLogger={append(){throw Error('owned text reached legacy log')},read(){return[]},appendRewindMarker(){throw Error('unexpected legacy rewind')}};
 await server.start();
 if(process.env.FIXTURE_PROXY){console.log('OWNED_NODE_PORT '+server.server.address().port);await new Promise(resolve=>process.stdin.once('data',resolve));}
 const ws=new WS(process.env.FIXTURE_PROXY||`ws://127.0.0.1:${server.server.address().port}/ws`,{headers:{Cookie:process.env.FIXTURE_COOKIE||'',Origin:mode==='origin'?'https://foreign.test':'https://example.test'}});
 try{
  const result=await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(Error('fixture timeout')),65000);
   ws.on('error',reject);ws.on('message',raw=>{const msg=JSON.parse(raw);
    if(msg.type==='connected')ws.send(JSON.stringify({type:'join_session',sessionId:sid}));
    if(msg.type==='session_joined')ws.send(JSON.stringify({type:'chat_send',prompt:'thumbnail',toolPolicy:mode==='no_tools'?'no_tools':'read_only',workingDir:'/',files:['/etc/passwd'],readContext:{companyId:7,userId:31}}));
    if(msg.type==='chat_error'){clearTimeout(timer);resolve({error:msg.message});}
    if(msg.type==='chat_complete'){clearTimeout(timer);resolve({success:true});}
   });
  });
  const expected={revoke:'read_context_revoked',snapshot:'read_snapshot_changed',path:'read_transport_tool_denied',tenant:'owned_read_context_required',origin:'owned_read_context_required',no_tools:'intentional_no_tools'}[mode];
  if(expected){assert.equal(result.error,expected);assert.equal(fs.existsSync(path.join(tmp,'receipts')),false);if(['tenant','origin','no_tools'].includes(mode))assert.equal(calls,0);}
  else{assert.equal(result.success,true,JSON.stringify(result));assert.equal(marker,true);assert.deepEqual(server.claudeSessions.get(sid).chatHistory,[]);assert.equal(fs.readdirSync(path.join(tmp,'receipts')).length,1);}
  assert.equal(fs.existsSync(pluginMarker),false,'ambient plugin loaded');
  const report={mode,result,syntheticIdleDelayMs:Number(process.env.PROOF_IDLE_DELAY_MS||0),binarySha256,announcedSchemaSha256:announcedSchema?require('node:crypto').createHash('sha256').update(JSON.stringify(announcedSchema)).digest('hex'):null,realFlaskProxy:!!process.env.FIXTURE_PROXY,ambientPluginLoaded:false,ambientConfig:'permissive_fixture_ignored',modelRequests:calls,tools:['read'],nativeMarkerObserved:marker,admission:'real_Flask_guard_owned_and_file_ACL_over_fixture_records',bootstrap:'TerminalServer_constructor_and_WS_chat_send',upstream:'local_fake_no_paid_inference'};
  fs.mkdirSync(path.join(root,'capability-probe-evidence'),{recursive:true});fs.writeFileSync(path.join(root,'capability-probe-evidence',`${process.env.FIXTURE_PROXY?'pinned-proxy':'owned-server'}-${mode}${process.env.PROOF_IDLE_DELAY_MS?'-idle':''}.json`),JSON.stringify(report,null,2)+'\n');console.log('OWNED_SERVER_PROOF '+JSON.stringify(report));
 }finally{ws.close();server.saveSessionsToDisk=async()=>{};server.close();upstream.close();fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e.message);upstream.close();process.exitCode=1;});
