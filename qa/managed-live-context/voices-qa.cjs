const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fixture=require('../global-ui/fixture.cjs');
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.QA_BROWSER_EXECUTABLE,args:['--no-sandbox']});
  for(const [width,height] of [[375,667],[1440,900]]){
    const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});
    await fixture(page);
    await page.addInitScript(()=>{
      localStorage.setItem('evo:active_company','7');window.__previews=0;
      HTMLMediaElement.prototype.play=function(){window.__previews++;return Promise.resolve()};
    });
    const voice=(id,name)=>({id,name,language:'pt',eligible:true,previewUrl:`/api/live/voices/7/${id}/preview`});
    const current=voice('voice_default_fixture','Fixture Default'),first=voice('voice_a_fixture','Fixture A'),second=voice('voice_b_fixture','Fixture B');
    let saved=null,connections=0,initiatedVoice=null,catalogReads=0,saves=0;
    const fulfill=(route,data)=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
    await page.route('**/api/companies',r=>fulfill(r,[{id:7,name:'Empresa QA',slug:'qa',status:'active'}]));
    await page.route('**/api/live/omni-context**',r=>{
      const path=new URL(r.request().url()).pathname;
      return fulfill(r,path.endsWith('/options')?{companies:[{id:7,name:'Empresa QA'}],agents:['fixture-agent'],consumptionApproved:true}:path.endsWith('/signed-session')?{signedUrl:'wss://api.elevenlabs.io/v1/convai/conversation?fixture',voiceId:saved?.id,voiceName:saved?.name}:path.endsWith('/conversation')?{bound:true}:{contextId:12,runtimeSessionId:'runtime-fixture'});
    });
    await page.route('**/api/live/voices/**',r=>{
      const url=new URL(r.request().url());
      if(r.request().method()==='PUT'){
        saves++;const id=r.request().postDataJSON().voiceId;saved=id===first.id?first:id===second.id?second:null;
        return fulfill(r,{saved,overrideAllowed:true,applies:'next_conversation'});
      }
      catalogReads++;
      return fulfill(r,{voices:url.searchParams.has('cursor')?[second]:[first],hasMore:!url.searchParams.has('cursor'),nextCursor:url.searchParams.has('cursor')?null:'fixture_cursor',current,saved,overrideAllowed:true});
    });
    await page.routeWebSocket('wss://api.elevenlabs.io/**',ws=>{
      connections++;
      ws.onMessage(raw=>{
        const message=JSON.parse(raw);
        if(message.type==='conversation_initiation_client_data'){
          initiatedVoice=message.conversation_config_override?.tts?.voice_id;
          ws.send(JSON.stringify({type:'conversation_initiation_metadata',conversation_initiation_metadata_event:{conversation_id:'conversation-fixture',agent_output_audio_format:'pcm_24000',user_input_audio_format:'pcm_16000'}}));
        }
        if(message.type==='user_message')ws.send(JSON.stringify({type:'agent_response',agent_response_event:{agent_response:'Histórico fixture preservado',event_id:1}}));
      });
    });
    await page.goto('http://127.0.0.1:5195/live',{waitUntil:'networkidle'});
    assert.equal(catalogReads,0);assert.equal(saves,0);assert.equal(connections,0);
    const picker=page.locator('.live-voices');await picker.locator('summary').click();
    await picker.getByText('Fixture A · pt',{exact:true}).waitFor();
    assert(await picker.getByText('Há mais páginas disponíveis.',{exact:false}).isVisible());
    await picker.getByRole('button',{name:'Carregar mais vozes',exact:true}).click();
    await picker.getByRole('button',{name:'Ouvir prévia de Fixture B',exact:true}).click();
    assert.equal(await page.evaluate(()=>window.__previews),1);assert.equal(saves,0);
    assert((await picker.locator('audio').getAttribute('src')).endsWith('/voice_b_fixture/preview'));
    await picker.getByRole('radio',{name:'Fixture B · pt',exact:true}).check();
    await picker.getByRole('button',{name:'Salvar escolha para próxima conversa',exact:true}).click();
    await picker.getByRole('status').filter({hasText:'A próxima conversa será iniciada'}).waitFor();
    assert.equal(saved.id,second.id);assert.equal(connections,0);
    await page.reload({waitUntil:'networkidle'});await page.locator('.live-voices summary').click();
    await page.locator('.live-voices dd').filter({hasText:'Fixture B'}).waitFor();
    await page.getByLabel('Agente da conversa').selectOption('fixture-agent');
    await page.getByRole('button',{name:'Iniciar conversa',exact:true}).click();
    await page.getByRole('status').filter({hasText:'Conectado por texto'}).waitFor();
    assert.equal(initiatedVoice,second.id);assert.equal(connections,1);
    await page.getByLabel('Mensagem',{exact:true}).fill('Mensagem fixture');await page.getByRole('button',{name:'Enviar mensagem',exact:true}).click();
    await page.getByText('Histórico fixture preservado',{exact:true}).waitFor();
    await page.locator('.live-voices').getByRole('radio',{name:'Fixture A · pt',exact:true}).check();
    await page.locator('.live-voices').getByRole('button',{name:'Salvar escolha para próxima conversa',exact:true}).click();
    await page.getByRole('status').filter({hasText:'A chamada atual e seu histórico continuam'}).waitFor();
    assert.equal(connections,1);assert.equal(initiatedVoice,second.id);assert.equal(saved.id,first.id);
    assert(await page.getByText('Histórico fixture preservado',{exact:true}).isVisible());
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.evaluate(()=>scrollTo(0,0));
    if(process.env.QA_OUTPUT_DIR)await page.screenshot({path:`${process.env.QA_OUTPUT_DIR}/voice-picker-fixture-${width}.png`,fullPage:true});
    await page.getByRole('button',{name:'Encerrar',exact:true}).click();await page.close();
  }
  await browser.close();console.log('PASS voice pagination, existing preview without saving, explicit persistence/reload, SDK next-call override, active conversation/history preserved; all provider/audio simulated');
})().catch(error=>{console.error(error);process.exit(1)});
