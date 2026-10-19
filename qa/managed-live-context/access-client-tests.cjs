const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('../../dashboard/frontend/node_modules/typescript');
const mod={exports:{}};let response;
vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/live/managed-context-client.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:mod.exports,module:mod,fetch:async()=>{if(response instanceof Error)throw response;return response},Error,JSON,Object,Number});
const set=(status,data)=>{response={ok:status===200,status,json:async()=>data}};
(async()=>{
 set(503,{error:'personal_access_not_configured',detail:'fixture-hidden-detail'});await assert.rejects(mod.exports.loadManagedOptions(),error=>error.name==='LiveRequestError'&&error.message.includes('usuário autenticado')&&!error.message.includes('fixture-hidden-detail'));
 response=new Error('fixture-network-private-detail');await assert.rejects(mod.exports.loadManagedOptions(),error=>error.message.includes('alcançar o servidor')&&!error.message.includes('fixture-network'));
 set(404,{error:'unknown_fixture'});await assert.rejects(mod.exports.loadManagedOptions(),/versão do servidor/);
 set(200,{companies:null,agents:[],consumptionApproved:false});await assert.rejects(mod.exports.loadManagedOptions(),/não é compatível/);
 set(200,{operationalSquadVersion:1,companies:[{id:7,name:'Fixture'}],agents:['qa-agent'],consumptionApproved:false});assert.equal((await mod.exports.loadManagedOptions()).consumptionApproved,false);
 console.log('PASS actionable public error mapping, no raw error leakage, malformed options rejection, valid options');
})().catch(error=>{console.error(error);process.exit(1)});
