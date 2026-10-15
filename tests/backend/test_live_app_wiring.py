"""Exercise the real app's auth middleware and registration without boot side effects.

app.py bootstraps migrations/plugins on import. Compile only its unchanged auth
function and Live import/registration nodes, against an isolated Flask app.
"""
import ast
import sys
import os
import secrets
from types import SimpleNamespace
from pathlib import Path

import pytest
from flask import Flask, g, jsonify, request, session
from flask_login import LoginManager, UserMixin, current_user, login_user


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard/backend"))

@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('GEMINI_LIVE_ENABLED', raising=False)
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='wiring-fixture')
    manager = LoginManager(app)

    class User(UserMixin):
        id = 'fixture-user'

    @manager.user_loader
    def load(uid):
        return User() if uid == User.id else None

    monkeypatch.setenv('DASHBOARD_API_TOKEN', 'fixture-agent')
    monkeypatch.setenv('DASHBOARD_API_USER', 'fixture-user')
    class Query:
        def filter_by(self, **kwargs): return self
        def first(self): return User()
    user_model = SimpleNamespace(query=Query())

    source = Path('dashboard/backend/app.py').read_text()
    tree = ast.parse(source)
    auth = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'auth_middleware')
    token_auth = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_try_api_token_auth')
    imp = next(n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == 'routes.live')
    reg = next(n for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
               and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'register_blueprint'
               and any(isinstance(a, ast.Name) and a.id == 'live_bp' for a in n.value.args))
    namespace = dict(app=app, request=request, jsonify=jsonify, current_user=current_user,
                     needs_setup=lambda: False, PUBLIC_PATHS=set(), User=user_model,
                     login_user=login_user, session=session, g=g, os=os, secrets=secrets,
                     valid_approval_bridge_token=lambda _: False, valid_site_alert_token=lambda _: False)
    exec(compile(ast.Module(body=[token_auth, auth, imp, reg], type_ignores=[]), 'app.py:live-wiring', 'exec'), namespace)
    rules = [r for r in app.url_map.iter_rules() if r.rule == '/api/live/ws']
    assert any(r.websocket for r in rules) and any(not r.websocket for r in rules)
    @app.get('/api/wiring-probe')
    def probe(): return jsonify(authenticated=current_user.is_authenticated, token=bool(getattr(g, 'auth_via_api_token', False)))
    return app.test_client()


def test_real_app_auth_order_and_cookie_only_live(client):
    assert client.get('/api/live/status').status_code == 401
    assert client.get('/api/live/status', headers={'Authorization': 'Bearer fixture-agent'}).status_code == 403
    # Reusing the same cookie jar must remain anonymous after bearer denial.
    assert client.get('/api/live/status').status_code == 401
    with client.session_transaction() as session:
        assert '_user_id' not in session
        session['_user_id'] = 'fixture-user'
        session['_fresh'] = True
    response = client.get('/api/live/status')
    assert response.status_code == 200
    assert response.json == {'enabled': False, 'freeTierVerified': False}
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/live/ws', headers={'Origin': 'http://localhost', 'Upgrade': 'websocket', 'Connection': 'Upgrade'}).status_code == 403


def test_agent_request_elsewhere_cannot_mint_live_cookie(client):
    response = client.get('/api/wiring-probe', headers={'Authorization': 'Bearer fixture-agent'})
    assert response.status_code == 200
    assert response.json == {'authenticated': True, 'token': True}
    assert not response.headers.get('Set-Cookie')
    assert client.get('/api/live/status').status_code == 401
    with client.session_transaction() as cookie:
        assert '_user_id' not in cookie


def test_agent_auth_preserves_existing_anonymous_session_data(client):
    with client.session_transaction() as cookie:
        cookie['preference'] = 'keep'
    response = client.get('/api/wiring-probe', headers={'Authorization': 'Bearer fixture-agent'})
    assert response.json == {'authenticated': True, 'token': True}
    with client.session_transaction() as cookie:
        assert cookie['preference'] == 'keep'
        assert '_user_id' not in cookie
    assert client.get('/api/live/status').status_code == 401
