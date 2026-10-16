const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const deps='../../dashboard/frontend/node_modules/',React=require(deps+'react'),{renderToStaticMarkup}=require(deps+'react-dom/server'),ts=require(deps+'typescript');
const source=fs.readFileSync('dashboard/frontend/src/live/ManagedNexusLive.tsx','utf8');
let role='viewer',selected='oracle',stateCalls=0;
const presentModule={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/live/VoiceFirstConversation.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:presentModule,exports:presentModule.exports,require:name=>name.endsWith('.css')?{}:name==='react'?React:require(deps+name)});
let phase='idle';
const Component=(()=>{const module={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:name=>{
 if(name.endsWith('.css'))return {};
 if(name==='react')return {...React,useEffect:()=>{},useSyncExternalStore:()=>({phase,agent:'oracle',company:'Empresa fixture',companyId:7,mic:false,messages:[],status:'Fixture'}),useState:value=>{const index=stateCalls++;return[index===0?{companies:[{id:7,name:'Empresa fixture'}],agents:['oracle'],consumptionApproved:true}:index===2?selected:value,()=>{}]}};
 // Host layout fixture isolates the shared avatar (portrait hashes/hydration have their own real contract).
 if(name.endsWith('/AgentAvatar'))return{AgentAvatar:({name,size})=>React.createElement('img',{alt:name,width:size,height:size})};
 if(name==='react/jsx-runtime')return require(deps+name);
 if(name.endsWith('/AuthContext'))return{useAuth:()=>({user:{role},hasAgentAccess:()=>true})};
 if(name.endsWith('/CompanyContext'))return{useCompanies:()=>({activeCompanyId:7,activeCompany:{id:7,name:'Empresa fixture'}})};
 if(name==='./managed-session')return{managedSession:{}};
 if(name==='./live-agent-catalog')return{agentChoice:()=>({name:'Oracle',role:'Discovery',sector:'Operação'})};
 if(name==='./voice-first-bindings')return{voiceFirstBindings:()=>({})};
 if(name==='./continuity-session')return{safeWorkLink:()=>null};
 if(name==='react-router-dom')return{Link:({to,children})=>React.createElement('a',{href:to},children)};
 if(name==='lucide-react')return{Send:()=>null};
 if(name==='./LiveFileSources')return{default:()=>React.createElement('section',null,'ADMIN_FILE_PANEL')};
 if(name==='./VoiceFirstConversation')return presentModule.exports;
 return{default:()=>null};
}});return module.exports.default})();
function render(){stateCalls=0;return renderToStaticMarkup(React.createElement(Component))}
const viewer=render();assert(!viewer.includes('ADMIN_FILE_PANEL'));assert(viewer.includes('Resultados e materiais'));assert(viewer.includes('id="live-message"'));assert(!/<details[^>]*open/.test(viewer));
role='admin';const admin=render();assert(admin.includes('ADMIN_FILE_PANEL'));assert(admin.includes('Resultados e materiais'));assert(!/<details[^>]*open/.test(admin));assert(source.includes('key={`files:${company.id}`}'));assert(source.includes('safeHref={safeWorkLink}'));assert(!source.includes('Conexão será validada'));
selected='';const picker=render();assert(/<details class="live-context-disclosure" open/.test(picker));
console.log('PASS host SSR: user results/composer visible, admin-only file mount, settings collapsed, missing agent picker open, company-prefixed file key and safeWorkLink preserved; frontend presentation test, not backend ACL verification.');

module.exports={renderPreview:(next='idle')=>{role='viewer';selected='oracle';phase=next;return render()}};
