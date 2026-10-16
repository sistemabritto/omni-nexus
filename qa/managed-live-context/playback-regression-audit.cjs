// Real source modules + installed ElevenLabs WebSocketConnection. Synthetic socket,
// AudioContext and HTTP only: no provider URL, mic permission, audio device or call.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
const {createRequire}=require('node:module');
const local=createRequire(path.resolve('dashboard/frontend/package.json'));
const ts=local('typescript'),{WebSocketConnection}=local('@elevenlabs/client');
const cache={},contexts=[],polls=[],checks=[];let connects=0;
class FakeAudioContext{
 currentTime=0;destination={};nodes=[];
 constructor(){contexts.push(this)}
 async resume(){}async close(){}
 createBuffer(_channels,length,rate){const data=new Float32Array(length);return{duration:length/rate,getChannelData(){return data}}}
 createBufferSource(){const node={buffer:null,stops:0,starts:[],connect(){},disconnect(){},start(t){this.starts.push(t)},stop(){this.stops++}};this.nodes.push(node);return node}
 createMediaStreamSource(){return{connect(){}}}
 createScriptProcessor(){return{connect(){},disconnect(){}}}
}
const chunk=Buffer.alloc(24000*2).toString('base64'); // exactly one second of PCM silence
const scoped={company:{id:7,name:'Synthetic A'},agentName:'fixture',continuity:{status:'available'}};
async function fetch(url,options){
 let data={};const body=JSON.parse(options.body||'{}');
 if(url.endsWith('/omni-context'))data={contextId:1,runtimeSessionId:'runtime-fixture'};
 else if(url.endsWith('/signed-session'))data={signedUrl:'never-used'};
 else if(url.endsWith('/continuity'))data={logicalConversationId:'logical-fixture'};
 else if(url.endsWith('/events'))data={logicalConversationId:'logical-fixture',events:[],next:0,hasMore:false};
 else if(url.endsWith('/tool-audit'))data={recorded:true};
 else if(url.endsWith('/read'))data=scoped;
 else if(url.endsWith('/transcript'))data={saved:true};
 else if(!url.endsWith('/conversation'))throw Error('Unexpected fixture HTTP '+url);
 return{ok:true,status:200,json:async()=>data};
}
function load(file){
 if(cache[file])return cache[file].exports;
 const module={exports:{}};cache[file]=module;
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{
  module,exports:module.exports,require:name=>load(path.resolve(path.dirname(file),name+'.ts')),
  fetch,Error,Number,JSON,Map,Set,crypto,setTimeout,clearTimeout,AbortController,Uint8Array,Float32Array,DataView,atob,btoa,
  navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){}}]})}},
  AudioContext:FakeAudioContext,setInterval:fn=>{polls.push(fn);return polls.length},clearInterval(){},
 });
 return module.exports;
}
function check(name,pass,evidence){checks.push({name,status:pass?'PASS':'FAIL',evidence})}
const tick=()=>new Promise(resolve=>setTimeout(resolve,20));
(async()=>{
 const root=path.resolve('dashboard/frontend/src/live');
 const {Playback}=load(root+'/audio.ts');
 const audio=new FakeAudioContext(),playback=new Playback(audio,24000);
 for(let i=0;i<7;i++)playback.play(chunk);
 const stopped=audio.nodes.reduce((n,v)=>n+v.stops,0);
 check('burst_does_not_silently_cancel_previously_scheduled_audio',stopped===0,{chunks:7,seconds_per_chunk:1,audio_clock_seconds:0,stopped_nodes:stopped,provider_interruption_events:0});
 check('burst_keeps_pcm_order',audio.nodes.every((node,index)=>node.starts[0]===index),{starts:audio.nodes.map(node=>node.starts[0])});
 playback.stop();
 check('explicit_stop_cancels_each_node_once',audio.nodes.every(node=>node.stops===1),{stops:audio.nodes.map(node=>node.stops)});
 const bounded=new FakeAudioContext(),queue=new Playback(bounded,24000);let overflow=false;
 try{for(let i=0;i<121;i++)queue.play(chunk)}catch{overflow=true}
 check('queue_ceiling_is_explicit_without_silent_cancellation',overflow&&bounded.nodes.length===120&&bounded.nodes.every(node=>node.stops===0),{overflow,scheduled:bounded.nodes.length});queue.stop();
 const listeners={};
 const socket={sent:[],addEventListener(name,fn){(listeners[name]??=[]).push(fn)},send(text){this.sent.push(JSON.parse(text))},close(){},
  emit(event){for(const fn of listeners.message||[])fn({data:JSON.stringify(event)})}};
 const connection=new WebSocketConnection(socket,'conv-fixture',{format:'pcm',sampleRate:16000},{format:'pcm',sampleRate:24000});
 const {ManagedSession}=load(root+'/managed-session.ts');
 const session=new ManagedSession(async()=>{connects++;return connection});
 await Promise.all([session.start(7,'Synthetic A','fixture'),session.start(7,'Synthetic A','fixture')]);
 check('one_connection_and_one_audio_listener',connects===1&&connection.outputListeners.size===1,{connections:connects,audio_listeners:connection.outputListeners.size});
 const before=socket.sent.filter(m=>m.type==='contextual_update').length;
 for(let i=0;i<3;i++){for(const fn of polls)fn();await tick()}
 check('continuity_poll_does_not_resend_context',socket.sent.filter(m=>m.type==='contextual_update').length===before,{before,after:socket.sent.filter(m=>m.type==='contextual_update').length,polls:3});
 await session.toggleMic();const current=contexts.at(-1);
 socket.emit({type:'audio',audio_event:{audio_base_64:chunk,event_id:10}});
 socket.emit({type:'interruption',interruption_event:{event_id:20}});
 const count=current.nodes.length;
 socket.emit({type:'audio',audio_event:{audio_base_64:chunk,event_id:10}});
 check('interrupted_generation_stale_audio_is_discarded',current.nodes.length===count,{interruption_event_id:20,late_audio_event_id:10,nodes_before_late:count,nodes_after_late:current.nodes.length});
 socket.emit({type:'audio',audio_event:{audio_base_64:chunk,event_id:21}});
 check('new_generation_audio_plays_once_without_sdk_backlog',current.nodes.length===count+1&&connection.pendingAudioEvents.length===0,{nodes:current.nodes.length,pending_sdk_audio:connection.pendingAudioEvents.length});
 const beforeDuplicate=current.nodes.reduce((sum,node)=>sum+node.stops,0);
 socket.emit({type:'interruption',interruption_event:{event_id:20}});
 check('duplicate_interruption_does_not_cut_new_audio',current.nodes.reduce((sum,node)=>sum+node.stops,0)===beforeDuplicate,{stops_before:beforeDuplicate,stops_after:current.nodes.reduce((sum,node)=>sum+node.stops,0)});
 socket.emit({type:'interruption',interruption_event:{event_id:30}});
 socket.emit({type:'audio',audio_event:{audio_base_64:chunk,event_id:29}});
 check('later_interruption_advances_watermark',current.nodes.length===count+1,{nodes:current.nodes.length});
 const tooLarge=Buffer.alloc(24000*2*11).toString('base64');socket.emit({type:'audio',audio_event:{audio_base_64:tooLarge,event_id:31}});
 check('invalid_audio_disables_mic_and_explains_failure',!session.snapshot().mic&&session.snapshot().status.includes('limite seguro'),{mic:session.snapshot().mic,status_explained:session.snapshot().status.includes('limite seguro')});
 session.end();const afterEnd=current.nodes.length;
 socket.emit({type:'audio',audio_event:{audio_base_64:chunk,event_id:21}});
 check('audio_after_end_is_discarded',current.nodes.length===afterEnd,{before:afterEnd,after:current.nodes.length});
 const report={synthetic_only:true,provider_calls:0,microphone_permissions:0,hardware_audio:false,source:'actual Playback/ManagedSession + installed ElevenLabs WebSocketConnection',checks};
 console.log(JSON.stringify(report,null,2));
 process.exitCode=checks.some(c=>c.status==='FAIL')?1:0;
})().catch(error=>{console.error(error);process.exitCode=2});
