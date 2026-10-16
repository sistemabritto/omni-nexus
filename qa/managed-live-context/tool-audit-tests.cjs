// Actual metadata dispatcher, synthetic callbacks; no provider, microphone or payload logging.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const ts=require(process.env.TYPESCRIPT_MODULE||path.resolve('dashboard/frontend/node_modules/typescript'));
const moduleUnderTest={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/live/tool-dispatch-audit.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module:moduleUnderTest,exports:moduleUnderTest.exports,Map,Set,JSON,Error});
const {AuditedToolDispatcher}=moduleUnderTest.exports;
const call={tool_name:'read_current_omni_session',tool_call_id:'call-1',parameters:{}};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 let stages=[],sent=[],dispatches=0,warnings=0;
 const persist=async(id,name,stage)=>{stages.push({id,name,stage})};
 let d=new AuditedToolDispatcher(persist,async()=>{},async()=>{dispatches++;assert(stages.some(x=>x.stage==='received'));assert(stages.some(x=>x.stage==='dispatch'));return 'PRIVATE RESULT'},x=>sent.push(x),()=>true,()=>warnings++);
 await Promise.all([d.handle(call),d.handle(call)]);
 assert.equal(dispatches,1);assert.equal(sent.length,2);assert(sent.every(x=>x.result==='PRIVATE RESULT'));assert(stages.some(x=>x.stage==='duplicate'));assert(stages.some(x=>x.stage==='sent_to_sdk'));assert(!JSON.stringify(stages).includes('PRIVATE'));
 await d.handle({...call,parameters:{companyId:8}});assert.equal(dispatches,1);assert.equal(sent.at(-1).is_error,true);
 // Cancellation after source response started: never send late private data.
 stages=[];sent=[];let release;
 d=new AuditedToolDispatcher(persist,async()=>{},()=>new Promise(resolve=>release=resolve),x=>sent.push(x),()=>true,()=>warnings++);
 const pending=d.handle(call);while(!release)await tick();d.close();release('PRIVATE CANCELLED');await pending;await tick();assert.equal(sent.length,0);assert(stages.some(x=>x.stage==='cancelled'));assert(!stages.some(x=>x.stage==='sent_to_sdk'));
 // Cancellation before readiness prevents target invocation entirely.
 stages=[];let ready,executed=0;
 d=new AuditedToolDispatcher(persist,()=>new Promise(resolve=>ready=resolve),async()=>{executed++;return 'x'},()=>{},()=>true,()=>warnings++);
 const before=d.handle(call);while(!ready)await tick();d.close();ready();await before;assert.equal(executed,0);assert(!stages.some(x=>x.stage==='dispatch'));
 // HTTP success and SDK send failure must NOT claim SDK delivery.
 stages=[];d=new AuditedToolDispatcher(persist,async()=>{},async()=>'x',()=>{throw Error('PRIVATE exception')},()=>true,()=>warnings++);await d.handle(call);assert(stages.some(x=>x.stage==='response'));assert(stages.some(x=>x.stage==='send_error'));assert(!stages.some(x=>x.stage==='sent_to_sdk'));assert(!JSON.stringify(stages).includes('PRIVATE'));
 stages=[];sent=[];d=new AuditedToolDispatcher(persist,async()=>{},async()=>{throw Error('PRIVATE backend exception')},x=>sent.push(x),()=>true,()=>warnings++);await d.handle(call);assert(stages.some(x=>x.stage==='error'));assert(sent[0].is_error);assert(!sent[0].result.includes('PRIVATE'));
 // Missing durable receipt: fail closed before source HTTP, return generic error.
 executed=0;sent=[];d=new AuditedToolDispatcher(async()=>{throw Error('audit down')},async()=>{},async()=>{executed++;return 'x'},x=>sent.push(x),()=>true,()=>warnings++);await d.handle(call);assert.equal(executed,0);assert(sent[0].is_error);assert(warnings>0);
 let bounded=0;const capSent=[];const capped=new AuditedToolDispatcher(async()=>{},async()=>{},async()=>{bounded++;return 'x'},x=>capSent.push(x),()=>true,()=>{});
 for(let n=0;n<257;n++)await capped.handle({...call,tool_call_id:'cap-'+n});assert.equal(bounded,256);assert.equal(capSent.at(-1).is_error,true);
 console.log('PASS metadata trace ordering, duplicate single dispatch/replay, conflicting ID denial, cancellation, source error, SDK send error, audit failure closed; no payload persistence');
})().catch(error=>{console.error(error);process.exit(1)});
