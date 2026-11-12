"""Bounded audio-only Gemini bridge. No credentials read until explicit activation."""
import base64
import binascii
import json
import logging
import socket
import os
import sqlite3
import time
import threading
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlencode

from live_model_policy import (COMPATIBLE_MODELS, MAX_PROVIDER_ATTEMPTS, ProviderFailure, csv_models, provider_failure)

ENDPOINT = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'


@dataclass(frozen=True)
class LiveConfig:
    enabled: bool = False
    free_verified: bool = False
    model: str = ''
    key: str = field(default='', repr=False)
    fallback_models: tuple = ()
    fallback_blocked_models: tuple = ()

    @classmethod
    def environment(cls):
        enabled = os.environ.get('GEMINI_LIVE_ENABLED') == 'true'
        verified = os.environ.get('GEMINI_FREE_TIER_VERIFIED') == 'true'
        # Disabled status never even reads the key.
        model = os.environ.get('GEMINI_LIVE_MODEL', '')
        requested = tuple(x for x in csv_models(os.environ.get('GEMINI_LIVE_FALLBACK_MODELS', '')) if x != model)
        quota_verified = csv_models(os.environ.get('GEMINI_LIVE_VERIFIED_MODELS', ''))
        eligible = tuple(x for x in requested if x in quota_verified)
        blocked = tuple(x for x in requested if x not in quota_verified)
        return cls(enabled, verified, model,
                   os.environ.get('GEMINI_API_KEY', '') if enabled and verified else '',
                   eligible, blocked)

    def status_payload(self):
        model = self.model if self.model in COMPATIBLE_MODELS else None
        return {'enabled': bool(self.ready), 'freeTierVerified': bool(self.ready),
                'configuredModel': model, 'activeModel': None,
                'fallbackModels': list(self.fallback_models),
                'fallbackBlockedModels': list(self.fallback_blocked_models),
                'maxProviderAttempts': MAX_PROVIDER_ATTEMPTS,
                'fallbackPolicy': 'startup_model_unavailable_only',
                'contextResumptionSupported': False}

    @property
    def ready(self):
        return self.enabled and self.free_verified and bool(self.key) and self.model in COMPATIBLE_MODELS


class LeaseStore:
    """Cross-worker limits. All dashboard workers must share this SQLite path."""
    def __init__(self, path):
        self.path = str(path)

    def acquire(self, user, now=None):
        now = time.time() if now is None else now
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute('CREATE TABLE IF NOT EXISTS live_leases (id TEXT PRIMARY KEY, user TEXT, expires REAL, started REAL, active INTEGER)')
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM live_leases WHERE expires < ?', (now,))
            rows = db.execute('SELECT user, started, active FROM live_leases').fetchall()
            if sum(row[2] for row in rows) >= 4 or any(row[0] == user and (row[2] or now-row[1] < 10) for row in rows):
                return None
            token = uuid.uuid4().hex
            db.execute('INSERT INTO live_leases VALUES (?, ?, ?, ?, 1)', (token, user, now+140, now))
            return token

    def release(self, token):
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute('UPDATE live_leases SET active=0 WHERE id=?', (token,))


def open_gemini(config):
    # Fixed TLS endpoint, no custom host, redirects or client-selected model/key.
    # websockets exceptions/URL must never reach logs or browser.
    from websockets.sync.client import connect
    silent = logging.Logger('omninexus.live.provider')
    silent.disabled = True
    silent.propagate = False
    return connect(ENDPOINT + '?' + urlencode({'key': config.key}),
                   open_timeout=5, close_timeout=1, max_size=262144, max_queue=8,
                   compression=None, proxy=None, logger=silent)


def setup_message(model):
    return {'setup': {
        'model': 'models/' + model,
        'generationConfig': {'responseModalities': ['AUDIO'], 'maxOutputTokens': 1024},
        'systemInstruction': {'parts': [{'text': 'Converse exclusivamente em português brasileiro. Seja breve. Você não tem ferramentas nem acesso a dados de produção.'}]},
        'inputAudioTranscription': {}, 'outputAudioTranscription': {},
        'realtimeInputConfig': {'activityHandling': 'START_OF_ACTIVITY_INTERRUPTS'},
    }}


class ProtocolError(Exception):
    pass


def parse_audio(raw):
    if not isinstance(raw, str) or len(raw) > 32000:
        raise ProtocolError()
    try:
        msg = json.loads(raw)
        if not isinstance(msg, dict) or set(msg) != {'audio'} or not isinstance(msg['audio'], str):
            raise ProtocolError()
        data = base64.b64decode(msg['audio'], validate=True)
        if not data or len(data) % 2 or len(data) > 16000:
            raise ProtocolError()
        return msg['audio'], len(data)
    except (ValueError, TypeError, binascii.Error):
        raise ProtocolError() from None


def translate(raw):
    if not isinstance(raw, (str, bytes)) or len(raw) > 262144:
        raise ProtocolError()
    msg = json.loads(raw)
    if not isinstance(msg, dict) or 'toolCall' in msg:
        raise ProtocolError()
    if 'error' in msg:
        if not isinstance(msg['error'], dict):
            raise ProtocolError()
        raise provider_failure(msg['error'])
    out = []
    if 'setupComplete' in msg:
        out.append({'status': 'ready'})
    if 'goAway' in msg:
        return [{'status': 'reconnect_required'}]
    content = msg.get('serverContent', {})
    if content.get('interrupted'):
        out.append({'interrupted': True})
    for part in content.get('modelTurn', {}).get('parts', []):
        audio = part.get('inlineData', {})
        if audio.get('mimeType', '').split(';')[0] == 'audio/pcm':
            if audio.get('mimeType') != 'audio/pcm;rate=24000':
                raise ProtocolError()
            data = base64.b64decode(audio['data'], validate=True)
            if len(data) % 2:
                raise ProtocolError()
            out.append({'audio': audio['data']})
    for name, role in [('inputTranscription', 'user'), ('outputTranscription', 'model')]:
        text = content.get(name, {}).get('text')
        if isinstance(text, str):
            out.append({'transcript': text[:4000], 'role': role})
    if content.get('turnComplete'):
        out.append({'status': 'listening'})
    return out


def run_session(client, config, provider_factory=open_gemini, clock=time.monotonic):
    """Single handler owns both sockets; polling bounds cancellation latency.

    No payloads or exception strings are logged. No automatic reconnect, tools or session persistence. Startup fallback is
    capped, quota-gated and limited to model-unavailable errors before readiness.
    """
    provider = None
    watchdog = None
    start = clock()
    ready = False
    tokens = 64000.0
    last = start
    models = tuple(dict.fromkeys((config.model,) + tuple(m for m in config.fallback_models if m in COMPATIBLE_MODELS)))[:MAX_PROVIDER_ATTEMPTS]
    attempt = 0
    active_model = None
    logger = logging.getLogger('omninexus.live.lifecycle')
    def send(value):
        client.send(json.dumps(value))
    try:
        if not config.ready:
            send({'error': 'live_disabled'})
            return
        def connect_next(reason):
            nonlocal provider, attempt
            while attempt < len(models):
                previous = models[attempt-1] if attempt else None
                if provider is not None:
                    try:
                        provider.close()
                    except Exception:
                        pass
                    provider = None
                model = models[attempt]
                attempt += 1
                if previous is not None:
                    send({'event': 'model_switch', 'fromModel': previous, 'toModel': model,
                          'reason': reason, 'attempt': attempt, 'maxAttempts': MAX_PROVIDER_ATTEMPTS,
                          'contextPreserved': False})
                send({'event': 'model_attempt', 'configuredModel': config.model, 'model': model,
                      'attempt': attempt, 'maxAttempts': MAX_PROVIDER_ATTEMPTS,
                      'reason': reason, 'contextPreserved': False})
                logger.info('live_model_attempt model=%s attempt=%d reason=%s', model, attempt, reason)
                try:
                    provider = provider_factory(replace(config, model=model))
                    return
                except Exception as error:
                    failure = provider_failure(error)
                    if failure.category != 'provider_model_unavailable' or attempt >= len(models):
                        raise failure from None
                    reason = 'model_unavailable'
        connect_next('initial')
        # Wall-clock watchdog also interrupts a blocked provider send.
        def expire():
            # Shutdown interrupts blocked socket sends without waiting for a
            # graceful close frame or an unresponsive peer.
            for peer, attr in ((client, 'sock'), (provider, 'socket')):
                raw_socket = getattr(peer, attr, None)
                if raw_socket is not None:
                    try:
                        raw_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
            for peer in (provider, client):
                try:
                    peer.close()
                except Exception:
                    pass
        watchdog = threading.Timer(max(0, 120 - (clock() - start)), expire)
        watchdog.daemon = True
        watchdog.start()
        def send_setup():
            while True:
                try:
                    provider.send(json.dumps(setup_message(models[attempt-1])))
                    return
                except Exception as error:
                    failure = provider_failure(error)
                    if failure.category != 'provider_model_unavailable' or attempt >= len(models):
                        raise failure from None
                    connect_next('model_unavailable')
        send_setup()
        while getattr(client, 'connected', True):
            now = clock()
            if now-start >= 120 or (not ready and now-start >= 10):
                send({'error': 'session_limit' if ready else 'setup_timeout'})
                break
            raw = client.receive(timeout=0.02)
            if raw is not None:
                if not ready:
                    raise ProtocolError()
                audio, size = parse_audio(raw)
                tokens = min(64000, tokens + (now-last)*40000)
                last = now
                if size > tokens:
                    send({'error': 'audio_rate_limit'})
                    break
                tokens -= size
                provider.send(json.dumps({'realtimeInput': {'audio': {'data': audio, 'mimeType': 'audio/pcm;rate=16000'}}}))
            if not getattr(client, 'connected', True):
                break
            try:
                incoming = provider.recv(timeout=0.02)
            except TimeoutError:
                continue
            try:
                events = translate(incoming)
            except ProviderFailure as failure:
                if not ready and failure.category == 'provider_model_unavailable' and attempt < len(models):
                    connect_next('model_unavailable')
                    send_setup()
                    continue
                raise
            for event in events:
                if event.get('status') == 'ready':
                    if ready:
                        raise ProtocolError()
                    ready = True
                    active_model = models[attempt-1]
                    send({'event': 'model_active', 'activeModel': active_model,
                          'attempt': attempt, 'contextPreserved': False})
                    logger.info('live_model_active model=%s attempt=%d', active_model, attempt)
                if event.get('status') == 'reconnect_required':
                    event.update(reason='go_away', activeModel=active_model, contextPreserved=False)
                send(event)
                if event.get('status') == 'reconnect_required':
                    return
    except ProtocolError:
        try:
            send({'error': 'invalid_audio_or_provider_protocol'})
        except Exception:
            pass
    except Exception as error:
        failure = provider_failure(error)
        logger.info('live_provider_failure category=%s attempt=%d', failure.category, attempt)
        try:
            send({'error': failure.category})
            if ready and failure.category == 'provider_network_error':
                send({'status': 'reconnect_required', 'reason': 'network_error',
                      'activeModel': active_model, 'contextPreserved': False})
        except Exception:
            pass
    finally:
        if watchdog is not None:
            watchdog.cancel()
        if provider is not None:
            try:
                provider.close()
            except Exception:
                pass
        try:
            client.close()
        except Exception:
            pass
