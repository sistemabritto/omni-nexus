'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {TerminalServer}=require('../src/server');
const {OWNED_READ_CONNECTION}=require('../src/owned-chat-read-context');
function fixture(){
 const server=Object.create(TerminalServer.prototype), events=[], calls={authorize:0,bridge:0,log:0};
 const session={id:'original',agentName:'agent-a',mode:'before',active:false,chatHistory:[{uuid:'old',role:'user',text:'fixture'}],sdkSessionId:'sdk-existing'};
 const wsInfo={id:'ws',claudeSessionId:'original',bindingRevision:1,ws:{readyState:1}};
 server.webSocketConnections=new Map([['ws',wsInfo]]);server.claudeSessions=new Map([['original',session]]);server.ownedReadConnections=new WeakMap([[wsInfo,{cookie:'fixture-only',origin:'https://fixture.test'}]]);
 server.sendToWebSocket=(_ws,event)=>events.push(event);server.broadcastToSession=()=>assert.fail('legacy broadcast');
 server.chatLogger={read(){calls.log++;throw Error('legacy read')},append(){calls.log++;throw Error('legacy write')},appendRewindMarker(){calls.log++;throw Error('legacy rewind')}};
 let options;server.chatBridge={startSession:async(_sid,opts)=>{calls.bridge++;options=opts}};
 server.ownedReadResolver={authorize:async()=>{calls.authorize++}};
 return {server,session,wsInfo,events,calls,options:()=>options};
}
for(const reason of ['rewind','no_tools','revoked','revoked_rewind'])test('owned '+reason+' rejects before session mutation or log I/O',async()=>{
 const f=fixture(),before=JSON.stringify(f.session);
 if(reason.startsWith('revoked'))f.server.ownedReadResolver.authorize=async()=>{f.calls.authorize++;throw Error('revoked')};
 await f.server.handleMessage('ws',{type:'chat_send',prompt:'fixture',...(reason.includes('rewind')?{rewindFromUuid:'old'}:{}),...(reason==='no_tools'?{toolPolicy:'no_tools'}:{})});
 assert.equal(JSON.stringify(f.session),before);assert.equal(f.calls.bridge,0);assert.equal(f.calls.log,0);
 assert.equal(f.calls.authorize,reason==='revoked'?1:0);assert.equal(f.events[0].type,'chat_error');
});
test('turn captures original SID and binding revision even when new SID aliases same session',async()=>{
 const f=fixture();await f.server.handleMessage('ws',{type:'chat_send',prompt:'fixture'});
 const connection=f.options()[OWNED_READ_CONNECTION];assert.equal(connection.active(),true);
 f.server.claudeSessions.set('other',f.session);f.wsInfo.claudeSessionId='other';assert.equal(connection.active(),false);
 f.wsInfo.claudeSessionId='original';f.wsInfo.bindingRevision++;assert.equal(connection.active(),false);
 f.options().onMessage({type:'text_delta',text:'old turn'});assert.equal(f.events.length,0);
});
