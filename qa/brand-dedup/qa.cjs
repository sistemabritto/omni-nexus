const {chromium}=require('/tmp/zapmagico-mcp-checks/node_modules/playwright');
const fs=require('fs');const assert=require('assert/strict');const fixture=require('../global-ui/fixture.cjs');
const expected=['/','/missions','/kanban','/workspace','/agents','/heartbeats','/routines','/triggers','/inteligencia'];
(async()=>{const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});const results=[];
for(const [width,height] of [[375,667],[1440,768]])for(const role of ['admin','viewer']){
 const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});await fixture(page,role);
 await page.route('**/api/companies',r=>r.fulfill({contentType:'application/json',body:JSON.stringify([{id:1,name:'Sistema Britto · QA',slug:'qa',status:'active',logo_url:role==='admin'?'/branding/sistema-britto.png':null}])}));
 if(role==='viewer')await page.route('**/api/auth/me',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({user:{id:2,username:'QA viewer',role:'viewer',onboarding_state:'completed'},permissions:{agents:['view'],workspace:['view']}})}));
 await page.addInitScript(()=>localStorage.setItem('sidebar-collapsed-groups',JSON.stringify({'native-inteligencia':true,'native-operations':true})));
 await page.goto('http://127.0.0.1:5193/',{waitUntil:'networkidle'});
 const open=async()=>{if(width<1024)await page.getByRole('button',{name:'Abrir menu de navegação',exact:true}).click()};await open();
 const nav=page.getByRole('navigation',{name:'Navegação principal'});
 const fit=await nav.evaluate(e=>({scrollHeight:e.scrollHeight,clientHeight:e.clientHeight}));assert(fit.scrollHeight<=fit.clientHeight+1,JSON.stringify({width,height,fit}));assert.equal(await page.locator('#omn-navigation').getByText(/^vQA$/).count(),0);const links=await nav.locator('a').evaluateAll(els=>els.map(e=>({href:e.getAttribute('href'),label:e.textContent.trim(),visible:e.getBoundingClientRect().width>0})));
 const allowed=role==='admin'?expected:['/','/workspace','/agents','/inteligencia'];assert.deepEqual(links.map(x=>x.href),allowed);const names={'/':'OmniNexus Live','/missions':'Missões','/kanban':'Kanban','/workspace':'Materiais','/agents':'Agentes','/heartbeats':'Heartbeats','/routines':'Rotinas','/triggers':'Gatilhos','/inteligencia':'Integrações'};assert.deepEqual(links.map(x=>x.label),allowed.map(x=>names[x]));assert(links.every(x=>x.visible));
 assert.equal(await nav.locator('button').count(),0);assert(await page.locator('img[alt="Sistema Britto"]').isVisible());assert.equal(await page.locator('#omn-navigation img[alt="EvoNexus"]').count(),1);assert(await page.locator('#omn-navigation img[alt="EvoNexus"]').isVisible());assert.equal(await page.locator('.omn-brand img').count(),1);assert(await page.locator('#omn-navigation').evaluate(e=>e.scrollWidth<=e.clientWidth));
 await page.screenshot({path:__dirname+`/${role}-${width}.png`});
 if(width<1024){for(let i=0;i<30;i++){await page.keyboard.press('Tab');assert(await page.evaluate(()=>!!document.activeElement.closest('#omn-navigation')))}await page.keyboard.press('Escape');assert(await page.getByRole('button',{name:'Abrir menu de navegação'}).evaluate(e=>e===document.activeElement));await open();}
 for(const href of allowed){await nav.locator(`a[href="${href}"]`).click();await page.waitForTimeout(100);assert.equal(new URL(page.url()).pathname,href);if(width<1024){assert.equal(await page.locator('#omn-navigation').getAttribute('inert'),'');await open();}}
 results.push({width,height,role,fit,links,keyboard:true,routes:true,fixture:true});await page.close();
}fs.writeFileSync(__dirname+'/results.json',JSON.stringify(results,null,2));await browser.close();console.log('PASS: 4 menu cases, original order/labels/permissions, route clicks and mobile keyboard');})().catch(e=>{console.error(e);process.exit(1)});
