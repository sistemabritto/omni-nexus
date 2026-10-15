"""Bounded fallback with injected providers; no real keys or network."""
import json
from dataclasses import replace
import pytest
from tests.backend.test_live_transport import Client, Provider, CONFIG
from live_transport import LiveConfig, run_session
from live_model_policy import provider_failure, RECOMMENDED_MODEL

FALLBACK = 'gemini-3.1-flash-live-preview'
CONFIGURED = replace(CONFIG, model=RECOMMENDED_MODEL, fallback_models=(FALLBACK, 'gemini-2.5-flash-native-audio-latest'))


def test_fallback_requires_independent_model_quota_evidence(monkeypatch):
    monkeypatch.setenv('GEMINI_LIVE_MODEL', RECOMMENDED_MODEL)
    monkeypatch.setenv('GEMINI_LIVE_FALLBACK_MODELS', FALLBACK+',https://evil,'+FALLBACK)
    monkeypatch.delenv('GEMINI_LIVE_VERIFIED_MODELS', raising=False)
    cfg = LiveConfig.environment()
    assert not cfg.ready and cfg.key == ''
    assert cfg.fallback_models == () and cfg.fallback_blocked_models == (FALLBACK,)
    monkeypatch.setenv('GEMINI_LIVE_VERIFIED_MODELS', FALLBACK)
    cfg = LiveConfig.environment()
    assert cfg.fallback_models == (FALLBACK,) and not cfg.ready
    assert cfg.status_payload()['activeModel'] is None


def test_startup_unavailable_switches_once_and_activates_only_after_setup(caplog):
    caplog.set_level('INFO', logger='omninexus.live.lifecycle')
    providers = [Provider([{'error': {'code':404,'status':'NOT_FOUND','message':'private-key-secret'}}]), Provider([{'setupComplete':{}},{'goAway':{}}])]
    calls=[]
    def factory(cfg):calls.append(cfg.model);return providers[len(calls)-1]
    c=Client();run_session(c, CONFIGURED, factory)
    assert calls == [RECOMMENDED_MODEL,FALLBACK]
    assert [e['event'] for e in c.sent if 'event' in e] == ['model_attempt','model_switch','model_attempt','model_active']
    active=next(e for e in c.sent if e.get('event')=='model_active')
    assert active['activeModel']==FALLBACK and active['attempt']==2
    assert all(p.closed for p in providers)
    assert 'private-key-secret' not in caplog.text+json.dumps(c.sent)
    assert 'fixture-not-a-key' not in caplog.text+json.dumps(c.sent)


@pytest.mark.parametrize('error,category', [
    ({'code':401},'provider_auth_failed'),({'code':403},'provider_auth_failed'),
    ({'code':429},'provider_rate_limited'),
    ({'code':429,'details':[{'@type':'type.googleapis.com/google.rpc.QuotaFailure'}]},'provider_quota_exhausted'),
    ({'code':429,'details':None},'provider_rate_limited'),
    ({'code':503},'provider_unavailable'),
])
def test_auth_quota_rate_limit_and_generic_unavailable_never_fallback(error,category):
    calls=[];p=Provider([{'error':error}]);c=Client()
    def factory(cfg):calls.append(cfg.model);return p
    run_session(c,CONFIGURED,factory)
    assert calls==[RECOMMENDED_MODEL]
    assert c.sent[-1]=={'error':category}
    assert not any(e.get('event')=='model_active' for e in c.sent)
    assert p.closed


def test_two_attempt_cap_has_no_loop_or_third_model():
    calls=[];providers=[]
    def factory(cfg):
        calls.append(cfg.model);p=Provider([{'error':{'code':404}}]);providers.append(p);return p
    c=Client();run_session(c,CONFIGURED,factory)
    assert calls==[RECOMMENDED_MODEL,FALLBACK]
    assert c.sent[-1]=={'error':'provider_model_unavailable'}
    assert all(p.closed for p in providers)


def test_no_model_switch_after_session_became_ready():
    calls=[];p=Provider([{'setupComplete':{}},{'error':{'code':404}}]);c=Client()
    def factory(cfg):calls.append(cfg.model);return p
    run_session(c,CONFIGURED,factory)
    assert calls==[RECOMMENDED_MODEL] and c.sent[-1]=={'error':'provider_model_unavailable'}


def test_handshake_unavailable_can_fallback_but_network_error_cannot():
    class Missing(Exception):status_code=404
    calls=[]
    def factory(cfg):
        calls.append(cfg.model)
        if len(calls)==1:raise Missing('private-key-secret')
        return Provider([{'setupComplete':{}},{'goAway':{}}])
    c=Client();run_session(c,CONFIGURED,factory)
    assert calls==[RECOMMENDED_MODEL,FALLBACK]
    assert provider_failure(OSError('private')).category=='provider_network_error'
    calls=[]
    def offline(cfg):calls.append(cfg.model);raise OSError('private-key-secret')
    c=Client();run_session(c,CONFIGURED,offline)
    assert len(calls)==1 and c.sent[-1]=={'error':'provider_network_error'}


def test_network_loss_after_ready_requires_explicit_new_session():
    p=Provider([{'setupComplete':{}},OSError('private')]);c=Client()
    run_session(c,CONFIGURED,lambda _:p)
    assert c.sent[-2]=={'error':'provider_network_error'}
    assert c.sent[-1]=={'status':'reconnect_required','reason':'network_error','activeModel':RECOMMENDED_MODEL,'contextPreserved':False}


def test_watchdog_is_running_before_first_setup_send(monkeypatch):
    import live_transport
    started=[]
    class Timer:
        def __init__(self,seconds,callback):pass
        def start(self):started.append(True)
        def cancel(self):pass
    class GuardedProvider(Provider):
        def send(self,value):
            assert started, 'setup send must be covered by watchdog'
            super().send(value)
    monkeypatch.setattr(live_transport.threading,'Timer',Timer)
    p=GuardedProvider([{'setupComplete':{}},{'goAway':{}}])
    run_session(Client(),CONFIGURED,lambda _:p)
    assert p.closed and len(p.sent)==1
