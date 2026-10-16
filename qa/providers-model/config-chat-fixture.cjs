// Real provider loader + chat bridge; in-memory configuration and mocked transport only.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const root=path.resolve(__dirname,'../..'),file=path.join(root,'dashboard/terminal-server/src/provider-config.js');
const fakeFs={existsSync:p=>String(p).endsWith('/config/providers.json'),readFileSync:p=>{if(String(p).endsWith('/config/providers.json'))return JSON.stringify(input.config);throw Error('fixture blocks other files')}};
const m={exports:{}};
new Function('require','module','exports','__dirname','process',fs.readFileSync(file,'utf8'))(name=>name==='fs'?fakeFs:require(name),m,m.exports,path.dirname(file),{env:{}});
const provider=m.exports;const cfg=provider.loadProviderConfig();
require.cache[file]={id:file,filename:file,loaded:true,exports:provider};
const {ChatBridge}=require(path.join(root,'dashboard/terminal-server/src/chat-bridge.js'));
let calls=[];global.fetch=async(url,request)=>{calls.push({url,request});return new Response('data: '+JSON.stringify({choices:[{delta:{content:'Fixture only'}}]})+'\n\ndata: [DONE]\n\n',{status:200,headers:{'Content-Type':'text/event-stream'}})};
(async()=>{const bridge=new ChatBridge();await new Promise((resolve,reject)=>{bridge.startSession('fixture-model-save',{prompt:'Fixture only',workingDir:input.cwd,onComplete:resolve,onError:reject}).catch(reject)});assert.equal(calls.length,1);const sent=calls[0],body=JSON.parse(sent.request.body);assert.equal(sent.url,input.base+'/chat/completions');assert.equal(body.model,input.model);assert.equal(sent.request.headers.Authorization,'Bearer fixture-private');console.log(JSON.stringify({model:body.model,transport:'mock',provider_calls:0,transport_calls:calls.length,credential_preserved:true,active:cfg.active}));})().catch(e=>{console.error(e.message);process.exitCode=1});
