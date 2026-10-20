// Current host SSR. Audio/chat behavior has separate controller/presenter tests.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const deps='../../dashboard/frontend/node_modules/',React=require(deps+'react'),{renderToStaticMarkup}=require(deps+'react-dom/server'),ts=require(deps+'typescript');
const source=fs.readFileSync('dashboard/frontend/src/live/ManagedNexusLive.tsx','utf8');
let phase='idle',stateCalls=0,selected='clawdia-assistant';
const identities={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('dashboard/frontend/src/lib/agent-routes.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{module:identities,exports:identities.exports});
const moduleFixture={exports:{}};
vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
 module:moduleFixture,exports:moduleFixture.exports,require:name=>{
  if(name.endsWith('.css'))return {};
  if(name==='react')return {...React,useEffect:()=>{},useSyncExternalStore:()=>({phase,agent:'clawdia-assistant',company:'Empresa fixture',companyId:7,mic:false,messages:[],status:'Fixture'}),useState:value=>{const index=stateCalls++;return [index===0?{companies:[{id:7,name:'Empresa fixture'}],agents:selected?['clawdia-assistant']:[],consumptionApproved:true}:index===1?selected:value,()=>{}]}};
  if(name==='react/jsx-runtime'||name==='lucide-react')return require(deps+name);
  if(name.endsWith('/AuthContext'))return{useAuth:()=>({hasAgentAccess:()=>true})};
  if(name.endsWith('/CompanyContext'))return{useCompanies:()=>({activeCompanyId:7,activeCompany:{id:7,name:'Empresa fixture'}})};
  if(name.endsWith('/agent-routes'))return identities.exports;
  if(name==='./managed-session')return{managedSession:{}};
  if(name==='react-router-dom')return{Link:({to,children,...props})=>React.createElement('a',{href:to,...props},children)};
  if(name==='./LiveAudioOrb')return{default:()=>React.createElement('div',{'data-fixture':'audio-orb'})};
  if(name==='./LiveChat')return{default:({agent,disabled})=>React.createElement('section',{'data-fixture':'chat','data-agent':agent,'data-disabled':disabled},'CHAT_CHILD')};
  if(name==='./LiveApprovals')return{default:()=>null};
  return{};
 }
});
function render(){stateCalls=0;return renderToStaticMarkup(React.createElement(moduleFixture.exports.default))}
let html=render();assert(html.includes('Conversar com Hera'));assert(html.includes('Só texto'));assert(html.includes('href="/agents/hera/voice"'));assert(html.includes('CHAT_CHILD'));
phase='connecting';html=render();assert(html.includes('Cancelar'));assert(html.includes('data-disabled="true"'));
phase='connected';html=render();assert(html.includes('Encerrar'));assert(html.includes('Ativar microfone'));assert(html.includes('data-disabled="false"'));
phase='idle';selected='';html=render();assert(/<select[^>]*disabled/.test(html));assert(/class="live-control-start" disabled/.test(html));
console.log('PASS current host SSR: identity/voice link, explicit start, shared chat, connecting cancellation, microphone/end controls, unavailable squad disabled; no provider/audio/browser call.');
module.exports={renderPreview:(next='idle')=>{selected='clawdia-assistant';phase=next;return render()}};
