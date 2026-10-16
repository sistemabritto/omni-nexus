// Render the real chat component with a receipt from the authenticated HTTP contract.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {createRequire}=require('node:module'),front=path.resolve('dashboard/frontend'),fromFront=createRequire(front+'/package.json');
const ts=fromFront('typescript'),React=fromFront('react'),{renderToStaticMarkup}=fromFront('react-dom/server'),cache={};
function load(file){if(cache[file])return cache[file].exports;const module={exports:{}};cache[file]=module;vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:name=>name.endsWith('.css')?{}:name.startsWith('.')?load(path.resolve(path.dirname(file),name+'.ts')):fromFront(name),console,fetch:()=>{throw Error('Network forbidden in render fixture')}});return module.exports}
const {safeWorkLink}=load(front+'/src/live/continuity-session.ts'),Conversation=load(front+'/src/live/VoiceFirstConversation.tsx').default;
const receipt='/api/live/file-results/'+'a'.repeat(32);
const html=renderToStaticMarkup(React.createElement(Conversation,{phase:'connected',mic:false,canStart:false,status:'Fixture',contextLabel:'Empresa autorizada',saveStatus:'saved',messages:[],events:[{event_id:'receipt',kind:'result',text:'roteiro.md\nTrecho autorizado',source:receipt,revision:1,verified:false,links:[{label:'Abrir arquivo',url:receipt},{label:'Não exibir',url:'https://untrusted.invalid'}]}],onStart(){},onToggleMic(){},onEnd(){},onRetrySave(){},safeHref:safeWorkLink,copyText:async()=>{}}));
assert.ok(html.includes('aria-label="Resultados e materiais"'));assert.ok(html.includes('Trecho autorizado'));
assert.ok(html.includes(`href="${receipt}" target="_blank" rel="noopener noreferrer"`));assert.ok(!html.includes('untrusted.invalid'));
console.log('PASS real chat renders persistent receipt in results, authenticated same-origin link in new tab, external link denied');
