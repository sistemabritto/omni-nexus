"""Persona scoping with synthetic voices; provider requests are fixtures only."""
from tests.backend.test_live_voices import voices
from tests.backend.test_managed_live_context import setup, ORIGIN, create
from unittest.mock import Mock


def test_persona_choice_does_not_replace_legacy_or_other_persona(voices, monkeypatch):
    app, c, login, mod, agent, voice, calls = voices
    import routes.managed_live_context as context
    (context.AGENTS_DIR / 'agent-b.md').write_text('---\nname: agent-b\n---\nFixture')
    put = lambda slug, choice: c.put('/api/live/voices/7/preference',
        json={'voiceId': choice, 'agentName': slug}, headers=ORIGIN)
    get = lambda slug: c.get('/api/live/voices/7', query_string={'agentName': slug})
    # Preserve legacy baseline, but explicit persona reset is a durable default.
    assert c.put('/api/live/voices/7/preference', json={'voiceId':'selected_fixture'}, headers=ORIGIN).status_code == 200
    assert get('agent-a').json['saved']['id'] == 'selected_fixture'
    assert put('agent-a', None).status_code == 200
    assert get('agent-a').json['saved'] is None
    assert get('agent-b').json['saved']['id'] == 'selected_fixture'
    assert c.get('/api/live/voices/7').json['saved']['id'] == 'selected_fixture'
    assert put('agent-a', 'selected_fixture').status_code == 200
    assert put('agent-b', None).status_code == 200
    assert get('agent-a').json['saved']['id'] == 'selected_fixture'
    assert get('agent-b').json['saved'] is None
    assert c.get('/api/live/voices/8?agentName=agent-a').json['saved'] is None
    app.config['NEXUS_LIVE_AGENT_ID'] = 'agent_other_fixture'
    assert get('agent-a').json['saved'] is None
    app.config['NEXUS_LIVE_AGENT_ID'] = 'agent_fixture'
    assert get('agent-a').json['saved']['id'] == 'selected_fixture'
    login(32)
    assert get('agent-a').status_code == 403


def test_persona_scope_denied_before_provider_calls(voices, monkeypatch):
    app, c, login, mod, agent, voice, calls = voices
    import routes.managed_live_context as context
    for slug in ('../agent-a', 'missing-agent', '', None):
        calls.clear()
        assert c.put('/api/live/voices/7/preference', json={'voiceId':'selected_fixture','agentName':slug}, headers=ORIGIN).status_code == 403
        assert calls == []
    monkeypatch.setattr(context, 'has_agent_access', lambda *_: False)
    assert c.get('/api/live/voices/7?agentName=agent-a').status_code == 403
    assert calls == []


def test_signed_session_uses_owned_persona_not_client_selection(voices, monkeypatch):
    app, c, login, mod, agent, voice, calls = voices
    assert c.put('/api/live/voices/7/preference', json={'voiceId':'selected_fixture','agentName':'agent-a'}, headers=ORIGIN).status_code == 200
    app.config['NEXUS_LIVE_COST_APPROVED'] = True
    ctx = create(c).json
    original = mod.requests.get
    def get(url, **kw):
        if url.endswith('/get-signed-url'):
            return Mock(json=lambda: {'signed_url':'wss://api.elevenlabs.io/v1/convai/conversation?fixture'}, raise_for_status=lambda:None)
        return original(url, **kw)
    monkeypatch.setattr(mod.requests, 'get', get)
    endpoint = f"/api/live/omni-context/{ctx['contextId']}/signed-session"
    assert c.post(endpoint, json={'agentName':'agent-b'}, headers=ORIGIN).status_code == 400
    response = c.post(endpoint, json={}, headers=ORIGIN)
    assert response.status_code == 200
    assert response.json['voiceId'] == 'selected_fixture'
    agent['platform_settings']['overrides']['conversation_config_override']['tts']['voice_id'] = False
    assert c.post(endpoint, json={}, headers=ORIGIN).status_code == 503


def test_reviewed_default_never_overrides_explicit_saved_reset(voices,monkeypatch):
    app,c,_,mod,_,_,_=voices
    monkeypatch.setattr(mod,'_persona_default',lambda name:'selected_fixture')
    with c:
        c.get('/api/live/voices/7?agentName=agent-a')
        assert mod._effective_voice(7,'agent-a')=='selected_fixture'
    assert c.put('/api/live/voices/7/preference',json={'voiceId':None,'agentName':'agent-a'},headers=ORIGIN).status_code==200
    with c:
        c.get('/api/live/voices/7?agentName=agent-a')
        assert mod._effective_voice(7,'agent-a') is None
