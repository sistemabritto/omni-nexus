// Run from repo root where a permitted local Chrome is available. Static SSR only.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.QA_PLAYWRIGHT_MODULE||'/tmp/zapmagico-mcp-checks/node_modules/playwright');
(async()=>{const browser=await chromium.launch({executablePath:process.env.QA_BROWSER_EXECUTABLE||'/usr/bin/google-chrome',args:['--no-sandbox']});
try{for(const [width,height] of [[360,800],[375,800],[1440,900]])for(const phase of ['idle','connecting','connected']){
 const page=await browser.newPage({viewport:{width,height}});let requests=0;
 await page.route('https://**',route=>{requests++;return route.abort()});await page.route('http://**',route=>{requests++;return route.abort()});
 await page.goto('file://'+path.resolve(`review/voice-first/mobile-${phase}.html`));
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${width}/${phase} overflow`);
 const transcript=page.locator('.voice-first-transcript');assert.equal(await transcript.getAttribute('open'),null);
 const context=page.locator('.live-context-disclosure>summary');await context.focus();await page.keyboard.press('Space');assert(await page.locator('.live-context-disclosure').evaluate(el=>el.open));await page.keyboard.press('Space');assert(!await page.locator('.live-context-disclosure').evaluate(el=>el.open));
 await page.locator('.voice-first-controls button').first().focus();assert.notEqual(await page.locator(':focus').evaluate(el=>getComputedStyle(el).outlineStyle),'none');
 const targets=await page.locator('.voice-first-review button').evaluateAll(els=>els.filter(el=>el.getClientRects().length).map(el=>{const r=el.getBoundingClientRect();return {text:el.textContent,w:r.width,h:r.height}}));assert(targets.every(r=>r.w>=44&&r.h>=44),JSON.stringify(targets));
 await page.screenshot({path:`review/voice-first/mobile-${width}-${phase}.png`,fullPage:true});
 await page.locator('.voice-first-review header p').evaluate(el=>{el.textContent='Empresa com nome muito longo '.repeat(12)});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.evaluate(()=>{document.documentElement.style.fontSize='200%'});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.equal(requests,0);await page.close();
}}finally{await browser.close()}
console.log('PASS static mounted host/presenter preview: 360/375x800 + desktop, native disclosure keyboard, focus, target size and overflow/long context. No controller/real API/mic/device QA.');
})().catch(e=>{fs.writeFileSync('review/voice-first/mobile-browser-error.txt',String(e));console.error(String(e));process.exit(1)});
