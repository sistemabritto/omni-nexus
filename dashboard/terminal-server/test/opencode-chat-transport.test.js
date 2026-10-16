'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {OpenCodeReadTransport}=require('../src/opencode-chat-transport');
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
function fixture(t,changes={}) {
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'omni-read-unit-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const binary=path.join(root,'fake-opencode');
 fs.writeFileSync(binary,`#!/usr/bin/env node
 const fs=require('fs'),path=require('path');
 const file=path.join(process.cwd(),'skill.md');
 const config=JSON.parse(process.env.OPENCODE_CONFIG_CONTENT);
 if(process.argv.includes('--auto')||!process.argv.includes('--pure')||config.permission['*']!=='deny'||config.permission.read['*']!=='deny'){console.error(JSON.stringify({argv:process.argv,tools:config.tools}));process.exit(4);}
 const value=fs.readFileSync(file,'utf8');
 console.log(JSON.stringify({type:'tool_use',part:{tool:'read',state:{status:'completed',input:{filePath:file},output:value}}}));
 console.log(JSON.stringify({type:'text',part:{text:'Fixture lida.'}}));
 `,{mode:0o700});
 let verified=0,resolved=0;
 const grant={sessionId:'owned',userId:31,companyId:7,agentName:'agent-a',revision:'r1',documents:[{name:'skill.md',text:'Conhecimento autoral de fixture.',sha256:hash('Conhecimento autoral de fixture.')}],verify:async()=>{verified++;return true},...changes};
 const transport=new OpenCodeReadTransport({binary,receiptRoot:path.join(root,'receipts'),attestation:{binarySha256:hash(fs.readFileSync(binary)),schemaSha256:'a'.repeat(64)},resolveReadContext:async()=>{resolved++;return grant}});
 const options={agentName:'agent-a',prompt:'Leia o contexto permitido.'};
 const provider={active:'fixture',providers:{fixture:{env_vars:{OPENAI_BASE_URL:'http://127.0.0.1:9/v1',OPENAI_API_KEY:'fixture-only',OPENAI_MODEL:'fixture'}}}};
 return {root,binary,transport,grant,options,provider,counts:()=>({verified,resolved})};
}
async function run(f,extra={}){return f.transport.run('owned',{...f.options,...extra},f.provider,new AbortController().signal)}

test('read-only adapter returns owned receipt and clears staged snapshot',async t=>{
 const f=fixture(t);const result=await run(f);assert.equal(result.text,'Fixture lida.');assert.equal(result.receipt.reads,1);
 const files=fs.readdirSync(path.join(f.root,'receipts'));assert.equal(files.length,1);
 const record=JSON.parse(fs.readFileSync(path.join(f.root,'receipts',files[0])));assert.equal(record.companyId,7);assert.equal(record.retryCount,0);assert.equal(record.effect,'read');
 assert.equal(result.capabilities.mode,'opencode_owned_read');assert.equal(f.counts().verified,3);
});

test('no_tools does not resolve context or spawn',async t=>{
 const f=fixture(t);await assert.rejects(run(f,{toolPolicy:'no_tools'}),e=>e.code==='intentional_no_tools');assert.equal(f.counts().resolved,0);
});

test('browser-shaped context cannot substitute server-owned session or agent',async t=>{
 const f=fixture(t,{sessionId:'foreign'});await assert.rejects(run(f,{readContext:{sessionId:'owned'}}),e=>e.code==='owned_read_context_required');
 const g=fixture(t);await assert.rejects(run(g,{agentName:'other'}),e=>e.code==='owned_read_context_required');
});

test('changed binary is rejected before resolving context',async t=>{
 const f=fixture(t);fs.appendFileSync(f.binary,'\n//changed');await assert.rejects(run(f),e=>e.code==='read_transport_binary_changed');assert.equal(f.counts().resolved,0);
});

test('tampered snapshot and secret-like text fail before native call',async t=>{
 const f=fixture(t,{documents:[{name:'skill.md',text:'changed',sha256:'a'.repeat(64)}]});await assert.rejects(run(f),e=>e.code==='read_snapshot_invalid');
 const secret='api_key = sk-'+ 'X'.repeat(25);const g=fixture(t,{documents:[{name:'skill.md',text:secret,sha256:hash(secret)}]});await assert.rejects(run(g),e=>e.code==='read_snapshot_invalid');
});

test('scope revocation after process result discards output and receipt',async t=>{
 let calls=0;const f=fixture(t,{verify:async()=>++calls<3});await assert.rejects(run(f),e=>e.code==='read_context_revoked');assert.equal(fs.existsSync(path.join(f.root,'receipts')),false);
});
