"""Account voice metadata and existing previews only; never synthesis or agent mutation."""
import os
import json
from urllib.parse import urlsplit
import requests
from flask import Blueprint, current_app, request, Response
from flask_login import current_user
from models import Company
from routes.managed_live_context import _guard, _reply, _store, _ID, _scope

bp = Blueprint('live_voices', __name__)
_API = 'https://api.elevenlabs.io'

class VoiceUnavailable(Exception):
    pass


def _agent_id():
    value = current_app.config.get('NEXUS_LIVE_AGENT_ID') or os.environ.get('NEXUS_LIVE_AGENT_ID')
    if not isinstance(value, str) or not _ID.fullmatch(value) or not value.startswith('agent_'):
        raise VoiceUnavailable()
    return value


def _get(path, **params):
    key = os.environ.get('ELEVENLABS_API_KEY')
    if not key:
        raise VoiceUnavailable()
    try:
        response = requests.get(_API + path, params=params, headers={'xi-api-key': key}, timeout=(3, 10), allow_redirects=False)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise VoiceUnavailable()
        return data
    except (requests.RequestException, ValueError, TypeError):
        raise VoiceUnavailable() from None


def _company(company_id):
    return Company.query.filter_by(id=company_id, status='active').first()


def _preference(company_id, value=None, save=False):
    agent_id = _agent_id()
    with _store() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS voice_preferences (
            user_id INTEGER NOT NULL, company_id INTEGER NOT NULL, agent_id TEXT NOT NULL,
            voice_id TEXT NOT NULL, PRIMARY KEY(user_id,company_id,agent_id))''')
        owner = (int(current_user.get_id()), company_id, agent_id)
        if save and value is None:
            conn.execute('DELETE FROM voice_preferences WHERE user_id=? AND company_id=? AND agent_id=?', owner)
        elif save:
            conn.execute('INSERT INTO voice_preferences VALUES(?,?,?,?) ON CONFLICT(user_id,company_id,agent_id) DO UPDATE SET voice_id=excluded.voice_id', (*owner, value))
        row = conn.execute('SELECT voice_id FROM voice_preferences WHERE user_id=? AND company_id=? AND agent_id=?', owner).fetchone()
        return row['voice_id'] if row else None



def _agent_preference(company_id, omni_agent, value=None, save=False):
    with _store() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS agent_voice_preferences (user_id INTEGER NOT NULL, company_id INTEGER NOT NULL, provider_agent_id TEXT NOT NULL, omni_agent TEXT NOT NULL, voice_id TEXT, PRIMARY KEY(user_id,company_id,provider_agent_id,omni_agent))')
        owner = (int(current_user.get_id()), company_id, _agent_id(), omni_agent)
        if save:
            conn.execute('INSERT INTO agent_voice_preferences VALUES(?,?,?,?,?) ON CONFLICT(user_id,company_id,provider_agent_id,omni_agent) DO UPDATE SET voice_id=excluded.voice_id', (*owner, value))
        row = conn.execute('SELECT voice_id FROM agent_voice_preferences WHERE user_id=? AND company_id=? AND provider_agent_id=? AND omni_agent=?', owner).fetchone()
        return (True, row['voice_id']) if row else (False, None)


def _effective_preference(company_id, omni_agent=None):
    if omni_agent:
        found, voice_id = _agent_preference(company_id, omni_agent)
        if found:
            return voice_id, 'agent_choice' if voice_id else 'agent_default'
    voice_id = _preference(company_id)
    return voice_id, 'company_choice' if voice_id else 'agent_default'


def _persona_suggestion(omni_agent, company_id, model):
    path = current_app.config.get('NEXUS_LIVE_AGENT_VOICES_FILE') or os.environ.get('NEXUS_LIVE_AGENT_VOICES_FILE')
    if not path or not omni_agent:
        return None
    try:
        with open(path, encoding='utf-8') as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            return None
        item = json.loads(raw).get(omni_agent)
        if not isinstance(item, dict):
            return None
        voice = _voice(item.get('voiceId'), model)
        return {'voice': _safe(voice, company_id, model), 'reason': str(item.get('reason', 'Sugestão configurada; aguarda sua escolha.'))[:800],
            'personaSource': str(item.get('personaSource', 'configuração administrativa'))[:200], 'applied': False}
    except (OSError, ValueError, TypeError, AttributeError, VoiceUnavailable):
        return None


def _agent():
    data = _get('/v1/convai/agents/' + _agent_id())
    tts = data.get('conversation_config', {}).get('tts', {})
    override = data.get('platform_settings', {}).get('overrides', {}).get('conversation_config_override', {}).get('tts', {}).get('voice_id') is True
    if not _ID.fullmatch(str(tts.get('voice_id', ''))) or not tts.get('model_id'):
        raise VoiceUnavailable()
    return tts, override


def _preview_url(voice):
    value = voice.get('preview_url')
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    # Exact public preview hosts only. Never forward credentials, follow redirects,
    # or accept a URL from the browser. Unknown hosts remain unavailable.
    if parsed.scheme != 'https' or parsed.username or parsed.password or port not in (None, 443):
        return None
    if parsed.hostname == 'storage.googleapis.com' and parsed.path.startswith('/eleven-public-prod/'):
        return value
    if parsed.hostname == 'cdn.elevenlabs.io':
        return value
    return None


def _eligible(voice, model):
    if voice.get('safety_control', 'NONE') != 'NONE':
        return False
    verification = voice.get('voice_verification') or {}
    if verification.get('requires_verification') and not verification.get('is_verified'):
        return False
    if not (voice.get('is_owner') is True or voice.get('permission_on_resource') in ('admin', 'editor', 'viewer') or voice.get('category') == 'premade'):
        return False
    category = voice.get('category')
    if category == 'professional':
        return (voice.get('fine_tuning') or {}).get('state', {}).get(model) == 'fine_tuned'
    return category in ('premade', 'cloned', 'generated')


def _voice(voice_id, model):
    if not isinstance(voice_id, str) or not _ID.fullmatch(voice_id):
        raise VoiceUnavailable()
    # Search scoped to the authenticated provider account, then re-read the detail.
    found = _get('/v2/voices', voice_ids=voice_id, page_size=1, include_total_count=False)
    if not any(v.get('voice_id') == voice_id for v in found.get('voices', [])):
        raise VoiceUnavailable()
    voice = _get('/v1/voices/' + voice_id)
    if voice.get('voice_id') != voice_id or not _eligible(voice, model):
        raise VoiceUnavailable()
    return voice


def _safe(voice, company_id, model):
    return {'id': voice['voice_id'], 'name': str(voice.get('name') or 'Voz sem nome')[:160],
            'language': str((voice.get('labels') or {}).get('language', ''))[:40],
            'eligible': _eligible(voice, model),
            'previewUrl': f'/api/live/voices/{company_id}/{voice["voice_id"]}/preview' if _preview_url(voice) else None}


def session_voice(company_id, omni_agent=None):
    """Called only on a new authorized start. No preference = no new API dependency."""
    selected, _ = _effective_preference(company_id, omni_agent)
    if not selected:
        return {}
    tts, override = _agent()
    voice = _voice(selected, tts['model_id'])
    if not override:
        raise VoiceUnavailable()  # Never silently start with the wrong saved voice.
    return {'voiceId': voice['voice_id'], 'voiceName': str(voice.get('name') or '')[:160]}


@bp.get('/api/live/voices/<int:company_id>')
def catalog(company_id):
    denied = _guard()
    if denied is not None:
        return denied
    if _company(company_id) is None:
        return _reply({'error': 'scope_denied'}, 403)
    if set(request.args) - {'cursor', 'search', 'agent'} or len(request.args.get('cursor', '')) > 2048 or len(request.args.get('search', '')) > 100:
        return _reply({'error': 'invalid_query'}, 400)
    omni_agent = request.args.get('agent')
    if omni_agent is not None and _scope(company_id, omni_agent) is None:
        return _reply({'error': 'scope_denied'}, 403)
    try:
        tts, override = _agent()
        params = {'page_size': 25, 'include_total_count': False}
        if request.args.get('cursor'):
            params['next_page_token'] = request.args['cursor']
        if request.args.get('search'):
            params['search'] = request.args['search']
        data = _get('/v2/voices', **params)
        voices = [_safe(v, company_id, tts['model_id']) for v in data.get('voices', []) if isinstance(v, dict) and _ID.fullmatch(str(v.get('voice_id', '')))]
        token = data.get('next_page_token')
        if data.get('has_more') is True and (not isinstance(token, str) or not token or len(token) > 2048):
            raise VoiceUnavailable()
        current = _get('/v1/voices/' + tts['voice_id'])
        selected, preference_source = _effective_preference(company_id, omni_agent)
        suggestion = _persona_suggestion(omni_agent, company_id, tts['model_id'])
        try:
            saved = _get('/v1/voices/' + selected) if selected else None
        except VoiceUnavailable:
            saved = {'voice_id': selected, 'name': 'Preferência indisponível; escolha outra voz ou o padrão', 'category': 'unavailable'}
        return _reply({'voices': voices, 'hasMore': data.get('has_more') is True,
            'nextCursor': token if data.get('has_more') is True else None, 'current': _safe(current, company_id, tts['model_id']),
            'saved': _safe(saved, company_id, tts['model_id']) if saved else None,
            'preferenceSource': preference_source, 'personaSuggestion': suggestion, 'overrideAllowed': override, 'applies': 'next_conversation' if override else 'requires_agent_permission'})
    except (VoiceUnavailable, KeyError, TypeError, ValueError):
        return _reply({'error': 'voice_catalog_unavailable'}, 503)


@bp.put('/api/live/voices/<int:company_id>/preference')
def save_preference(company_id):
    denied = _guard(write=True)
    if denied is not None:
        return denied
    if _company(company_id) is None:
        return _reply({'error': 'scope_denied'}, 403)
    omni_agent = request.args.get('agent')
    if set(request.args) - {'agent'} or (omni_agent is not None and _scope(company_id, omni_agent) is None):
        return _reply({'error': 'scope_denied'}, 403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'voiceId'}:
        return _reply({'error': 'invalid_preference'}, 400)
    try:
        tts, override = _agent()
        voice = _voice(data['voiceId'], tts['model_id']) if data['voiceId'] is not None else None
        # Saving a next-call preference does not alter any existing conversation.
        if omni_agent:
            _agent_preference(company_id, omni_agent, voice['voice_id'] if voice else None, save=True)
        else:
            _preference(company_id, voice['voice_id'] if voice else None, save=True)
        return _reply({'saved': _safe(voice, company_id, tts['model_id']) if voice else None, 'preferenceSource': ('agent_choice' if voice else 'agent_default') if omni_agent else 'company_choice', 'overrideAllowed': override,
            'applies': 'next_conversation' if override else 'requires_agent_permission'})
    except VoiceUnavailable:
        return _reply({'error': 'voice_not_permitted_or_compatible'}, 409)


@bp.get('/api/live/voices/<int:company_id>/<voice_id>/preview')
def preview(company_id, voice_id):
    denied = _guard()
    if denied is not None:
        return denied
    if _company(company_id) is None:
        return _reply({'error': 'scope_denied'}, 403)
    try:
        tts, _ = _agent()
        voice = _voice(voice_id, tts['model_id'])
        url = _preview_url(voice)
        if not url:
            raise VoiceUnavailable()
        with requests.get(url, stream=True, timeout=(3, 10), allow_redirects=False) as response:
            response.raise_for_status()
            mime = response.headers.get('Content-Type', '').split(';')[0]
            if mime not in ('audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/mp4') or 300 <= response.status_code < 400:
                raise VoiceUnavailable()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 5 * 1024 * 1024:
                    raise VoiceUnavailable()
                chunks.append(chunk)
        return Response(b''.join(chunks), mimetype=mime, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    except (VoiceUnavailable, requests.RequestException):
        return _reply({'error': 'existing_preview_unavailable'}, 503)
