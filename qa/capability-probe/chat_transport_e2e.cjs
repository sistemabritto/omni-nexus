'use strict';
// Actual ChatBridge -> installed OpenCode -> local fake upstream -> native read.
// Company/owner admission is a fixture, not a production ACL attestation.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http'),cp=require('node:child_process'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'omni-chat-e2e-'));
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const outside=process.env.PROBE_OUTSIDE==='1';
const query='Quero criar uma thumbnail seguindo nossa marca';
const brand='Marca autorizada de fixture: OMNI_CHAT_BRAND_716. Não é aprovação comercial.';
const selector=cp.execFileSync('/home/sistemabritto/Documentos/evo-nexus/.venv/bin/python',['-c',
`import sys,json;sys.path.insert(0,sys.argv[1]);from skill_capability_dispatch import dispatch_query;r=dispatch_query(sys.argv[2],root=sys.argv[3],row={'id':1,'company_id':7,'user_id':31},verify_scope=lambda:True,read_files=lambda *a:{'status':'available','results':[{'path':'workspace/brand.md','text':sys.argv[4],'sha256':__import__('hashlib').sha256(sys.argv[4].encode()).hexdigest()}]});print(json.dumps(r))`,path.join(root,'dashboard/backend'),query,root,brand],{encoding:'utf8'});
const selected=JSON.parse(selector);assert.equal(selected.selected,'creative-brand-context');
const documents=[{name:'skill.md',text:selected.skills[0].text,sha256:selected.skills[0].sha256},{name:'brand.md',text:brand,sha256:sha(brand)}];
for(const doc of selected.skills[0].documents)documents.push({name:path.basename(doc.path).toLowerCase(),text:doc.text,sha256:doc.sha256});
let snapshots=[];let marker=false;
const server=http.createServer((req,res)=>{let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{
 const body=JSON.parse(raw);const toolList=body.tools||[];const read=toolList.find(t=>t.function?.name==='read');
 if(read) snapshots.push(toolList);
 const messages=(body.messages||[]).filter(m=>m.role==='tool');marker ||= messages.some(m=>JSON.stringify(m).includes('OMNI_CHAT_BRAND_716'));
 let delta,finish;
 if(read&&messages.length<2){const name=messages.length===0?'skill.md':'brand.md';delta={role:'assistant',tool_calls:[{index:0,id:'read-'+name,type:'function',function:{name:'read',arguments:JSON.stringify({filePath:outside?path.join(tmp,'outside.md'):path.join(JSON.stringify(body.messages).match(/\/tmp\/omni-chat-read-[A-Za-z0-9_-]+/)[0],'snapshot',name)})}}]};finish='tool_calls';}
 else{delta={role:'assistant',content:marker?'Referência lida: OMNI_CHAT_BRAND_716.':'Fixture local.'};finish='stop';}
 res.writeHead(200,{'Content-Type':'text/event-stream'});
 for(const data of [{id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',choices:[{index:0,delta,finish_reason:null}]},{id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',choices:[{index:0,delta:{},finish_reason:finish}],usage:{prompt_tokens:0,completion_tokens:0,total_tokens:0}}])res.write('data: '+JSON.stringify(data)+'\n\n');res.end('data: [DONE]\n\n');
});});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const provider=require('../../dashboard/terminal-server/src/provider-config');
 const config={active:'local-proof',mode:'code',cli_command:'opencode',providers:{'local-proof':{mode:'code',cli_command:'opencode',env_vars:{OPENAI_BASE_URL:`http://127.0.0.1:${server.address().port}/v1`,OPENAI_API_KEY:'fixture-only',OPENAI_MODEL:'fixture'}}}};
 provider.loadProviderConfig=()=>config;
 const {ChatBridge}=require('../../dashboard/terminal-server/src/chat-bridge');
 const {OpenCodeReadTransport}=require('../../dashboard/terminal-server/src/opencode-chat-transport');
 const binary=cp.execFileSync('which',['opencode'],{encoding:'utf8'}).trim();const receipts=path.join(tmp,'receipts');
 const proof=require('../../docs/ops/runtime-tool-proof-2026-10-16.json').records[0];
 assert.equal(sha(fs.readFileSync(binary)),proof.binary_sha256,'binary differs from reviewed local read proof');
 fs.writeFileSync(path.join(tmp,'outside.md'),'OUTSIDE_MARKER_MUST_NOT_READ');
 const transport=new OpenCodeReadTransport({binary,receiptRoot:receipts,attestation:{binarySha256:proof.binary_sha256,schemaSha256:proof.tools_schema_sha256},resolveReadContext:async(sessionId,question)=>{
  assert.equal(question,query);return{sessionId,userId:31,companyId:7,agentName:'canvas-designer',revision:'fixture-r1',documents,verify:async()=>true};
 }});
 const bridge=new ChatBridge({openCodeReadTransport:transport});const events=[];
 try{
  const output=await new Promise((resolve,reject)=>bridge.startSession('owned-fixture',{agentName:'canvas-designer',prompt:query,onMessage:e=>events.push(e),onComplete:resolve,onError:reject}).catch(reject));
  assert.equal(marker,true);assert.ok(snapshots.length>=3);for(const tools of snapshots)assert.deepEqual(tools.map(t=>t.function.name),['read']);
  assert.equal(output.receipt.reads,2);assert.ok(events.some(e=>e.type==='text_delta'&&e.text.includes('OMNI_CHAT_BRAND_716')));
  const receipt=JSON.parse(fs.readFileSync(path.join(receipts,output.receipt.id+'.json'),'utf8'));assert.equal(receipt.companyId,7);assert.equal(receipt.status,'completed');
  const report={proof:'actual_chatbridge_opencode_native_read',upstream:'local_fake_no_paid_inference',company_admission:'fixture_not_production',selected_skill:selected.skills[0].name,tools_list:['read'],native_reads:receipt.reads,receipt_sha256:output.receipt.sha256,result_sha256:receipt.resultSha256,request_schemas_sha256:sha(JSON.stringify(snapshots[0])),received_brand_marker:marker,binary_sha256:sha(fs.readFileSync(binary)),external_calls:0,codex_activated:false};
  fs.mkdirSync(path.join(root,'capability-probe-evidence'),{recursive:true});fs.writeFileSync(path.join(root,'capability-probe-evidence/chat-opencode-e2e-proof.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
 }catch(error){if(!outside||error.code!=='read_transport_tool_denied')throw error;assert.equal(fs.existsSync(receipts),false);console.log(JSON.stringify({proof:'actual_native_outside_read_denied',receipt_created:false,upstream:'local_fake_no_paid_inference'}));}finally{await bridge.stopSession('owned-fixture');server.close();fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(error=>{console.error(error.code||error.message);server.close();process.exitCode=1;});
