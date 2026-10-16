// Actual local HTTP + Flask + SQLite + TS dispatcher. Socket/provider injected only.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const ts=require(process.env.TYPESCRIPT_MODULE||path.resolve('dashboard/frontend/node_modules/typescript'));
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),cache={},nativeFetch=global.fetch;
const requests=[];
async function fetch(url,options={}){
 if(url.endsWith('/signed-session'))return {ok:true,json:async()=>({signedUrl:'wss://fixture.invalid'})};
 requests.push({url,body:options.body?JSON.parse(options.body):null});
 if(url.endsWith('/tool-audit')&&JSON.parse(options.body).stage===fixture.auditFailureStage){
  if(fixture.auditFailureMode==='timeout')return new Promise((_resolve,reject)=>{if(options.signal.aborted)reject(Error('aborted'));else options.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true})});
  return {ok:false,status:503,json:async()=>({error:'audit_unavailable'})};
 }
 return nativeFetch(fixture.base+url,{...options,headers:{...options.headers,Cookie:fixture.cookie,'X-Forwarded-Host':'example.test',Origin:'https://example.test'}});
}
function load(file){if(cache[file])return cache[file].exports;const module={exports:{}};cache[file]=module;
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module,exports:module.exports,require:name=>name==='./audio'?{}:load(path.resolve(path.dirname(file),name+'.ts')),fetch,crypto,Error,Number,JSON,Map,Set,setTimeout,clearTimeout,AbortController,setInterval:()=>1,clearInterval:()=>{},console});return module.exports;}
const {ManagedSession}=load(path.resolve('dashboard/frontend/src/live/managed-session.ts'));
const socket={conversationId:'query-http-provider',messages:[],addListener(){},onDisconnect(){},onMessage(fn){this.emit=fn},sendMessage(value){this.messages.push(value)},close(){}};
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
(async()=>{
 const session=new ManagedSession(async()=>socket);
 try{
  await session.start(7,'Company A fixture','agent-a');assert.equal(session.snapshot().phase,'connected');
  for(let n=0;n<100&&!requests.some(r=>r.url.endsWith('/tool-audit')&&r.body.stage==='instrumented');n++)await tick();
  assert(requests.some(r=>r.url.endsWith('/tool-audit')&&r.body.stage==='instrumented'));
  if(fixture.voiceFileLookup){
    const {safeWorkLink}=load(path.resolve('dashboard/frontend/src/live/continuity-session.ts'));
    const {isFileLookupRequest}=load(path.resolve('dashboard/frontend/src/live/file-lookup.ts'));
    assert.equal(isFileLookupRequest('Mostre o arquivo Zephyr roteiro'),true);assert.equal(isFileLookupRequest('Crie um roteiro'),false);
    socket.emit({type:'user_transcript',user_transcription_event:{user_transcript:'Mostre o arquivo Zephyr roteiro'}});
    for(let n=0;n<1000&&!session.snapshot().continuity?.events.some(e=>e.links?.some(l=>l.url.startsWith('/api/live/file-results/')));n++)await tick();
    const results=session.snapshot().continuity.events.filter(e=>e.kind==='result');assert.equal(results.length,1);
    const link=results[0].links[0].url;assert.equal(safeWorkLink(link),link);assert.ok(results[0].text.includes('Zephyr roteiro aprovado'));
    assert.ok(!JSON.stringify(results).includes('SECRET unbound file'));
    const response=await fetch(link);assert.equal(response.status,200);assert.ok((await response.text()).includes('Zephyr roteiro aprovado'));
    assert.equal((await nativeFetch(fixture.base+link)).status,401);
    assert.equal(socket.messages.filter(m=>m.type==='client_tool_result').length,0); // no provider tool call was needed
    const queries=requests.filter(r=>r.url.endsWith('/query')).length;
    socket.emit({type:'agent_response',agent_response_event:{agent_response:'Mostre o arquivo Zephyr roteiro'}});
    await new Promise(resolve=>setTimeout(resolve,100));assert.equal(requests.filter(r=>r.url.endsWith('/query')).length,queries);
    assert.equal(socket.messages.filter(m=>m.type==='contextual_update').length,1); // bootstrap only, no extra model input
    assert.equal(safeWorkLink('https://external.invalid/file'),null);
    console.log('PASS actual HTTP voice file receipt; authenticated link, source ACL, no remote model invocation');return;
  }
  session.send('Zephyr');
  async function tool(name,parameters,id){socket.emit({type:'client_tool_call',client_tool_call:{tool_name:name,parameters,tool_call_id:id}});for(let n=0;n<400;n++){const m=socket.messages.find(m=>m.type==='client_tool_result'&&m.tool_call_id===id);if(m)return m;await tick()}throw Error('tool timeout')}
  const query=await tool('search_omni_context',{query:'Zephyr'},'query-http');assert.equal(query.is_error,false);
  const data=JSON.parse(query.result);assert.ok(data.work.results.some(x=>x.reference==='/api/tickets/ticket-3'));assert.ok(data.memory.some(x=>x.text==='Zephyr confirmado na terça'&&x.revision===2));assert.ok(!query.result.includes('SECRET'));assert.ok(!query.result.includes('obsolete'));
  if(fixture.auditFailureStage)assert.equal(session.snapshot().toolAuditDegraded,true);
  const existing=await tool('read_current_omni_session',{},'existing-read');assert.equal(existing.is_error,false);assert.ok(JSON.parse(existing.result).queryResult.memory.some(x=>x.text==='Zephyr confirmado na terça'));
  if(fixture.expectedProfileName)assert.deepEqual(JSON.parse(existing.result).authenticatedUser,{displayName:fixture.expectedProfileName,nameAvailable:true,source:'authenticated_profile'});
  if(fixture.expectedFile){
    for(const files of [data.files,JSON.parse(existing.result).queryResult.files]){
      assert.equal(files.results.length,1);assert.equal(files.results[0].path,fixture.expectedFile.path);
      assert.equal(files.results[0].sha256,fixture.expectedFile.sha256);assert.equal(files.results[0].revision,1);
      assert.equal(files.source,'explicit_workspace_files');assert.ok(files.results[0].text.includes('Zephyr roteiro aprovado'));
    }
    assert.ok(!existing.result.includes('SECRET unbound file'));
  }
  const denied=await tool('search_omni_context',{query:'Zephyr',companyId:8},'tenant-injection');assert.equal(denied.is_error,true);
  const sourceIndex=requests.findIndex(r=>r.url.endsWith('/query'));
  const receivedIndex=requests.findIndex(r=>r.url.endsWith('/tool-audit')&&r.body.toolCallId==='query-http'&&r.body.stage==='received');
  const dispatchIndex=requests.findIndex(r=>r.url.endsWith('/tool-audit')&&r.body.toolCallId==='query-http'&&r.body.stage==='dispatch');
  assert(receivedIndex>=0&&receivedIndex<dispatchIndex&&dispatchIndex<sourceIndex);
  const auditRequest=requests[receivedIndex];
  const traceResponse=await fetch(auditRequest.url+'/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversationId:socket.conversationId,toolCallId:'query-http'})});
  assert(traceResponse.ok);const trace=await traceResponse.json();
  assert.deepEqual(trace.events.map(e=>e.stage),['received','dispatch','response','send_attempt','sent_to_sdk'].filter(stage=>stage!==fixture.auditFailureStage));
  assert(!JSON.stringify(trace).includes('Zephyr'));assert(trace.deliveryEvidence.includes('not_provider_ack'));
  assert.equal(requests.filter(r=>r.url.endsWith('/query')).length,1);assert.ok(!requests.some(r=>r.url.endsWith('/tasks')));
  console.log('PASS actual HTTP scoped history+ticket query through real dispatcher and existing zero-argument read; no provider/harness call');
 }finally{session.end()}
})().catch(error=>{console.error(error);process.exit(1)});
