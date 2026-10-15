// Pair real Flask route responses with the shipped TypeScript client. Offline only.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const ts=require('../../dashboard/frontend/node_modules/typescript');
const data=JSON.parse(execFileSync(process.env.QA_PYTHON||'python3',['qa/providers-explorer/backend-contract.py'],{encoding:'utf8'}));
let payload=data.catalog,status=200;const calls=[],moduleUnderTest={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/components/provider-execution-client.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module:moduleUnderTest,exports:moduleUnderTest.exports,Error,Object,JSON,Number,fetch:async(url,options)=>{calls.push({url,options});return{ok:status===200,status,json:async()=>payload}}});
(async()=>{const {loadExecutionCatalog,previewExecution}=moduleUnderTest.exports;
 const catalog=await loadExecutionCatalog();assert.equal(catalog.default_combo,'combo:REVIEW');assert.equal(JSON.stringify(catalog.roles),JSON.stringify([['oath','combo:REVIEW']]));
 assert.equal(data.templates.roles.oath,'combo:REVIEW');assert(data.templates.templates.every(t=>t.execution_enabled===false));
 assert.equal(catalog.providers.find(p=>p.id==='codex_auth').harness_id,'openclaude');for(const id of ['hermes','codex'])assert.equal(catalog.harnesses.find(h=>h.id===id).state,'coming_soon');
 payload=data.decision;const decision=await previewExecution(catalog,{operation:'summarize_ticket',pool_id:'combo:REVIEW',selection:{}});assert.equal(decision.preferred.provider_id,'anthropic');assert.equal(decision.selected,null);assert.equal(data.decision.provider_calls,0);
 const request=JSON.parse(calls.at(-1).options.body);assert.equal(request.expected_revision,catalog.catalog_revision);assert.equal(request.pool_id,'combo:REVIEW');
 status=409;payload=data.conflict;await assert.rejects(previewExecution(catalog,{operation:'summarize_ticket',pool_id:'combo:REVIEW',selection:{}}),error=>error.reload);
 status=200;payload=data.disabled;const disabled=await loadExecutionCatalog();payload=data.disabled_decision;const stopped=await previewExecution(disabled,{operation:'summarize_ticket',pool_id:'legacy-active',selection:{}});assert.equal(stopped.preferred,null);assert(stopped.reasons.includes('active_provider_disabled'));
 for(const roles of [[['oath','missing-pool']],[['oath']]]){payload={...data.catalog,roles};await assert.rejects(loadExecutionCatalog(),/Templates incompatíveis/)}
 assert(calls.every(c=>['/api/execution/catalog','/api/execution/decisions/preview'].includes(c.url)));
 console.log('PASS actual Flask routes + shipped TS client: catalog/roles/templates/order/preview/disabled/revision/coming-soon; synthetic cookies/files, no provider/CLI/network');
})().catch(error=>{console.error(error);process.exitCode=1});
