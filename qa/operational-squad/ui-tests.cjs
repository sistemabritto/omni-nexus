const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const dep=path.resolve('dashboard/frontend/node_modules'),React=require(dep+'/react'),{renderToStaticMarkup}=require(dep+'/react-dom/server'),ts=require(dep+'/typescript');
function compile(file,customRequire){const module={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:customRequire});return module.exports}
const catalog=compile('dashboard/frontend/src/live/live-agent-catalog.ts',require);
const manifest=JSON.parse(fs.readFileSync('dashboard/backend/operational-squad.json'));
const rows=manifest.agents.map(member=>({name:member.slug,operational_squad:{...member,version:1},catalog:{display_name:member.slug,function:'Fixture',sector:'Fixture'}}));
rows.push({name:'nex-sales'},{name:'dex-data'},{name:'custom-existing'},{name:'inactive',operational_squad:{version:1,active:false}},{name:'blocked',locked:true,operational_squad:{version:1,active:true}});
let states=[],index=0,captured=[],phase='idle';
function mockReact(){return{...React,useState:initial=>[index<states.length?states[index++]:((index++),initial),()=>{}],useEffect:()=>{},useSyncExternalStore:()=>({phase,agent:'oracle',companyId:7,mic:false,messages:[]})}}
function dependencies(name){
 if(name.endsWith('.css'))return{};if(name==='react')return mockReact();if(name==='react/jsx-runtime')return require(dep+'/react/jsx-runtime');
 if(name.endsWith('live-agent-catalog'))return catalog;
 if(name==='react-router-dom')return{Link:({to,children,...rest})=>React.createElement('a',{href:to,...rest},children)};
 if(name==='lucide-react')return{Search:()=>null,Lock:()=>null,Send:()=>null};
 if(name.endsWith('AgentAvatar'))return{AgentAvatar:()=>null};
 if(name.endsWith('AuthContext'))return{useAuth:()=>({user:{role:'viewer'},hasAgentAccess:name=>name!=='blocked'})};
 if(name.endsWith('CompanyContext'))return{useCompanies:()=>({activeCompanyId:7,activeCompany:{id:7,name:'Fixture'}})};
 if(name==='./managed-session')return{managedSession:{}};
 if(name==='./voice-first-bindings')return{voiceFirstBindings:()=>({})};
 if(name==='./continuity-session')return{safeWorkLink:()=>null};
 if(name==='./LiveAgentSelector')return{default:props=>{captured=props.allowed;return React.createElement('section',null,props.allowed.join('|'))}};
 return{default:()=>null,api:{}};
}
const Agents=compile('dashboard/frontend/src/pages/Agents.tsx',dependencies).default;
const Host=compile('dashboard/frontend/src/live/ManagedNexusLive.tsx',dependencies).default;
function render(Component,values){states=values;index=0;return renderToStaticMarkup(React.createElement(Component))}
const page=render(Agents,[rows,false,false,'',0]);
const operational=page.split('Catálogo geral · históricos e personalizados')[0];
for(const row of rows.slice(0,12))assert(operational.includes(`/agents/${row.name}`));
for(const slug of ['nex-sales','dex-data','custom-existing','inactive','blocked'])assert(!operational.includes(`/agents/${slug}`));
for(const slug of ['nex-sales','dex-data','custom-existing','inactive'])assert(page.includes(`/agents/${slug}`));
assert(page.includes('Sem acesso'));assert(page.includes('Conteúdo · Dante'));assert(page.includes('Direção visual · Íris'));
const pending=render(Agents,[rows,true,false,'',0]);assert(!pending.includes('/agents/'));
const failure=render(Agents,[rows,false,true,'',0]);assert(failure.includes('role="alert"'));assert(!failure.includes('/agents/'));
render(Host,[null,rows,null,'Carregando',false,false,0,false]);assert.equal(captured.length,0);
render(Host,[null,rows,null,'Erro',false,false,0,true]);assert.equal(captured.length,0);
render(Host,[{companies:[{id:7,name:'Fixture'}],agents:manifest.agents.map(a=>a.slug),consumptionApproved:true},rows,null,'Disponível',false,false,0,false]);assert.equal(captured.length,12);assert(!captured.includes('nex-sales'));assert(!captured.includes('custom-existing'));
const clientSource=fs.readFileSync('dashboard/frontend/src/live/managed-context-client.ts','utf8');
let response;
// A separate VM injects fetch so options validate the actual response protocol.
const moduleClient={exports:{}};vm.runInNewContext(ts.transpileModule(clientSource,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{module:moduleClient,exports:moduleClient.exports,fetch:async()=>response});
(async()=>{for(const data of [{companies:[],agents:rows.map(a=>a.name),consumptionApproved:true},{operationalSquadVersion:2,companies:[],agents:[],consumptionApproved:true}]){response={ok:true,json:async()=>data};await assert.rejects(moduleClient.exports.loadManagedOptions(),/não é compatível/)}response={ok:false,status:503,json:async()=>({error:'operational_squad_unavailable'})};await assert.rejects(moduleClient.exports.loadManagedOptions(),/squad operacional/);console.log('PASS actual Agents/Live SSR: approved twelve, historical/custom separated, aliases and locked state preserved, loading/error no broad fallback, legacy/unknown option protocol rejected; no browser QA')})().catch(e=>{console.error(e);process.exit(1)});
