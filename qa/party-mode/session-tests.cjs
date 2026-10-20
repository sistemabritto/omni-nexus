const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('../../dashboard/frontend/node_modules/typescript');
const mod={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/live/party-session.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:mod.exports,module:mod,crypto:require('node:crypto'),Error,Set,fetch(){throw Error('NO NETWORK IN FIXTURE')}});
const {PartySession}=mod.exports;
const copy=value=>JSON.parse(JSON.stringify(value));
const tick=()=>new Promise(setImmediate);
function fixture(){
 let snapshot={id:'owned',companyId:7,agents:['agent-a','agent-b'],mode:'text_no_tools',maxRounds:8,rounds:[],messages:[]},calls=[],gate=null,after=null;
 async function api(path,body){
  calls.push({path,body:copy(body??null)});
  if(gate&&path.endsWith('/next'))await gate;
  if(path.startsWith('/sessions?'))return{session:null};
  if(path==='/sessions')return copy(snapshot);
  if(path.endsWith('/rounds')){snapshot.rounds.push({id:'round-1',status:'pending',next_index:0,error:null});snapshot.messages.push({id:1,round_id:'round-1',agent:null,text:body.text});return{roundId:'round-1',session:copy(snapshot)}}
  if(path.endsWith('/cancel')){snapshot.rounds[0].status='cancelled';return copy(snapshot)}
  if(path.endsWith('/next')){const round=snapshot.rounds[0];if(round.status==='pending'&&round.next_index===body.expectedIndex){snapshot.messages.push({id:snapshot.messages.length+1,round_id:round.id,agent:snapshot.agents[round.next_index],text:'fixture answer'});round.next_index++;round.status=round.next_index===2?'completed':'pending'}if(after)after(snapshot);return copy(snapshot)}
  return copy(snapshot);
 }
 return {api,calls,get snapshot(){return snapshot},set gate(value){gate=value},set after(value){after=value}};
}
(async()=>{
 const f=fixture(),s=new PartySession(f.api);assert.equal(f.calls.length,0,'import/constructor cannot start execution');
 await s.restore(7);assert.equal(f.calls.length,1);assert.equal(s.snapshot().session,null);
 assert(await s.send(7,['agent-a','agent-b'],'Question'));
 assert.equal(s.snapshot().session.rounds[0].status,'completed');assert.equal(s.snapshot().session.messages.length,3);
 assert.deepEqual(f.calls.filter(c=>c.path.endsWith('/next')).map(c=>c.body.expectedIndex),[0,1]);
 const duplicate=fixture(),d=new PartySession(duplicate.api);let release;duplicate.gate=new Promise(r=>release=r);
 const running=d.send(7,['agent-a','agent-b'],'Once');while(!duplicate.calls.some(c=>c.path.endsWith('/next')))await tick();
 assert.equal(await d.send(7,['agent-a','agent-b'],'Twice'),false);await d.cancel();release();await running;
 assert.equal(d.snapshot().session.rounds[0].status,'cancelled');assert.equal(d.snapshot().session.messages.length,1);
 assert.equal(duplicate.calls.filter(c=>c.path.endsWith('/next')).length,1,'cancel stops future speakers');
 const late=fixture(),l=new PartySession(late.api);let resume;late.gate=new Promise(r=>resume=r);
 const pending=l.send(7,['agent-a','agent-b'],'Company A');while(!late.calls.some(c=>c.path.endsWith('/next')))await tick();
 l.detach();await l.restore(8);resume();await pending;assert.equal(l.snapshot().session,null,'old company result must not repopulate UI');
 const failure=fixture(),fail=new PartySession(failure.api);failure.after=snapshot=>{snapshot.rounds[0].status='failed'};
 assert(await fail.send(7,['agent-a','agent-b'],'Question'));assert.equal(failure.calls.filter(c=>c.path.endsWith('/next')).length,1);assert.equal(fail.snapshot().busy,false);
 const uncertain=fixture(),u=new PartySession(async(path,body)=>{if(path.endsWith('/next'))throw Error('connection lost');return uncertain.api(path,body)});
 assert(await u.send(7,['agent-a','agent-b'],'Question'));assert(u.snapshot().uncertain);assert.equal(await u.send(7,['agent-a','agent-b'],'No retry'),false);await u.refresh();assert.equal(uncertain.calls.filter(c=>c.path.endsWith('/next')).length,0,'refresh never retries execution');
 const restored=copy(f.snapshot);restored.rounds[0].status='running';let reads=0;const r=new PartySession(async()=>{reads++;return{session:restored}});await r.restore(7);assert.equal(reads,1);assert(r.snapshot().uncertain,'running is not completed or resumed');
 const starting=fixture();let roundRelease,roundReached=false;const roundGate=new Promise(r=>roundRelease=r);const awaitingRound=new PartySession(async(path,body)=>{const result=await starting.api(path,body);if(path.endsWith('/rounds')){roundReached=true;await roundGate}return result});
 const awaitingSend=awaitingRound.send(7,['agent-a','agent-b'],'Keep my confirmed message');while(!roundReached)await tick();await awaitingRound.cancel();assert(awaitingRound.snapshot().uncertain);assert.equal(await awaitingRound.send(7,['agent-a','agent-b'],'Do not overlap'),false);roundRelease();assert(await awaitingSend);assert.equal(awaitingRound.snapshot().session.rounds[0].status,'cancelled');assert.equal(awaitingRound.snapshot().session.messages.length,1);assert.equal(awaitingRound.snapshot().uncertain,false);assert.equal(starting.calls.filter(c=>c.path.endsWith('/next')).length,0);
 let restoreFails=true,restoreCalls=0;const recover=new PartySession(async()=>{restoreCalls++;if(restoreFails)throw Error('unavailable');return{session:null}});
 await recover.restore(7);assert(recover.snapshot().uncertain&&recover.snapshot().session===null);restoreFails=false;await recover.restore(7);assert.equal(recover.snapshot().uncertain,false);assert.equal(restoreCalls,2);
 const lost=fixture();let created=false;const lostCreation=new PartySession(async(path,body)=>{if(path==='/sessions'){created=true;await lost.api(path,body);throw Error('response lost')}if(path.startsWith('/sessions?'))return{session:created?copy(lost.snapshot):null};return lost.api(path,body)});
 assert.equal(await lostCreation.send(7,['agent-a','agent-b'],'No replay'),false);assert(lostCreation.snapshot().uncertain&&lostCreation.snapshot().session===null);await lostCreation.restore(7);assert(lostCreation.snapshot().session);assert.equal(lost.calls.filter(c=>c.path==='/sessions').length,1);assert.equal(lost.calls.filter(c=>c.path.endsWith('/rounds')).length,0);
 console.log('PASS Party session: ordered turns, repeated click, cancel, late result, company change, failure, uncertain request, restore. No network/provider/audio.');
})().catch(error=>{console.error(error);process.exitCode=1});
