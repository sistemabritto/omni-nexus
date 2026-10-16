const {chromium}=require(process.env.QA_PLAYWRIGHT_MODULE||'playwright'),assert=require('assert/strict'),fs=require('fs'),path=require('path');
const fixture=require('../global-ui/fixture.cjs'),catalog=require('./catalog-fixture.json');
(async()=>{const browser=await chromium.launch({executablePath:process.env.QA_BROWSER_EXECUTABLE||'/usr/bin/google-chrome',args:['--no-sandbox']});const results=[];
for(const width of [375,1440]){
 const page=await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});await fixture(page);await page.route('https://**',r=>r.abort());
 await page.addInitScript(()=>{localStorage.setItem('evo:active_company','7');window.__mic=0;navigator.mediaDevices.getUserMedia=async()=>{window.__mic++;throw Error('Microphone forbidden in fixture')}});
 let unavailable=false,created=[],signed=0,sockets=0,catalogReads=0;const contexts={};
 const companies=[{id:7,name:'Empresa Alfa QA',slug:'alfa',status:'active'},{id:8,name:'Empresa Beta QA',slug:'beta',status:'active'}];
 const fulfill=(route,data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
 await page.route('**/api/companies',r=>fulfill(r,companies));
 await page.route('**/api/agents',r=>{catalogReads++;return unavailable?fulfill(r,{error:'unavailable'},503):fulfill(r,[...catalog,{name:'metadata-only-unauthorized',catalog:{display_name:'Não autorizado',function:'Nunca incluir',sector:'Restrito'}},{name:'locked-fixture',locked:true}])});
 await page.route('**/api/live/omni-context**',r=>{const url=new URL(r.request().url()),p=url.pathname,body=r.request().postDataJSON()||{};
  if(p.endsWith('/options'))return fulfill(r,{companies,agents:catalog.map(a=>a.name),consumptionApproved:true,presentationGroups:{Legado:['mako-marketing']}});
  if(p==='/api/live/omni-context'){created.push(body);const id=10+created.length;contexts[id]={company:companies.find(c=>c.id===body.companyId),agentName:body.agentName};return fulfill(r,{contextId:id,runtimeSessionId:'runtime-'+id,company:contexts[id].company,agentName:body.agentName})}
  const id=Number(p.split('/')[4]),ctx=contexts[id],logical='logical-'+id;
  if(p.endsWith('/signed-session')){signed++;return fulfill(r,{signedUrl:'wss://api.elevenlabs.io/v1/convai/conversation?fixture='+id})}
  if(p.endsWith('/continuity'))return fulfill(r,{status:'available',kind:'untrusted_reference_data',logicalConversationId:logical,current:[],summaryRevision:0,truncated:false});
  if(p.endsWith('/events'))return fulfill(r,{logicalConversationId:logical,events:[],next:0,hasMore:false});
  if(p.endsWith('/read'))return fulfill(r,{company:ctx.company,agentName:ctx.agentName,continuity:{status:'available'}});
  if(p.endsWith('/transcript'))return fulfill(r,{saved:true});
  if(p.endsWith('/tool-audit'))return fulfill(r,{recorded:true});
  return fulfill(r,{bound:true});
 });
 await page.routeWebSocket('wss://api.elevenlabs.io/**',ws=>{sockets++;ws.onMessage(raw=>{const m=JSON.parse(raw);if(m.type==='conversation_initiation_client_data')ws.send(JSON.stringify({type:'conversation_initiation_metadata',conversation_initiation_metadata_event:{conversation_id:'provider-fixture-'+sockets,agent_output_audio_format:'pcm_24000',user_input_audio_format:'pcm_16000'}}))})});
 await page.goto((process.env.QA_BASE_URL||'http://127.0.0.1:5199')+'/live',{waitUntil:'networkidle'});
 const picker=page.getByLabel('Agente da conversa'),search=page.getByLabel('Buscar no squad');
 await page.locator('optgroup[label="Dados e pesquisa"]').waitFor({state:'attached'});assert.equal(await picker.locator('optgroup').count(),7);assert.equal(await picker.locator('option').count(),43);
 assert.equal(await picker.locator('option[value="metadata-only-unauthorized"]').count(),0);assert.equal(await picker.locator('option[value="locked-fixture"]').count(),0);
 await picker.selectOption('mako-marketing');await page.locator('.managed-agent strong').filter({hasText:'Mako'}).waitFor();
 await search.fill('metricas');assert.equal(await picker.inputValue(),'mako-marketing');await page.getByText('Seleção atual mantida fora da busca.',{exact:false}).waitFor();await picker.selectOption('dex-data');
 await picker.selectOption('dex-data');assert.equal(created.length,0);assert.equal(signed,0);assert.equal(sockets,0);assert.equal(catalogReads,1);
 await search.fill('');await search.focus();await page.keyboard.press('Tab');assert(await picker.evaluate(e=>e===document.activeElement));
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert((await search.boundingBox()).height>=44);assert((await picker.boundingBox()).height>=44);
 const controls=await page.locator('.live-agent-selector input,.live-agent-selector select').evaluateAll(elements=>elements.map(e=>{const c=getComputedStyle(e),rgb=v=>{const n=v.match(/[\d.]+/g).map(Number);if(n.length===4&&n[3]!==1)throw Error('Alpha requires composition');return n.slice(0,3)},lum=v=>rgb(v).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0),a=lum(c.color),b=lum(c.backgroundColor);return {foreground:c.color,background:c.backgroundColor,fontSize:parseFloat(c.fontSize),contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)}}));assert(controls.every(c=>c.contrast>=4.5&&c.fontSize>=16));
 if(process.env.QA_OUTPUT_DIR){fs.mkdirSync(process.env.QA_OUTPUT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.QA_OUTPUT_DIR,`selector-${width}.png`),fullPage:true})}
 await page.getByRole('button',{name:'Retomar conversa',exact:true}).click();await page.getByRole('status').filter({hasText:'Conectado por texto'}).waitFor();assert(await picker.isDisabled());assert(await search.isDisabled());assert.deepEqual(created,[{companyId:7,agentName:'dex-data'}]);assert.equal(sockets,1);
 if(width<1024)await page.getByRole('button',{name:'Abrir menu de navegação',exact:true}).click();await page.getByRole('button',{name:'Selecionar empresa',exact:true}).click();await page.getByRole('menuitemradio',{name:/Empresa Beta QA/}).click();if(width<1024)await page.getByRole('button',{name:'Fechar menu de navegação',exact:true}).click();
 await page.locator('.managed-current-company p').filter({hasText:'Empresa Beta QA'}).waitFor();await page.getByRole('status').filter({hasText:'Empresa alterada no menu global'}).waitFor();assert.equal(created.length,1);assert.equal(signed,1);assert.equal(sockets,1);assert.equal(await picker.inputValue(),'dex-data');
 unavailable=true;await page.reload({waitUntil:'networkidle'});await page.getByText('Catálogo de setores indisponível.',{exact:false}).waitFor();assert(await picker.isEnabled());await picker.selectOption('dex-data');await page.getByRole('button',{name:'Recarregar catálogo do squad',exact:true}).click();await page.getByRole('button',{name:'Recarregar catálogo do squad',exact:true}).waitFor();assert.equal(await picker.inputValue(),'dex-data');unavailable=false;await page.getByRole('button',{name:'Recarregar catálogo do squad',exact:true}).click();await picker.locator('optgroup[label="Dados e pesquisa"]').waitFor({state:'attached'});assert.equal(await picker.inputValue(),'dex-data');assert.equal(created.length,1);assert.equal(sockets,1);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.equal(await page.evaluate(()=>window.__mic),0);
 results.push({width,controls,sectors:7,authorizedNativeAgents:42,searchSelectionRepeatedNoRequests:true,activeSelectionLocked:true,companySwitchEndedWithoutAutoReconnect:true,catalogUnavailableFallback:true,microphoneCalls:0,realProviderCalls:0});await page.close();
}
await browser.close();if(process.env.QA_OUTPUT_DIR)fs.writeFileSync(path.join(process.env.QA_OUTPUT_DIR,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));})().catch(e=>{console.error(e);process.exit(1)});
