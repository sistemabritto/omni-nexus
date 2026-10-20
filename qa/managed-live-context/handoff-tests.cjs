// Actual controller, synthetic provider/audio. Never opens a provider connection.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ts=require('../../dashboard/frontend/node_modules/typescript');
const voices=JSON.parse(fs.readFileSync('dashboard/backend/live-agent-voices.json')).voices;
const roster=JSON.parse(fs.readFileSync('dashboard/backend/operational-squad.json'));
const moduleFixture={exports:{}};let preparedAgent,failVoice=false,failConnection=false,closed=0,permissionRequests=0,stopped=0,callbacks=[];
const selected=[];class LiveRequestError extends Error{constructor(){super('Voz do destino indisponível.');this.name='LiveRequestError'}}
class Audio{destination={};sampleRate=16000;async resume(){}async close(){}createAnalyser(){return {connect(){},disconnect(){},frequencyBinCount:0}}createMediaStreamSource(){return {connect(){},disconnect(){}}}createScriptProcessor(){return {connect(){},disconnect(){}}}}
const mocks={
 './file-lookup':{isFileLookupRequest:()=>false},
 './tool-dispatch-audit':{AuditedToolDispatcher:class{async instrument(){}close(){}}},
 './managed-context-client':{
  prepareManagedContext:async(_company,agent)=>{preparedAgent=agent;return {contextId:1,runtimeSessionId:'runtime-'+agent}},
  requestManagedSignedSession:async()=>{if(failVoice)throw new LiveRequestError();return {signedUrl:'fixture-only',voiceId:voices[preparedAgent],voiceName:'Synthetic voice'}},
  createManagedContextTools:()=>({onConversationConnected:async()=>{},disconnect(){},experience:async(_action,p)=>JSON.stringify({authorized:true,agentName:p.agentName}),recordToolAudit:async()=>{}}),
 },
 './continuity-contract':{ContinuityUnavailable:class extends Error{}},
 './continuity-session':{ContinuitySession:class{state={logicalId:'same-logical-id',writeStatus:'saved'};async resume(){}async flush(){}async context(){return '{}'}async record(){}async refresh(){}}},
 '../lib/agent-routes':{agentIdentity:agent=>({name:agent})},'./agent-transfer':{requestedAgent:()=>null},
 './audio':{encodePCM:()=>'',Playback:class{stop(){}play(){}}},
};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/live/managed-session.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
 module:moduleFixture,exports:moduleFixture.exports,require:n=>{assert(n in mocks,n);return mocks[n]},
 AudioContext:Audio,navigator:{mediaDevices:{getUserMedia:async()=>{permissionRequests++;return {getTracks:()=>[{stop(){stopped++}}]}}}},
 crypto:require('node:crypto'),Error,Set,Uint8Array,Float32Array,setInterval:()=>1,clearInterval(){},queueMicrotask,
});
(async()=>{
 assert.deepEqual(Object.keys(voices).sort(),roster.agents.filter(x=>x.active).map(x=>x.slug).sort());
 const session=new moduleFixture.exports.ManagedSession(async(_url,voice)=>{
  if(failConnection)throw Error('synthetic socket failure');selected.push(voice);
  return {conversationId:'conv-'+selected.length,inputFormat:{format:'pcm',sampleRate:16000},outputFormat:{format:'pcm',sampleRate:24000},addListener(){},onMessage(){},onDisconnect(fn){callbacks.push(fn)},sendMessage(){},close(){closed++}};
 });
 await session.startVoice(7,'Synthetic company','clawdia-assistant');
 assert.equal(session.snapshot().phase,'connected');assert.equal(session.snapshot().mic,true);
 for(const agent of Object.keys(voices)){
  if(agent===session.snapshot().agent)continue;
  await session.handoff(agent);assert.equal(session.snapshot().phase,'connected',agent);assert.equal(session.snapshot().agent,agent);assert.equal(selected.at(-1),voices[agent]);assert.equal(session.snapshot().mic,true);
  callbacks[0]();assert.equal(session.snapshot().phase,'connected','old disconnect must not close destination');
 }
 assert.equal(permissionRequests,1);assert.equal(stopped,0);
 const previous=session.snapshot().agent,before=closed;
 failVoice=true;await session.handoff('pixel-social-media');
 assert.equal(session.snapshot().agent,previous);assert.equal(session.snapshot().phase,'connected');assert.equal(session.snapshot().mic,true);assert.equal(closed,before);assert(session.snapshot().status.includes('preservada'));assert(session.snapshot().status.includes('Voz do destino'));
 failVoice=false;failConnection=true;await session.handoff('canvas-designer');
 assert.equal(session.snapshot().phase,'idle');assert.equal(session.snapshot().mic,false);assert(!session.snapshot().status.includes('preservada'));
 session.end();
 assert(Object.keys(voices).includes('sage-strategy'));
 console.log('PASS: all '+Object.keys(voices).length+' persona voice mappings, Iris/Dante/Vulcano/Sage handoff, microphone reuse, stale disconnect, failed voice preflight preserves source, socket failure is explicit; provider calls=0');
})().catch(e=>{console.error(e);process.exitCode=1});
