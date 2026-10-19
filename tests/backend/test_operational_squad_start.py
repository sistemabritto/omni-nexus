"""Independent review regressions: owned history is not a new voice admission.

Only Flask fixture requests and mocked voice/provider calls; no paid/network API.
Original two reproductions came from the independent review of 50c19e2.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from unittest.mock import Mock
import pytest
from test_managed_live_context import setup, create, link, read, ORIGIN


@pytest.mark.parametrize('manifest_state,expected_status,expected_error', [
    ('inactive', 403, 'scope_denied'),
    ('removed', 403, 'scope_denied'),
    ('unavailable', 503, 'operational_squad_unavailable'),
    ('missing_file', 503, 'operational_squad_unavailable'),
    ('active', 200, None),
])
def test_old_unbound_context_revalidates_before_voice_and_provider(
        setup, monkeypatch, manifest_state, expected_status, expected_error):
    app, client, login, mod, _, _ = setup
    login()
    context = create(client).json
    app.config.update(NEXUS_LIVE_COST_APPROVED=True, NEXUS_LIVE_AGENT_ID='agent_fixture')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'fixture-not-real')
    import routes.live_voices as voices
    voice = Mock(return_value={})
    monkeypatch.setattr(voices, 'session_voice', voice)
    provider = Mock(return_value=Mock(
        json=lambda: {'signed_url': 'wss://api.elevenlabs.io/v1/convai/conversation?fixture=1'},
        raise_for_status=lambda: None))
    monkeypatch.setattr(mod.requests, 'get', provider)
    if manifest_state in ('unavailable', 'missing_file'):
        def broken():
            raise ValueError() if manifest_state == 'unavailable' else FileNotFoundError()
        monkeypatch.setattr(mod, 'load_operational_squad', broken)
    else:
        members = {} if manifest_state == 'removed' else {
            'agent-a': {'active': manifest_state == 'active', 'group': 'principal', 'version': 1}}
        monkeypatch.setattr(mod, 'load_operational_squad', lambda: members)
    response = client.post(f"/api/live/omni-context/{context['contextId']}/signed-session", json={}, headers=ORIGIN)
    assert response.status_code == expected_status
    if expected_error:
        assert response.json == {'error': expected_error}
        voice.assert_not_called()
        provider.assert_not_called()
    else:
        assert response.json['signedUrl'].startswith('wss://api.elevenlabs.io/')
        voice.assert_called_once_with(7, agent_name='agent-a')
        provider.assert_called_once()


def test_bound_history_remains_readable_when_manifest_unavailable(setup, monkeypatch):
    _, client, login, mod, _, _ = setup
    login()
    context = create(client).json
    assert link(client, context['contextId']).status_code == 200
    def broken():
        raise ValueError('fixture_manifest_unavailable')
    monkeypatch.setattr(mod, 'load_operational_squad', broken)
    assert read(client, context['contextId']).status_code == 200
    response = client.post(f"/api/live/omni-context/{context['contextId']}/signed-session", json={}, headers=ORIGIN)
    assert response.status_code == 409
    assert response.json == {'error': 'conversation_already_bound'}
