const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fixture=require('../global-ui/fixture.cjs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.QA_BROWSER_EXECUTABLE,args:['--no-sandbox']});
 for(const [width,height] of [[375,667],[1440,900]]){
  const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});await fixture(page);await page.route('https://**',route=>route.abort());
  await page.addInitScript(()=>{localStorage.setItem('evo:active_company','7');window.__mic=0;navigator.mediaDevices.getUserMedia=async()=>{window.__mic++;throw Error('Real microphone prohibited in fixture')}});
  let mode='denied',created=0,signed=0,sockets=0,reads=0;
  const fulfill=(route,data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  await page.route('**/api/companies',r=>fulfill(r,[{id:7,name:'Empresa QA',slug:'qa',status:'active'}]));
  await page.route('**/api/live/omni-context**',r=>{
   const path=new URL(r.request().url()).pathname;
   if(path.endsWith('/options')){reads++;return mode==='denied'?fulfill(r,{error:'personal_access_not_configured'},503):fulfill(r,{companies:[{id:7,name:'Empresa QA'}],agents:['qa-agent'],consumptionApproved:mode==='allowed'})}
   if(path.endsWith('/signed-session')){signed++;return fulfill(r,{error:'provider_not_configured'},503)}
   created++;assert.equal(r.request().postDataJSON().companyId,7);return fulfill(r,{contextId:12,runtimeSessionId:'fixture-runtime'});
  });
  await page.routeWebSocket('wss://api.elevenlabs.io/**',()=>{sockets++;throw Error('No provider allowed')});
  await page.goto((process.env.QA_BASE_URL||'http://127.0.0.1:5195')+'/live',{waitUntil:'networkidle'});
  const agent=page.getByLabel('Agente da conversa'),start=page.getByRole('button',{name:'Iniciar conversa',exact:true}),conditions=page.getByRole('region',{name:'Condições para iniciar'});
  await conditions.getByText('O acesso Live ainda não foi configurado no servidor para seu usuário autenticado.',{exact:true}).waitFor();
  assert(await agent.isEnabled());await agent.selectOption('qa-agent');assert(await start.isDisabled());assert.equal(created,0);
  mode='cost_blocked';await page.getByRole('button',{name:'Verificar acesso novamente',exact:true}).click();
  await conditions.getByText('O consumo da conversa ainda não foi liberado no servidor.',{exact:true}).waitFor();assert(await start.isDisabled());assert(await agent.isEnabled());
  mode='allowed';await page.getByRole('button',{name:'Verificar acesso novamente',exact:true}).click();
  await conditions.getByText('Empresa e agente selecionados. A conexão será validada ao iniciar.',{exact:true}).waitFor();assert(await start.isEnabled());
  await start.click();await page.getByRole('status').filter({hasText:'A integração de voz ainda não está configurada no servidor.'}).waitFor();
  assert.equal(created,1);assert.equal(signed,1);assert.equal(sockets,0);assert.equal(await page.evaluate(()=>window.__mic),0);assert.equal(reads,3);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.evaluate(()=>scrollTo(0,0));
  if(process.env.QA_OUTPUT_DIR)await page.screenshot({path:`${process.env.QA_OUTPUT_DIR}/agent-access-fixture-${width}.png`,fullPage:true});await page.close();
 }
 await browser.close();console.log('PASS selector independent of Live access failure, explicit configuration/cost feedback, retry recovery and actionable start error; no real provider/microphone');
})().catch(error=>{console.error(error);process.exit(1)});
