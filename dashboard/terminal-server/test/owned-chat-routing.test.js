'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{createRequire}=require('node:module');
let config,providerReads=0,sdkCalls=0;
const provider=require('../src/provider-config');provider.loadProviderConfig=()=>{providerReads++;return config};
// Instrument only the import boundary; a routing regression cannot run a real SDK.
const filename=path.resolve(__dirname,'../src/chat-bridge.js');const source=fs.readFileSync(filename,'utf8');
assert.ok(source.includes("await import('@anthropic-ai/claude-agent-sdk')"));
const sandbox={module:{exports:{}},require:createRequire(filename),__dirname:path.dirname(filename),process,console,Buffer,URL,AbortController,setTimeout,clearTimeout,structuredClone,
 __ownedSDKProbe:async()=>{sdkCalls++;throw Error('unexpected SDK import')}};
vm.runInNewContext(source.replace("await import('@anthropic-ai/claude-agent-sdk')","await __ownedSDKProbe()"),sandbox,{filename});
const {ChatBridge}=sandbox.module.exports;
function fixtureConfig(mode='code'){return{active:'fixture',mode,cli_command:'opencode',providers:{fixture:{mode,cli_command:'opencode',env_vars:{}}}}}

test('owned no_tools rejects before reading provider configuration',async()=>{
 const bridge=new ChatBridge({openCodeReadTransport:{run(){assert.fail('native call')}}});let http=0;
 bridge._startOpenAICompatibleSession=async()=>{http++};config=undefined;providerReads=0;sdkCalls=0;
 await assert.rejects(bridge.startSession('owned',{toolPolicy:'no_tools'}),e=>e.code==='intentional_no_tools');
 assert.equal(http,0);assert.equal(providerReads,0);assert.equal(sdkCalls,0);assert.equal(bridge.sessions.size,0);assert.equal(sdkCalls,0);
});

for(const bad of ['chat','anthropic','openclaude','nested_mismatch','missing_mode'])test('owned route rejects '+bad+' before any legacy/native invocation',async()=>{
 config=fixtureConfig('code');sdkCalls=0;
 if(bad==='chat')config.mode='chat';
 if(bad==='anthropic')config.active='anthropic';
 if(bad==='openclaude')config.cli_command='openclaude';
 if(bad==='nested_mismatch')config.providers.fixture.cli_command='openclaude';
 if(bad==='missing_mode')delete config.mode;
 const calls={http:0,owned:0,upstream:0};const bridge=new ChatBridge({openCodeReadTransport:{run(){calls.owned++;assert.fail('native invocation')}}});
 bridge._startOpenAICompatibleSession=async()=>{calls.http++};bridge._rateLimitedFetch=async()=>{calls.upstream++};
 await assert.rejects(bridge.startSession('owned',{prompt:'thumbnail'}),e=>e.code==='owned_read_provider_incompatible');
 assert.deepEqual(calls,{http:0,owned:0,upstream:0});assert.equal(bridge.sessions.size,0);assert.equal(sdkCalls,0);
});

test('owned route rechecks changed provider config on each turn and snapshots admitted config',async()=>{
 config=fixtureConfig('code');const bridge=new ChatBridge({openCodeReadTransport:{run(){assert.fail('stubbed dispatch')}}});let admitted;
 bridge._startOpenCodeReadSession=async(_sid,_options,cfg)=>{admitted=cfg;return {mode:'owned'}};
 bridge._startOpenAICompatibleSession=async()=>assert.fail('HTTP');
 assert.equal((await bridge.startSession('owned',{prompt:'thumbnail'})).mode,'owned');
 config.mode='chat';assert.equal(admitted.mode,'code');
 await assert.rejects(bridge.startSession('owned',{prompt:'thumbnail'}),e=>e.code==='owned_read_provider_incompatible');
});

test('review reproducer: mode chat + owned dummy + no_tools cannot select legacy_http_selected',async()=>{
 config=fixtureConfig('chat');providerReads=0;sdkCalls=0;let http=0,native=0;
 const bridge=new ChatBridge({openCodeReadTransport:{run(){native++;assert.fail('CLI')}}});
 bridge._startOpenAICompatibleSession=async()=>{http++;return 'legacy_http_selected'};
 await assert.rejects(bridge.startSession('owned',{prompt:'fixture',toolPolicy:'no_tools'}),e=>e.code==='intentional_no_tools');
 assert.equal(http,0);assert.equal(native,0);assert.equal(sdkCalls,0);assert.equal(providerReads,0);
});
