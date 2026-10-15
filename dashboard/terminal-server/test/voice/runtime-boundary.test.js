const { test } = require('node:test');
const assert = require('node:assert/strict');
const { VoiceRuntimeBoundary } = require('../../src/voice/runtime-boundary');
const actor = { userId:'user-a', authenticated:true, authMethod:'cookie' };
const selection = { companyId:1, agentName:'agent-a', sessionId:'session-a' };
function fixture(overrides = {}) {
  let allowed = true, now = 1000;
  const record = { ownerUserId:'user-a', companyId:1, agentName:'agent-a', sdkSessionId:'sdk-existing', history:['prior conversation'], active:false };
  const calls = [], stops = [];
  const boundary = new VoiceRuntimeBoundary({ resolveSession:async id => id === 'session-a' ? record : null,
    authorize:async ({operation,toolName}) => allowed && (operation !== 'tool_call' || toolName === 'read-approved'),
    runTurn:async () => 'done', executeTool:async args => { calls.push(args); return 'result'; }, stopAudio:(...args) => stops.push(args), clock:() => now, ...overrides });
  return { boundary, record, calls, stops, revoke:() => { allowed=false; }, expire:() => { now=122000; } };
}
test('binds only canonical owner/company/agent; no legacy adoption or UI/model identity override', async () => {
  const {boundary,record} = fixture();
  for (const [who,pick] of [[{...actor,userId:'user-b'},selection],[actor,{...selection,companyId:2}],[actor,{...selection,agentName:'agent-b'}],[{...actor,authMethod:'api_token'},selection]]) await assert.rejects(boundary.open(who,pick));
  const owner=record.ownerUserId;delete record.ownerUserId;await assert.rejects(boundary.open(actor,selection));record.ownerUserId=owner;
  const result=await boundary.open(actor,selection);assert.deepEqual(result.context,{userId:'user-a',...selection});assert(Object.isFrozen(result.context));
  await assert.rejects(boundary.open(actor,selection),{code:'session_busy'});
  await assert.rejects(boundary.startTurn({...actor,userId:'user-b'},result.bindingId,'hi'),{code:'unauthorized'});
});
test('agent/company access revocation checked again for each turn',async()=>{
  const f=fixture(),{bindingId}=await f.boundary.open(actor,selection);f.revoke();await assert.rejects(f.boundary.startTurn(actor,bindingId,'hi'),{code:'permission_denied'});
});
test('reassignment of canonical runtime session invalidates old binding',async()=>{
  const f=fixture(),{bindingId}=await f.boundary.open(actor,selection);f.record.companyId=2;await assert.rejects(f.boundary.startTurn(actor,bindingId,'hi'),{code:'session_scope_denied'});
});
test('tool authority is enforced separately; recursive cross-tenant arguments denied before execution',async()=>{
  let tools;const f=fixture({runTurn:async args=>{tools=args.tools;await assert.rejects(tools.call('write-unapproved',{}),{code:'tool_denied'});await assert.rejects(tools.call('read-approved',{nested:{company_id:2}}),{code:'scope_override_denied'});return tools.call('read-approved',{company_id:1});}});
  const {bindingId}=await f.boundary.open(actor,selection),turn=await f.boundary.startTurn(actor,bindingId,'Read a permitted item');assert.equal(await turn.completion,'result');assert.equal(f.calls.length,1);assert.equal(f.calls[0].context.companyId,1);await assert.rejects(tools.call('read-approved',{}),{code:'turn_cancelled'});
});
test('revoking tool permission during a turn blocks further effects',async()=>{
  const f=fixture({runTurn:async args=>{f.revoke();await assert.rejects(args.tools.call('read-approved',{}),{code:'permission_denied'});}});
  const {bindingId}=await f.boundary.open(actor,selection);await (await f.boundary.startTurn(actor,bindingId,'hello')).completion;assert.equal(f.calls.length,0);
});
test('interrupt aborts only turn/audio, drops stale output and retains runtime history/id',async()=>{
  let first,release;const events=[];let runs=0;
  const f=fixture({runTurn:async args=>{if(++runs===1){first=args;await new Promise(resolve=>{release=resolve});args.onEvent('stale');return 'late';}args.onEvent('fresh');return 'next';}});
  const {bindingId}=await f.boundary.open(actor,selection),turn=await f.boundary.startTurn(actor,bindingId,'first',e=>events.push(e));await new Promise(setImmediate);
  await assert.rejects(f.boundary.startTurn(actor,bindingId,'concurrent'),{code:'session_busy'});assert.equal(await f.boundary.interrupt(actor,bindingId),true);assert(first.signal.aborted);assert.equal(f.stops.length,1);assert.deepEqual(f.record.history,['prior conversation']);assert.equal(f.record.sdkSessionId,'sdk-existing');
  const next=await f.boundary.startTurn(actor,bindingId,'second',e=>events.push(e));assert.equal(await next.completion,'next');release();await turn.completion;assert.deepEqual(events,['fresh']);
});
test('expired or closed binding cannot be reused; cancellation does not invoke stopSession',async()=>{
  let signal;const f=fixture({runTurn:async args=>{signal=args.signal;await new Promise(resolve=>args.signal.addEventListener('abort',resolve,{once:true}));}});
  const {bindingId}=await f.boundary.open(actor,selection),turn=await f.boundary.startTurn(actor,bindingId,'hi');await new Promise(setImmediate);f.expire();f.boundary.sweepExpired();assert(signal.aborted);await turn.completion;await assert.rejects(f.boundary.startTurn(actor,bindingId,'again'),{code:'binding_not_found'});assert.equal(f.record.sdkSessionId,'sdk-existing');
});
test('no execution default, no exception secrets, no token/provider route',async()=>{
  const f=fixture({runTurn:undefined}),{bindingId}=await f.boundary.open(actor,selection);await assert.rejects(f.boundary.startTurn(actor,bindingId,'hi'),{code:'runtime_port_unavailable'});
  const g=fixture({runTurn:async()=>{throw Error('secret-provider-error')}}),bound=await g.boundary.open(actor,selection);await assert.rejects((await g.boundary.startTurn(actor,bound.bindingId,'hello')).completion,{message:'runtime_turn_failed'});
});
test('two legitimate tenants keep independent bindings, output and tool scope',async()=>{
  const actorB={...actor,userId:'user-b'},selectionB={companyId:2,agentName:'agent-b',sessionId:'session-b'};
  const records=new Map([['session-a',{ownerUserId:'user-a',companyId:1,agentName:'agent-a'}],['session-b',{ownerUserId:'user-b',companyId:2,agentName:'agent-b'}]]),effects=[];
  const boundary=new VoiceRuntimeBoundary({resolveSession:async id=>records.get(id),authorize:async()=>true,
    runTurn:async ({context,tools,onEvent})=>{await tools.call('read',{company_id:context.companyId});onEvent(context.companyId);},executeTool:async call=>effects.push(call.context)});
  const a=await boundary.open(actor,selection),b=await boundary.open(actorB,selectionB),seenA=[],seenB=[];
  await assert.rejects(boundary.startTurn(actor,b.bindingId,'cross'),{code:'unauthorized'});
  const turns=await Promise.all([boundary.startTurn(actor,a.bindingId,'a',e=>seenA.push(e)),boundary.startTurn(actorB,b.bindingId,'b',e=>seenB.push(e))]);await Promise.all(turns.map(t=>t.completion));
  assert.deepEqual(seenA,[1]);assert.deepEqual(seenB,[2]);assert.deepEqual(effects.map(x=>x.companyId).sort(),[1,2]);
});
test('late abort for an older turn cannot cancel the next turn',async()=>{
  let finish;const f=fixture({runTurn:async()=>new Promise(resolve=>finish=resolve)}),bound=await f.boundary.open(actor,selection);
  const old=await f.boundary.startTurn(actor,bound.bindingId,'old');await new Promise(setImmediate);await f.boundary.interrupt(actor,bound.bindingId,old.turnId);finish();await old.completion;
  const next=await f.boundary.startTurn(actor,bound.bindingId,'new');await new Promise(setImmediate);assert.equal(await f.boundary.interrupt(actor,bound.bindingId,old.turnId),false);finish();await next.completion;
});
test('minimal managed-agent read returns only authorized session metadata',async()=>{
 const f=fixture(),{bindingId}=await f.boundary.open(actor,selection);f.record.name='Minha sessão';f.record.apiKey='not-returned';f.record.systemPrompt='not-returned';
 const result=await f.boundary.readSession(actor,bindingId);assert.deepEqual(result,{companyId:1,agentName:'agent-a',sessionId:'session-a',name:'Minha sessão',active:false});assert(!JSON.stringify(result).includes('not-returned'));
 await assert.rejects(f.boundary.readSession({...actor,userId:'other'},bindingId),{code:'unauthorized'});f.revoke();await assert.rejects(f.boundary.readSession(actor,bindingId),{code:'permission_denied'});
});
test('closing voice lease keeps canonical session available for a later binding',async()=>{
 const f=fixture(),first=await f.boundary.open(actor,selection);await f.boundary.close(actor,first.bindingId);await assert.rejects(f.boundary.readSession(actor,first.bindingId),{code:'binding_not_found'});
 const next=await f.boundary.open(actor,selection);assert.notEqual(next.bindingId,first.bindingId);assert.deepEqual(f.record.history,['prior conversation']);assert.equal(f.record.sdkSessionId,'sdk-existing');
});
