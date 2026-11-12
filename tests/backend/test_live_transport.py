"""Provider-injected tests: never read a real key or connect to Google."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
from live_transport import LiveConfig, LeaseStore, parse_audio, translate, run_session, open_gemini

CONFIG = LiveConfig(True, True, 'fixture-model', 'fixture-not-a-key')

class Client:
    def __init__(self, inputs=()):
        self.inputs = iter(inputs)
        self.connected = True
        self.sent = []
    def receive(self, timeout):
        value = next(self.inputs, None)
        if value == 'disconnect':
            self.connected = False
            return None
        return value
    def send(self, value): self.sent.append(json.loads(value))
    def close(self): self.connected = False

class Provider:
    def __init__(self, inputs): self.inputs = iter(inputs); self.sent = []; self.closed = False
    def send(self, value): self.sent.append(json.loads(value))
    def recv(self, timeout):
        value = next(self.inputs, {'goAway': {}})
        if isinstance(value, Exception): raise value
        return json.dumps(value)
    def close(self): self.closed = True


def test_disabled_never_opens_or_reads_secret(monkeypatch):
    monkeypatch.delenv('GEMINI_LIVE_ENABLED', raising=False)
    monkeypatch.setenv('GEMINI_API_KEY', 'must-not-read')
    config = LiveConfig.environment()
    assert not config.ready and config.key == ''
    c = Client()
    run_session(c, config, lambda _: pytest.fail('provider opened'))
    assert c.sent == [{'error': 'live_disabled'}]
    assert 'fixture-not-a-key' not in repr(CONFIG)


@pytest.mark.parametrize('model', ['', 'models/evil', 'https://evil', 'x\n'])
def test_model_names_cannot_change_endpoint(model):
    assert not LiveConfig(True, True, model, 'fixture').ready


def test_production_connector_fixed_tls_options_without_network():
    with patch('websockets.sync.client.connect') as connect:
        open_gemini(CONFIG)
    args, opts = connect.call_args
    assert args[0].startswith('wss://generativelanguage.googleapis.com/ws/')
    assert opts['open_timeout'] == 5 and opts['close_timeout'] == 1
    assert opts['proxy'] is None and opts['max_queue'] == 8


def test_setup_audio_interruption_transcripts_and_goaway():
    p = Provider([{'setupComplete': {}}, {'serverContent': {
        'interrupted': True, 'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': 'AAAAAA=='}}]},
        'inputTranscription': {'text': 'Oi'}, 'outputTranscription': {'text': 'Olá'}, 'turnComplete': True,
    }}, {'goAway': {}}])
    c = Client([None, '{"audio":"AAAAAA=="}'])
    run_session(c, CONFIG, lambda _: p)
    setup = p.sent[0]['setup']
    assert setup['generationConfig']['responseModalities'] == ['AUDIO']
    assert 'responseModalities' not in setup and 'tools' not in setup
    assert setup['realtimeInputConfig']['activityHandling'] == 'START_OF_ACTIVITY_INTERRUPTS'
    assert p.sent[1]['realtimeInput']['audio']['mimeType'] == 'audio/pcm;rate=16000'
    assert c.sent == [{'status': 'ready'}, {'interrupted': True}, {'audio': 'AAAAAA=='}, {'transcript': 'Oi', 'role': 'user'}, {'transcript': 'Olá', 'role': 'model'}, {'status': 'listening'}, {'status': 'reconnect_required'}]
    assert p.closed and not c.connected


@pytest.mark.parametrize('raw', ['{"setup":{}}', '{"audio":"AA=="}', '{"audio":"??"}', '{"audio":""}', '[]', 'x'*32001, b'AAAA'])
def test_reject_untrusted_messages(raw):
    with pytest.raises(Exception): parse_audio(raw)


def test_early_audio_rejected_and_both_connections_closed():
    p = Provider([]); c = Client(['{"audio":"AAAAAA=="}'])
    run_session(c, CONFIG, lambda _: p)
    assert c.sent == [{'error': 'invalid_audio_or_provider_protocol'}]
    assert p.closed and not c.connected


def test_provider_failure_does_not_disclose_exception():
    c = Client(); p = Provider([ValueError('key=private')])
    run_session(c, CONFIG, lambda _: p)
    assert c.sent == [{'error': 'provider_unavailable'}]
    assert p.closed


def test_disconnect_and_deadline_release_provider():
    c = Client(['disconnect']); p = Provider([])
    run_session(c, CONFIG, lambda _: p)
    assert p.closed
    for ready, times in [(False, [0, 0, 11]), (True, [0, 0, 1, 121])]:
        c = Client(); p = Provider([{'setupComplete': {}}]); times = iter(times)
        run_session(c, CONFIG, lambda _: p, clock=lambda: next(times))
        assert c.sent[-1]['error'] == ('session_limit' if ready else 'setup_timeout')
        assert p.closed


def test_shared_worker_limits_and_cooldown(tmp_path):
    a = LeaseStore(tmp_path/'limits.db'); b = LeaseStore(tmp_path/'limits.db')
    token = a.acquire('u1', 100)
    assert token and b.acquire('u1', 101) is None
    a.release(token)
    assert b.acquire('u1', 102) is None
    assert b.acquire('u1', 111)
    for user in ['u2', 'u3', 'u4']: assert a.acquire(user, 111)
    assert a.acquire('u5', 111) is None
    assert a.acquire('u5', 252)


def test_unsupported_output_and_tools_fail_closed():
    for msg in [{'toolCall': {}}, {'error': {'message': 'private'}}, {'serverContent': {'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=16000', 'data': 'AAAAAA=='}}]}}}]:
        with pytest.raises(Exception): translate(json.dumps(msg))


def test_audio_rate_limit_stops_provider_and_cleans_up():
    import base64
    frame = json.dumps({'audio': base64.b64encode(bytes(16000)).decode()})
    c = Client([None] + [frame]*5)
    p = Provider([{'setupComplete': {}}] + [TimeoutError()]*6)
    run_session(c, CONFIG, lambda _: p, clock=lambda: 0)
    assert c.sent[-1] == {'error': 'audio_rate_limit'}
    assert len(p.sent) == 5  # server setup + four permitted chunks
    assert p.closed


def test_watchdog_includes_provider_connection_time(monkeypatch):
    import live_transport
    timers = []
    class Timer:
        def __init__(self, seconds, callback): timers.append(seconds)
        def start(self): pass
        def cancel(self): pass
    monkeypatch.setattr(live_transport.threading, 'Timer', Timer)
    ticks = iter([0, 5, 6])
    c = Client(['disconnect']); p = Provider([])
    run_session(c, CONFIG, lambda _: p, clock=lambda: next(ticks))
    assert timers == [115]
    assert p.closed and not c.connected
