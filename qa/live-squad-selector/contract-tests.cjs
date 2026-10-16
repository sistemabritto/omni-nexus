const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const ts=require(path.resolve('dashboard/frontend/node_modules/typescript')),m={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/live/live-agent-catalog.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module:m,exports:m.exports,Set,Object,Array,String});
const {agentChoice,agentChoices,matchesAgent}=m.exports;
const rows=[{name:'dex-data',description:'Legacy',catalog:{display_name:'Dex',function:'Métricas e reconciliação',sector:'Dados e pesquisa'}},{name:'forbidden',catalog:{display_name:'Forbidden',sector:'Secret',function:'Unauthorized'}},{name:'locked',locked:true}];
const allowed=agentChoices(['dex-data','legacy','dex-data','locked'],rows,{'Legado':['legacy']});
assert.equal(allowed.length,2);assert(!allowed.some(x=>['forbidden','locked'].includes(x.slug)));assert.equal(allowed[0].name,'Dex');assert.equal(allowed[1].sector,'Legado');assert(matchesAgent(allowed[0],'metricas'));assert(matchesAgent(allowed[0],'dados'));assert(!matchesAgent(allowed[0],'vendas'));assert.equal(agentChoice('custom-agent',[],{}).name,'Custom Agent');
assert.equal(agentChoice('dex-data',[{name:'dex-data',description:42,catalog:{display_name:42,function:null,sector:{}}}],{bad:42}).name,'Dex Data');
console.log('PASS selector enriches only authorized slugs, locked exclusion, fallback, accent search and malformed metadata');
