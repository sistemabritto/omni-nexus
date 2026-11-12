// Real localhost Flask API + SQLite worker; injected socket/provider, never a real harness.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const ts=require(process.env.TYPESCRIPT_MODULE||path.resolve('dashboard/frontend/node_modules/typescript'));
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),cache={},nativeFetch=global.fetch;
async function fetch(url,options={}){
 if(url.endsWith('/signed-session'))return {ok:true,json:async()=>({signedUrl:'wss://fixture.invalid'})};
 return nativeFetch(fixture.base+url,{...options,headers:{...options.headers,Cookie:fixture.cookie,'X-Forwarded-Host':'example.test',Origin:'https://example.test'}});
}
function load(file){if(cache[file])return cache[file].exports;const module={exports:{}};cache[file]=module;
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module,exports:module.exports,require:name=>name==='./audio'?{}:load(path.resolve(path.dirname(file),name+'.ts')),fetch,crypto,Error,Number,JSON,Map,Set,setInterval:()=>1,clearInterval:()=>{},console});return module.exports;}
const {ManagedSession}=load(path.resolve('dashboard/frontend/src/live/managed-session.ts'));
const socket={conversationId:'provider-http-fixture',messages:[],addListener(){},onDisconnect(){},onMessage(fn){this.emit=fn},sendMessage(value){this.messages.push(value)},close(){}};
const tick=()=>new Promise(resolve=>setTimeout(resolve,25));
(async()=>{
 const session=new ManagedSession(async()=>socket);
 try{
  await session.start(7,'Company A fixture','agent-a');assert.equal(session.snapshot().phase,'connected');
  async function tool(name,parameters,id){const before=socket.messages.filter(m=>m.type==='client_tool_result'&&m.tool_call_id===id).length;socket.emit({type:'client_tool_call',client_tool_call:{tool_name:name,parameters,tool_call_id:id}});for(let n=0;n<200;n++){const matches=socket.messages.filter(m=>m.type==='client_tool_result'&&m.tool_call_id===id);if(matches.length>before)return matches.at(-1);await tick()}throw Error('tool timeout')}
  const first=await tool('request_internal_task',{ticketId:'ticket-a',operation:'draft_ticket'},'stable-http-id');assert.equal(first.is_error,false);const job=JSON.parse(first.result).jobId;assert(job);
  const duplicate=await tool('request_internal_task',{ticketId:'ticket-a',operation:'draft_ticket'},'stable-http-id');assert.equal(duplicate.is_error,false);assert.equal(JSON.parse(duplicate.result).jobId,job);assert.equal(JSON.parse(duplicate.result).replayed,true);
  const contextRequest=socket.messages.find(m=>m.type==='contextual_update');assert(contextRequest);
  const status=await tool('read_internal_task_status',{jobId:job},'status-http-id');assert.equal(status.is_error,false);assert.equal(JSON.parse(status.result).status,'success');
  assert(session.snapshot().messages.some(m=>m.author==='Tarefa interna'&&m.text.includes(job)));
  assert(session.snapshot().continuity.events.some(e=>e.kind==='result'&&e.text.includes('Rascunho interno fixture')&&e.links.some(l=>l.url==='/api/live/tasks/'+job)));
  assert(!JSON.stringify(session.snapshot()).includes('SECRET B'));
  console.log('PASS actual localhost API/context/queue/worker/result in chat; provider and socket injected, no real harness');
 }finally{session.end()}
})().catch(error=>{console.error(error);process.exit(1)});
