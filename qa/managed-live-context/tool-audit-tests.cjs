// Actual metadata dispatcher, synthetic callbacks; no provider, microphone or payload logging.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const ts=require(process.env.TYPESCRIPT_MODULE||path.resolve('dashboard/frontend/node_modules/typescript'));
const moduleUnderTest={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/live/tool-dispatch-audit.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module:moduleUnderTest,exports:moduleUnderTest.exports,Map,Set,JSON,Error,setTimeout,clearTimeout,AbortController});
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
 // Audit rejection must never block source execution or successful SDK output.
 executed=0;sent=[];d=new AuditedToolDispatcher(async()=>{throw Error('audit down')},async()=>{},async()=>{executed++;return 'x'},x=>sent.push(x),()=>true,()=>warnings++);await d.handle(call);assert.equal(executed,1);assert.equal(sent[0].is_error,false);assert.equal(sent[0].result,'x');assert(warnings>0);
 for(const mode of ['reject','timeout'])for(const stage of ['received','dispatch','response','error','send_attempt','sent_to_sdk','send_error','duplicate','cancelled']){
  let ran=0,notified=0;const output=[];let finish,failedSignal;
  const audit=async(_id,_name,value,signal)=>{if(value===stage){failedSignal=signal;if(mode==='reject')throw Error('audit failure');return new Promise(()=>{})}};
  const failingSource=stage==='error',failingSdk=stage==='send_error';
  const instance=new AuditedToolDispatcher(audit,async()=>{},async()=>{ran++;if(failingSource)throw Error('PRIVATE source');if(stage==='cancelled')return new Promise(resolve=>finish=resolve);return 'PRIVATE obtained result'},value=>{if(failingSdk)throw Error('PRIVATE sdk');output.push(value)},()=>true,()=>notified++,5);
  const request=instance.handle(call);
  if(stage==='cancelled'){while(!finish)await tick();instance.close();finish('PRIVATE late');await request;assert.equal(output.length,0)}
  else {await request;if(stage==='duplicate')await instance.handle(call);if(!failingSdk){assert.equal(output[0].is_error,failingSource);if(!failingSource)assert.equal(output[0].result,'PRIVATE obtained result')}}
  assert.equal(ran,1,mode+' '+stage+' must execute once');assert(notified>0,mode+' '+stage+' must signal telemetry failure');if(mode==='timeout')assert(failedSignal.aborted);
 }
 for(const phase of ['received','dispatch','response','error','send_attempt']){
  let executions=0;const delivered=[];let instance;
  instance=new AuditedToolDispatcher(async(_id,_name,stage)=>{if(stage===phase){instance.close();return new Promise(()=>{})}},async()=>{},async()=>{executions++;if(phase==='error')throw Error('source failure');return 'PRIVATE late'},x=>delivered.push(x),()=>true,()=>{},5);
  await instance.handle(call);assert.equal(delivered.length,0,'close during '+phase+' cannot send late');assert.equal(executions,['received','dispatch'].includes(phase)?0:1);
 }
 for(const mode of ['reject','timeout']){let warned=0,ran=0;const d=new AuditedToolDispatcher(async()=>{if(mode==='reject')throw Error('audit down');return new Promise(()=>{})},async()=>{},async()=>{ran++;return 'x'},()=>{},()=>true,()=>warned++,5);await d.instrument();await d.handle(call);assert.equal(ran,1);assert.equal(warned,1)}
 let bounded=0;const capSent=[];const capped=new AuditedToolDispatcher(async()=>{},async()=>{},async()=>{bounded++;return 'x'},x=>capSent.push(x),()=>true,()=>{});
 for(let n=0;n<257;n++)await capped.handle({...call,tool_call_id:'cap-'+n});assert.equal(bounded,256);assert.equal(capSent.at(-1).is_error,true);
 console.log('PASS metadata trace ordering, duplicate single dispatch/replay, conflicting ID denial, cancellation, source error, SDK send error, audit failure nonblocking; no payload persistence');
})().catch(error=>{console.error(error);process.exit(1)});
