const {chromium}=require(process.env.QA_PLAYWRIGHT_MODULE||'playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const fixture=require('../global-ui/fixture.cjs');
(async()=>{const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});const results=[];
try{for(const width of [375,1440]){
 const page=await browser.newPage({viewport:{width,height:950},reducedMotion:'reduce'});await fixture(page);await page.routeWebSocket('ws://127.0.0.1:5207/**',ws=>ws.connectToServer());await page.route('https://**',r=>r.abort());
 await page.addInitScript(()=>{localStorage.setItem('evo:active_company','7');window.__mic=0;navigator.mediaDevices.getUserMedia=async()=>{window.__mic++;throw Error('forbidden')}});
 const duplicateKeys=[];page.on('console',message=>{if(message.text().includes('Encountered two children with the same key'))duplicateKeys.push(message.text())});
 const companies=[{id:7,name:'Empresa Alfa QA',slug:'alfa',status:'active'},{id:8,name:'Empresa Beta QA',slug:'beta',status:'active'}];let bindings=[],mutations=[],provider=0,failPreview=false;
 const fulfill=(r,data,status=200)=>r.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
 await page.route('**/api/companies',r=>fulfill(r,companies));
 await page.route('**/api/live/omni-context**',r=>{const path=new URL(r.request().url()).pathname;if(path.endsWith('/options'))return fulfill(r,{companies,agents:['qa-agent'],consumptionApproved:false,presentationGroups:{}});provider++;return fulfill(r,{},503)});
 await page.route('**/api/live/file-sources/**',r=>{const p=new URL(r.request().url()).pathname,companyId=Number(p.split('/')[4]),action=p.split('/').at(-1),body=r.request().postDataJSON();
  if(action==='list')return fulfill(r,{bindings:companyId===7?bindings:[],limit:32});
  if(action==='preview'){if(failPreview)return fulfill(r,{error:'file_source_denied'},403);return fulfill(r,{path:body.path,sha256:'a'.repeat(64),size:123,companyId,expectedRevision:0})}
  mutations.push({companyId,action,body});
  if(action==='bind'){bindings=[{id:'binding-a',revision:1,path:body.path,status:'current'}];return fulfill(r,{...bindings[0],active:true})}
  if(action==='revoke'){bindings=[];return fulfill(r,{id:body.id,revision:2,active:false})}
  return fulfill(r,{},400);
 });
 await page.goto((process.env.QA_BASE_URL||'http://127.0.0.1:5207')+'/live',{waitUntil:'networkidle'});
 const summary=page.locator('.live-file-sources summary');await summary.click();
 const input=page.getByLabel('Caminho do arquivo no Workspace'),inspect=page.getByRole('button',{name:'Conferir arquivo',exact:true});
 await input.fill('workspace/editorial/roteiro.md');await inspect.click();
 const confirmation=page.getByRole('checkbox',{name:/Confirmo que este arquivo pertence a Empresa Alfa QA/});await confirmation.waitFor();
 const bind=page.getByRole('button',{name:'Vincular arquivo a Empresa Alfa QA',exact:true});assert(await bind.isDisabled());assert.equal(mutations.length,0);
 await confirmation.check();await bind.click();await page.getByText('Arquivo vinculado às suas consultas nesta empresa.',{exact:true}).waitFor();
 assert.equal(mutations.length,1);assert.deepEqual(mutations[0],{companyId:7,action:'bind',body:{path:'workspace/editorial/roteiro.md',sha256:'a'.repeat(64),expectedRevision:0,confirmOwnership:true}});
 await page.getByRole('button',{name:'Remover vínculo',exact:true}).click();await page.getByText('Vínculo removido das próximas consultas. O arquivo foi preservado.',{exact:true}).waitFor();assert.equal(mutations[1].action,'revoke');
 failPreview=true;await inspect.click();await page.getByRole('status').filter({hasText:'Arquivo indisponível para este acesso.'}).waitFor();assert.equal(await confirmation.count(),0);failPreview=false;
 await inspect.click();await confirmation.waitFor();await confirmation.check();
 if(width<1024)await page.getByRole('button',{name:'Abrir menu de navegação',exact:true}).click();await page.getByRole('button',{name:'Selecionar empresa',exact:true}).click();await page.getByRole('menuitemradio',{name:/Empresa Beta QA/}).click();if(width<1024)await page.getByRole('button',{name:'Fechar menu de navegação',exact:true}).click();
 await page.locator('.live-file-sources summary').filter({hasText:'Empresa Beta QA'}).waitFor();assert.equal(await page.locator('.live-file-confirm').count(),0);
 await page.locator('.live-file-sources summary').click();assert.equal(await input.inputValue(),'');assert.equal(provider,0);assert.equal(await page.evaluate(()=>window.__mic),0);assert.equal(duplicateKeys.length,0);assert.equal(await page.locator('.live-file-sources').count(),1);assert.equal(await page.locator('.live-voices').count(),1);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert((await input.boundingBox()).height>=44);
 fs.mkdirSync('/tmp/live-file-source-ui',{recursive:true});await page.screenshot({path:`/tmp/live-file-source-ui/files-${width}.png`,fullPage:true});
 results.push({width,explicitCompanyConfirmation:true,previewNoMutation:true,bindRevoke:true,inlineDenied:true,companySwitchClearsConfirmation:true,providerCalls:provider,microphoneCalls:0});await page.close();
}console.log(JSON.stringify(results));}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
