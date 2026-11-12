"""Synthetic provider metadata only. No real voice IDs, credentials or audio generation."""
import pytest
from unittest.mock import Mock
from tests.backend.test_managed_live_context import setup, create, ORIGIN

@pytest.fixture
def voices(setup,monkeypatch):
    app,client,login,context,_,_=setup
    import routes.live_voices as mod
    app.register_blueprint(mod.bp)
    app.config['NEXUS_LIVE_AGENT_ID']='agent_fixture'
    monkeypatch.setenv('ELEVENLABS_API_KEY','fixture-only')
    login()
    voice=lambda identity: {'voice_id':identity,'name':'Voice '+identity,'category':'generated','is_owner':True,'labels':{'language':'pt'},'preview_url':'https://storage.googleapis.com/eleven-public-prod/fixture.mp3','safety_control':'NONE'}
    current=voice('default_fixture');selected=voice('selected_fixture')
    agent={'conversation_config':{'tts':{'voice_id':'default_fixture','model_id':'model_fixture'}},'platform_settings':{'overrides':{'conversation_config_override':{'tts':{'voice_id':True}}}}}
    calls=[]
    def get(url,**kw):
        calls.append((url,kw));params=kw.get('params',{})
        if '/convai/agents/' in url:data=agent
        elif url.endswith('/v2/voices'):
            if params.get('voice_ids'):data={'voices':[selected] if params['voice_ids']==selected['voice_id'] else []}
            elif params.get('next_page_token')=='cursor_fixture':data={'voices':[selected],'has_more':False}
            else:data={'voices':[current],'has_more':True,'next_page_token':'cursor_fixture'}
        elif url.endswith('/default_fixture'):data=current
        elif url.endswith('/selected_fixture'):data=selected
        else:raise AssertionError('Unexpected provider endpoint')
        return Mock(json=lambda:data,raise_for_status=lambda:None)
    monkeypatch.setattr(mod.requests,'get',get)
    return app,client,login,mod,agent,selected,calls


def test_catalog_is_paginated_sanitized_and_never_saves_or_generates(voices):
    app,c,login,mod,agent,voice,calls=voices
    result=c.get('/api/live/voices/7');assert result.status_code==200
    assert result.json['hasMore'] is True;assert result.json['nextCursor']=='cursor_fixture';assert result.json['saved'] is None
    assert result.json['current']['id']=='default_fixture';assert 'fixture-only' not in result.text;assert 'storage.googleapis' not in result.text
    second=c.get('/api/live/voices/7?cursor=cursor_fixture');assert second.json['voices'][0]['id']=='selected_fixture';assert second.json['hasMore'] is False
    assert all('/text-to-speech' not in url for url,_ in calls)
    assert [kw['params']['page_size'] for url,kw in calls if url.endswith('/v2/voices')]==[25,25]


def test_save_requires_explicit_choice_and_persists_scoped_to_user_company_agent(voices):
    app,c,login,mod,agent,voice,calls=voices
    assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==200
    assert c.get('/api/live/voices/7').json['saved']['id']=='selected_fixture'
    reloaded=app.test_client()
    with reloaded.session_transaction() as session:
        session['_user_id']='31';session['_fresh']=True
    assert reloaded.get('/api/live/voices/7').json['saved']['id']=='selected_fixture'
    assert c.get('/api/live/voices/8').json['saved'] is None
    app.config['NEXUS_LIVE_AGENT_ID']='agent_other_fixture'
    assert c.get('/api/live/voices/7').json['saved'] is None
    app.config['NEXUS_LIVE_AGENT_ID']='agent_fixture'
    login(32);assert c.get('/api/live/voices/7').status_code==403
    login();assert c.put('/api/live/voices/7/preference',json={'voiceId':'missing_fixture'},headers=ORIGIN).status_code==409
    assert c.get('/api/live/voices/7').json['saved']['id']=='selected_fixture'
    assert c.put('/api/live/voices/7/preference',json={'voiceId':None},headers=ORIGIN).status_code==200
    assert c.get('/api/live/voices/7').json['saved'] is None


def test_guards_and_compatibility_fail_before_saving(voices,monkeypatch):
    app,c,login,mod,agent,voice,calls=voices
    assert c.get('/api/live/voices/999').status_code==403;assert calls==[]
    assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture'}).status_code==403
    assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture','companyId':8},headers=ORIGIN).status_code==400
    voice['safety_control']='BAN';assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==409
    voice['safety_control']='NONE';voice['is_owner']=False;assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==409
    voice['is_owner']=True;voice['category']='professional';voice['fine_tuning']={'state':{'other_model':'fine_tuned'}}
    assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==409
    voice['fine_tuning']['state']['model_fixture']='fine_tuned';assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==200


def test_preference_used_on_next_authorized_start_and_override_disabled_fails_closed(voices,monkeypatch):
    app,c,login,mod,agent,voice,calls=voices
    assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==200
    # Fresh metadata read represents reload; no active session changed by save.
    assert c.get('/api/live/voices/7').json['saved']['id']=='selected_fixture'
    import routes.managed_live_context as context
    app.config['NEXUS_LIVE_COST_APPROVED']=True
    original=mod.requests.get
    def get(url,**kw):
        if url.endswith('/get-signed-url'):return Mock(json=lambda:{'signed_url':'wss://api.elevenlabs.io/v1/convai/conversation?fixture'},raise_for_status=lambda:None)
        return original(url,**kw)
    monkeypatch.setattr(mod.requests,'get',get)
    ctx=create(c).json
    response=c.post(f"/api/live/omni-context/{ctx['contextId']}/signed-session",json={},headers=ORIGIN)
    assert response.status_code==200;assert response.json['voiceId']=='selected_fixture'
    agent['platform_settings']['overrides']['conversation_config_override']['tts']['voice_id']=False
    assert c.post(f"/api/live/omni-context/{ctx['contextId']}/signed-session",json={},headers=ORIGIN).status_code==503


def test_preview_is_existing_bounded_audio_without_credential_forwarding(voices,monkeypatch):
    app,c,login,mod,agent,voice,calls=voices
    original=mod.requests.get;preview_calls=[]
    def get(url,**kw):
        if url.startswith('https://storage.googleapis.com/'):
            preview_calls.append(kw);response=Mock(status_code=200,headers={'Content-Type':'audio/mpeg'});response.iter_content.return_value=[b'fixture-audio'];response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);return response
        return original(url,**kw)
    monkeypatch.setattr(mod.requests,'get',get)
    response=c.get('/api/live/voices/7/selected_fixture/preview');assert response.status_code==200;assert response.data==b'fixture-audio';assert response.headers['Cache-Control']=='no-store'
    assert 'headers' not in preview_calls[0];assert preview_calls[0]['allow_redirects'] is False
    voice['preview_url']='https://private.example.test/secret';assert c.get('/api/live/voices/7/selected_fixture/preview').status_code==503


def test_persona_suggestion_is_review_only_and_explicit_agent_choice_wins(voices,tmp_path):
    import json
    app,c,login,mod,agent,voice,calls=voices
    mapping=tmp_path/'persona-fixture.json';mapping.write_text(json.dumps({'agent-a':{'voiceId':'selected_fixture','reason':'Clareza declarada nos metadados; proposta revisável','personaSource':'fixture-contract'}}))
    app.config['NEXUS_LIVE_AGENT_VOICES_FILE']=str(mapping)
    response=c.get('/api/live/voices/7?agent=agent-a');assert response.status_code==200
    assert response.json['personaSuggestion']['applied'] is False;assert response.json['saved'] is None
    with c:
        c.get('/api/live/voices/7?agent=agent-a')
        assert mod.session_voice(7,'agent-a')=={}
    assert c.put('/api/live/voices/7/preference',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==200
    assert c.get('/api/live/voices/7?agent=agent-a').json['preferenceSource']=='company_choice'
    # Explicit default for this agent overrides the previous company-wide choice.
    assert c.put('/api/live/voices/7/preference?agent=agent-a',json={'voiceId':None},headers=ORIGIN).status_code==200
    result=c.get('/api/live/voices/7?agent=agent-a').json;assert result['saved'] is None;assert result['preferenceSource']=='agent_default'
    assert c.get('/api/live/voices/7').json['saved']['id']=='selected_fixture'
    assert c.put('/api/live/voices/7/preference?agent=agent-a',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==200
    assert c.get('/api/live/voices/7?agent=agent-a').json['preferenceSource']=='agent_choice'

def test_persona_catalog_rejects_unknown_agent_before_provider(voices):
    app,c,login,mod,agent,voice,calls=voices
    assert c.get('/api/live/voices/7?agent=unknown-fixture').status_code==403;assert calls==[]
    assert c.put('/api/live/voices/7/preference?agent=unknown-fixture',json={'voiceId':'selected_fixture'},headers=ORIGIN).status_code==403;assert calls==[]
