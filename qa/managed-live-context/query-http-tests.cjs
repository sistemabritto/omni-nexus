// Actual local HTTP + Flask + SQLite + TS dispatcher. Socket/provider injected only.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const ts=require(process.env.TYPESCRIPT_MODULE||path.resolve('dashboard/frontend/node_modules/typescript'));
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),cache={},nativeFetch=global.fetch;
const requests=[];
async function fetch(url,options={}){
 if(url.endsWith('/signed-session'))return {ok:true,json:async()=>({signedUrl:'wss://fixture.invalid'})};
 requests.push({url,body:options.body?JSON.parse(options.body):null});
 return nativeFetch(fixture.base+url,{...options,headers:{...options.headers,Cookie:fixture.cookie,'X-Forwarded-Host':'example.test',Origin:'https://example.test'}});
}
function load(file){if(cache[file])return cache[file].exports;const module={exports:{}};cache[file]=module;
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module,exports:module.exports,require:name=>name==='./audio'?{}:load(path.resolve(path.dirname(file),name+'.ts')),fetch,crypto,Error,Number,JSON,Map,Set,setInterval:()=>1,clearInterval:()=>{},console});return module.exports;}
const {ManagedSession}=load(path.resolve('dashboard/frontend/src/live/managed-session.ts'));
const socket={conversationId:'query-http-provider',messages:[],addListener(){},onDisconnect(){},onMessage(fn){this.emit=fn},sendMessage(value){this.messages.push(value)},close(){}};
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
(async()=>{
 const session=new ManagedSession(async()=>socket);
 try{
  await session.start(7,'Company A fixture','agent-a');assert.equal(session.snapshot().phase,'connected');
  for(let n=0;n<100&&!requests.some(r=>r.url.endsWith('/tool-audit')&&r.body.stage==='instrumented');n++)await tick();
  assert(requests.some(r=>r.url.endsWith('/tool-audit')&&r.body.stage==='instrumented'));
  session.send('Zephyr');
  async function tool(name,parameters,id){socket.emit({type:'client_tool_call',client_tool_call:{tool_name:name,parameters,tool_call_id:id}});for(let n=0;n<400;n++){const m=socket.messages.find(m=>m.type==='client_tool_result'&&m.tool_call_id===id);if(m)return m;await tick()}throw Error('tool timeout')}
  const query=await tool('search_omni_context',{query:'Zephyr'},'query-http');assert.equal(query.is_error,false);
  const data=JSON.parse(query.result);assert.ok(data.work.results.some(x=>x.reference==='/api/tickets/ticket-3'));assert.ok(data.memory.some(x=>x.text==='Zephyr confirmado na terça'&&x.revision===2));assert.ok(!query.result.includes('SECRET'));assert.ok(!query.result.includes('obsolete'));
  const existing=await tool('read_current_omni_session',{},'existing-read');assert.equal(existing.is_error,false);assert.ok(JSON.parse(existing.result).queryResult.memory.some(x=>x.text==='Zephyr confirmado na terça'));
  const denied=await tool('search_omni_context',{query:'Zephyr',companyId:8},'tenant-injection');assert.equal(denied.is_error,true);
  const sourceIndex=requests.findIndex(r=>r.url.endsWith('/query'));
  const receivedIndex=requests.findIndex(r=>r.url.endsWith('/tool-audit')&&r.body.toolCallId==='query-http'&&r.body.stage==='received');
  const dispatchIndex=requests.findIndex(r=>r.url.endsWith('/tool-audit')&&r.body.toolCallId==='query-http'&&r.body.stage==='dispatch');
  assert(receivedIndex>=0&&receivedIndex<dispatchIndex&&dispatchIndex<sourceIndex);
  const auditRequest=requests[receivedIndex];
  const traceResponse=await fetch(auditRequest.url+'/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversationId:socket.conversationId,toolCallId:'query-http'})});
  assert(traceResponse.ok);const trace=await traceResponse.json();
  assert.deepEqual(trace.events.map(e=>e.stage),['received','dispatch','response','send_attempt','sent_to_sdk']);
  assert(!JSON.stringify(trace).includes('Zephyr'));assert(trace.deliveryEvidence.includes('not_provider_ack'));
  assert.equal(requests.filter(r=>r.url.endsWith('/query')).length,1);assert.ok(!requests.some(r=>r.url.endsWith('/tasks')));
  console.log('PASS actual HTTP scoped history+ticket query through real dispatcher and existing zero-argument read; no provider/harness call');
 }finally{session.end()}
})().catch(error=>{console.error(error);process.exit(1)});
