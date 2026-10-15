"""Real loopback WebSocket upgrade/audio/cleanup; upstream is injected, no Google."""
import json
import queue
import sys
import threading
from pathlib import Path

import pytest
from flask import Flask, g
from flask_login import LoginManager, UserMixin
from werkzeug.serving import make_server
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))


def test_real_cookie_websocket_audio_and_cancellation(monkeypatch, tmp_path):
    import routes.live as routes
    from live_transport import run_session
    monkeypatch.setenv('GEMINI_LIVE_ENABLED', 'true')
    monkeypatch.setenv('GEMINI_FREE_TIER_VERIFIED', 'true')
    monkeypatch.setenv('GEMINI_LIVE_MODEL', 'fixture-model')
    monkeypatch.setenv('GEMINI_API_KEY', 'fixture-never-transmitted')
    stopped = threading.Event()
    providers = []
    class Provider:
        def __init__(self): self.incoming = queue.Queue(); self.sent = []; providers.append(self)
        def send(self, raw):
            msg = json.loads(raw); self.sent.append(msg)
            if 'setup' in msg: self.incoming.put({'setupComplete': {}})
            else: self.incoming.put({'serverContent': {'interrupted': True, 'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': 'AAAAAA=='}}]}, 'outputTranscription': {'text': 'Olá'}, 'turnComplete': True}})
        def recv(self, timeout):
            try: return json.dumps(self.incoming.get(timeout=timeout))
            except queue.Empty: raise TimeoutError() from None
        def close(self): stopped.set()
    monkeypatch.setattr(routes, 'run_session', lambda client, config: run_session(client, config, lambda _: Provider()))
    app = Flask(__name__)
    app.config.update(SECRET_KEY='fixture-only', LIVE_LIMITS_PATH=str(tmp_path/'limits.db'))
    manager = LoginManager(app)
    class User(UserMixin): id = '1'
    @manager.user_loader
    def load(uid): return User() if uid == '1' else None
    @app.before_request
    def auth_type(): g.auth_via_api_token = False
    app.register_blueprint(routes.bp)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    origin = f'http://127.0.0.1:{server.server_port}'
    monkeypatch.setattr(routes, 'ALLOWED_ORIGINS', frozenset([origin]))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = origin.replace('http:', 'ws:') + '/api/live/ws'
    try:
        with pytest.raises(InvalidStatus) as error:
            connect(url, origin=origin, proxy=None)
        assert error.value.response.status_code == 401
        assert not providers
        browser = app.test_client()
        with browser.session_transaction() as session: session['_user_id'] = '1'; session['_fresh'] = True
        cookie = browser.get_cookie('session').value
        headers = {'Cookie': 'session=' + cookie}
        with pytest.raises(InvalidStatus) as error:
            connect(url, origin='https://evil.invalid', additional_headers=headers, proxy=None)
        assert error.value.response.status_code == 403
        assert not providers
        with connect(url, origin=origin, additional_headers=headers, proxy=None) as ws:
            assert json.loads(ws.recv(timeout=2)) == {'status': 'ready'}
            # Duplicate session is accepted only to return a redacted limit error,
            # without constructing another provider.
            with connect(url, origin=origin, additional_headers=headers, proxy=None) as second:
                assert json.loads(second.recv(timeout=2)) == {'error': 'session_rate_limit'}
            assert len(providers) == 1
            ws.send('{"audio":"AAAAAA=="}')
            events = [json.loads(ws.recv(timeout=2)) for _ in range(4)]
            assert events == [{'interrupted': True}, {'audio': 'AAAAAA=='}, {'transcript': 'Olá', 'role': 'model'}, {'status': 'listening'}]
            assert providers[0].sent[1]['realtimeInput']['audio']['mimeType'] == 'audio/pcm;rate=16000'
        assert stopped.wait(2), 'browser disconnect must close provider'
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
