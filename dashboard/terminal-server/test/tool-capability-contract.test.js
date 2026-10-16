'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const provider = require('../src/provider-config');
let config;
provider.loadProviderConfig = () => config;
const { ChatBridge } = require('../src/chat-bridge');
const { requireCompatibleCodeTransport, httpTextCapability, HTTP_TEXT_NOTICE } = require('../src/tool-capability-contract');

function fixtureConfig(mode='chat') {
  return { active:'local-fixture',mode,cli_command:'opencode',providers:{'local-fixture':{
    model:'fixture-model',mode,cli_command:'opencode',env_vars:{OPENAI_BASE_URL:'http://fixture.invalid/v1',OPENAI_API_KEY:'fixture-only',OPENAI_MODEL:'fixture-model'},fallback_models:[]}},env_vars:{} };
}
function response(delta) {
  const body=new TextEncoder().encode('data: '+JSON.stringify({choices:[{delta}]})+'\n\ndata: [DONE]\n\n');let sent=false;
  return {ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:body})})}};
}

test('code provider unsupported by SDK never silently downgrades to HTTP', async()=>{
  config=fixtureConfig('code');const bridge=new ChatBridge();let calls=0;
  bridge._rateLimitedFetch=async()=>{calls++;throw Error('must not call upstream')};
  await assert.rejects(bridge.startSession('code-fixture',{prompt:'Leia o arquivo autorizado.'}),error=>error.code==='chat_code_transport_unavailable');
  assert.equal(calls,0);assert.equal(bridge.sessions.size,0);
  assert.throws(()=>requireCompatibleCodeTransport('code','openclaude',false),/chat_code_transport_unavailable/);
});

test('HTTP text mode declares empty tools and visible limitation, no action claim', async()=>{
  const bridge=new ChatBridge();const events=[];let request;
  bridge._rateLimitedFetch=async(_url,opts)=>{request=JSON.parse(opts.body);return response({content:'Rascunho baseado no texto fornecido.'})};
  await new Promise((resolve,reject)=>bridge._startOpenAICompatibleSession('text-fixture',{
    prompt:'Resuma este texto de fixture.',onMessage:e=>events.push(e),onComplete:resolve,onError:reject},fixtureConfig()).catch(reject));
  assert.equal(request.tools,undefined);
  assert.match(request.messages[0].content,/No tools, filesystem reads, MCP/);
  const capability=events.find(e=>e.type==='runtime_capabilities');assert.deepEqual(capability.tools_list,[]);
  assert.ok(events.some(e=>e.type==='text_delta'&&e.text===HTTP_TEXT_NOTICE));
  assert.ok(!events.some(e=>e.type==='tool_use_start'));
  assert.equal(events.filter(e=>e.type==='result'&&!e.isError).length,1);
  assert.equal(httpTextCapability().toolExecution,'unavailable');
});

test('HTTP upstream tool_call cannot become fake successful execution', async()=>{
  const bridge=new ChatBridge();const events=[];
  bridge._rateLimitedFetch=async()=>response({tool_calls:[{id:'fake',function:{name:'read',arguments:'{}'}}]});
  const error=await new Promise((resolve,reject)=>bridge._startOpenAICompatibleSession('tool-fixture',{
    prompt:'Leia fixture.',onMessage:e=>events.push(e),onComplete:()=>reject(Error('unexpected success')),onError:resolve},fixtureConfig()).catch(reject));
  assert.equal(error.code,'http_tool_call_not_executed');
  assert.ok(!events.some(e=>e.type==='result'&&!e.isError));
  assert.ok(!events.some(e=>e.type==='tool_use_start'));
  assert.equal(bridge.sessions.size,0);
});
