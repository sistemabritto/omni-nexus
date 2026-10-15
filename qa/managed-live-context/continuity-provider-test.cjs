// Actual PR58 dispatcher + client-tool code, backend-produced JSON, fake provider.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const ts=require(process.env.TYPESCRIPT_MODULE || path.resolve('dashboard/frontend/node_modules/typescript'));
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const sent=[];let onMessage;
const fetch=async(url,options)=>({ok:true,json:async()=>url.endsWith('/read')?fixture.response:url.endsWith('/signed-session')?{signedUrl:'wss://fixture.invalid'}:url.endsWith('/conversation')?{bound:true}:fixture.context});
function load(file,requireImpl){const mod={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:mod.exports,module:mod,require:requireImpl,fetch,Error,JSON,Object,Set,console});return mod.exports}
const tools=load('dashboard/frontend/src/live/managed-context-client.ts',()=>{throw Error('unexpected import')});
const sessionModule=load('dashboard/frontend/src/live/managed-session.ts',name=>name==='./managed-context-client'?tools:name==='./audio'?{}:(()=>{throw Error('provider SDK must not load')})());
const connection={conversationId:'provider-b',addListener(){},onDisconnect(){},onMessage(cb){onMessage=cb},sendMessage(event){sent.push(event)},close(){}};
(async()=>{const session=new sessionModule.ManagedSession(async()=>connection);await session.start(7,'fixture A','agent-a');
 onMessage({type:'client_tool_call',client_tool_call:{tool_name:'read_current_omni_session',parameters:{},tool_call_id:'memory-proof'}});
 for(let n=0;n<8;n++)await new Promise(resolve=>setImmediate(resolve));
 const event=sent.find(e=>e.type==='client_tool_result');assert.ok(event);assert.equal(event.is_error,false);
 const context=JSON.parse(event.result);assert.equal(context.continuity.logicalConversationId,fixture.response.continuity.logicalConversationId);
 if(fixture.expectedWrittenReference)assert.ok(context.continuity.current.some(e=>e.reference===fixture.expectedWrittenReference && e.links.some(link=>link.url===fixture.expectedWrittenReference)));
 else if(fixture.expectedReference)assert.ok(context.previousWork.results.some(e=>e.reference===fixture.expectedReference));
 else assert.ok(context.continuity.current.some(e=>e.text.includes('terça')));assert.ok(!event.result.includes('SECRET B'));
 session.end();console.log('PASS actual Live dispatcher delivered persisted context in client_tool_result to mocked provider');
})().catch(error=>{console.error(error);process.exit(1)});
