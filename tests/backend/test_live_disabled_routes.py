"""No credentials, network, microphone, or provider required for disabled Live."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask, g, request
from flask_login import LoginManager, UserMixin

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'dashboard/backend'))

@pytest.fixture
def client():
    from routes.live import bp
    app=Flask(__name__)
    app.config.update(TESTING=True,SECRET_KEY='isolated-fixture',SERVER_NAME='nexus.sistemabritto.com.br')
    manager=LoginManager(app)
    class User(UserMixin):id='1'
    @manager.user_loader
    def load(uid):return User() if uid=='1' else None
    @app.before_request
    def simulate_agent_token():g.auth_via_api_token=request.headers.get('X-Fixture-Agent')=='1'
    app.register_blueprint(bp)
    return app.test_client()


def login(client):
    with client.session_transaction() as session:session['_user_id']='1';session['_fresh']=True


def test_anonymous_status_and_upgrade_are_denied(client):
    assert client.get('/api/live/status').status_code==401
    assert client.get('/api/live/ws',headers={'Upgrade':'websocket','Connection':'Upgrade','Origin':'https://nexus.sistemabritto.com.br'}).status_code==401


def test_cookie_status_is_disabled_and_no_store_even_with_env_flags(client,monkeypatch):
    login(client)
    monkeypatch.setenv('GEMINI_API_KEY','fixture-not-used')
    monkeypatch.setenv('GEMINI_LIVE_ENABLED','true')
    monkeypatch.setenv('GEMINI_FREE_TIER_VERIFIED','true')
    with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
        r=client.get('/api/live/status')
    assert r.status_code==200
    assert r.json=={'enabled':False,'freeTierVerified':False}
    assert r.headers['Cache-Control']=='no-store'
    assert 'fixture-not-used' not in r.text


def test_agent_token_cannot_substitute_for_browser_cookie(client):
    login(client)
    assert client.get('/api/live/status',headers={'X-Fixture-Agent':'1'}).status_code==403


@pytest.mark.parametrize('origin',[None,'https://evil.invalid','https://nexus.workflowapi.com.br','null'])
def test_upgrade_origin_must_match_allowed_current_host(client,origin):
    login(client)
    headers={'Upgrade':'websocket','Connection':'Upgrade'}
    if origin:headers['Origin']=origin
    assert client.get('/api/live/ws',headers=headers).status_code==403


def test_authenticated_same_origin_upgrade_is_disabled_before_handshake(client):
    login(client)
    r=client.get('/api/live/ws',headers={'Upgrade':'websocket','Connection':'Upgrade','Origin':'https://nexus.sistemabritto.com.br'})
    assert r.status_code==503
    assert r.json=={'error':'live_disabled'}
    assert r.headers['Cache-Control']=='no-store'
    assert 'Sec-WebSocket-Accept' not in r.headers


def test_status_cross_origin_denied(client):
    login(client)
    assert client.get('/api/live/status',headers={'Origin':'https://evil.invalid'}).status_code==403
