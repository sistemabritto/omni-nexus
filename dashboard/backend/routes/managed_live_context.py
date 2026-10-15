"""Personal Nexus Live read tool through the authenticated browser; no provider calls."""
import os
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import requests
from flask import Blueprint, current_app, g, jsonify, request
from flask_login import current_user
from models import Company, User, TICKET_STATUSES, has_permission, has_agent_access
from routes.agents import AGENTS_DIR
from routes._helpers import WORKSPACE
from routes.terminal_proxy import TERMINAL_HTTP_BASE

bp = Blueprint('managed_live_context', __name__)
_ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def _reply(data, status=200):
    response = jsonify(data)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response


def _guard(write=False):
    if not current_user.is_authenticated:
        return _reply({'error': 'unauthorized'}, 401)
    if getattr(g, 'auth_via_api_token', False):
        return _reply({'error': 'cookie_session_required'}, 403)
    allowed = current_app.config.get('NEXUS_LIVE_USER_ID') or os.environ.get('NEXUS_LIVE_USER_ID')
    if not allowed or not str(allowed).isdigit():
        return _reply({'error': 'personal_access_not_configured'}, 503)
    person = User.query.filter_by(id=int(allowed), is_active=True).first()
    if person is None or str(current_user.get_id()) != str(person.id):
        return _reply({'error': 'personal_access_denied'}, 403)
    # The current app has global company roles, not a per-company membership ACL.
    # This narrow MVP admits the personally configured administrator only.
    if person.role != 'admin' or not has_permission(person.role, 'goals', 'view') or not has_permission(person.role, 'agents', 'view'):
        return _reply({'error': 'permission_denied'}, 403)
    origin = request.headers.get('Origin')
    if (write and not origin) or (origin and (urlsplit(origin).netloc != request.host or urlsplit(origin).scheme != 'https')):
        return _reply({'error': 'origin_forbidden'}, 403)
    return None


def _scope(company_id, agent_name):
    if type(company_id) is not int or not isinstance(agent_name, str) or not _ID.fullmatch(agent_name):
        return None
    company = Company.query.filter_by(id=company_id, status='active').first()
    path = AGENTS_DIR / (agent_name + '.md')
    if company is None or not path.is_file() or not has_agent_access(current_user.role, agent_name):
        return None
    return company


@contextmanager
def _store():
    path = Path(current_app.config.get('NEXUS_LIVE_CONTEXT_DB') or WORKSPACE / 'dashboard/data/nexus-live-context.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS contexts (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, company_id INTEGER NOT NULL,
        agent_name TEXT NOT NULL, runtime_session_id TEXT NOT NULL UNIQUE,
        conversation_id TEXT UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@bp.get('/api/live/omni-context/options')
def context_options():
    denied = _guard()
    if denied is not None:
        return denied
    companies = [{'id': c.id, 'name': c.name} for c in Company.query.filter_by(status='active').order_by(Company.id).all()]
    agents = [p.stem for p in sorted(AGENTS_DIR.glob('*.md')) if _ID.fullmatch(p.stem) and has_agent_access(current_user.role, p.stem)]
    return _reply({'companies': companies, 'agents': agents, 'consumptionApproved': _consumption_approved(), 'presentationGroups': _presentation_groups(agents)})


@bp.post('/api/live/omni-context')
def create_context():
    denied = _guard(write=True)
    if denied is not None:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'companyId', 'agentName'}:
        return _reply({'error': 'invalid_context'}, 400)
    company = _scope(data['companyId'], data['agentName'])
    if company is None:
        return _reply({'error': 'scope_denied'}, 403)
    try:
        # Always create; never adopt an unowned legacy session via for-agent/reuse.
        response = requests.post(TERMINAL_HTTP_BASE + '/api/sessions/create', json={'agentName': data['agentName']}, timeout=(3, 10), allow_redirects=False)
        response.raise_for_status()
        created = response.json()
        sid = created.get('sessionId')
        runtime = created.get('session', {})
        if created.get('success') is not True or not isinstance(sid, str) or not _ID.fullmatch(sid) or runtime.get('id') != sid or runtime.get('agentName') != data['agentName']:
            raise ValueError()
        with _store() as conn:
            cursor = conn.execute('INSERT INTO contexts(user_id,company_id,agent_name,runtime_session_id) VALUES(?,?,?,?)', (int(current_user.get_id()), company.id, data['agentName'], sid))
            context_id = cursor.lastrowid
        return _reply({'contextId': context_id, 'runtimeSessionId': sid, 'company': {'id': company.id, 'name': company.name}, 'agentName': data['agentName']}, 201)
    except (requests.RequestException, ValueError, TypeError, AttributeError, sqlite3.Error):
        return _reply({'error': 'runtime_context_unavailable'}, 503)


def _owned(context_id):
    with _store() as conn:
        row = conn.execute('SELECT * FROM contexts WHERE id=? AND user_id=?', (context_id, int(current_user.get_id()))).fetchone()
    if row is None or _scope(row['company_id'], row['agent_name']) is None:
        return None
    return row


@bp.post('/api/live/omni-context/<int:context_id>/conversation')
def link_conversation(context_id):
    denied = _guard(write=True)
    if denied is not None:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'conversationId'} or not isinstance(data['conversationId'], str) or not _ID.fullmatch(data['conversationId']):
        return _reply({'error': 'invalid_conversation'}, 400)
    row = _owned(context_id)
    if row is None:
        return _reply({'error': 'scope_denied'}, 403)
    if row['conversation_id'] and row['conversation_id'] != data['conversationId']:
        return _reply({'error': 'conversation_already_bound'}, 409)
    try:
        with _store() as conn:
            updated = conn.execute('UPDATE contexts SET conversation_id=? WHERE id=? AND user_id=? AND (conversation_id IS NULL OR conversation_id=?)', (data['conversationId'], context_id, int(current_user.get_id()), data['conversationId']))
            if updated.rowcount != 1:
                return _reply({'error': 'conversation_already_bound'}, 409)
        return _reply({'bound': True, 'conversationIdSource': 'authenticated_browser'})
    except sqlite3.IntegrityError:
        return _reply({'error': 'conversation_already_bound'}, 409)


@bp.post('/api/live/omni-context/<int:context_id>/read')
def read_context(context_id):
    denied = _guard(write=True)
    if denied is not None:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'conversationId'}:
        return _reply({'error': 'invalid_read'}, 400)
    row = _owned(context_id)
    if row is None or not row['conversation_id'] or data['conversationId'] != row['conversation_id']:
        return _reply({'error': 'scope_denied'}, 403)
    try:
        response = requests.get(TERMINAL_HTTP_BASE + '/api/sessions/' + row['runtime_session_id'], timeout=(3, 10), allow_redirects=False)
        response.raise_for_status()
        runtime = response.json()
        if runtime.get('id') != row['runtime_session_id']:
            raise ValueError()
        company = _scope(row['company_id'], row['agent_name'])
        if company is None:
            return _reply({'error': 'scope_denied'}, 403)
        from routes.tickets import read_company_ticket_page
        def ticket_page(**kwargs):
            result = read_company_ticket_page(company.id, **kwargs)
            return None if isinstance(result, tuple) else result.get_json()
        page = ticket_page(statuses=('open', 'in_progress', 'blocked', 'review'), limit=10)
        if page is None:
            return _reply({'error': 'ticket_access_denied'}, 403)
        counts = {}
        for status in TICKET_STATUSES:
            count = ticket_page(statuses=(status,))
            if count is None:
                return _reply({'error': 'ticket_access_denied'}, 403)
            counts[status] = count['total']
        tasks = {'source': '/api/tickets', 'total': sum(counts.values()), 'byStatus': counts, 'pendingTotal': page['total'], 'pendingLimit': 10, 'pending': [{key: ticket.get(key) for key in ('id', 'title', 'status', 'priority', 'due_date', 'blocked_reason', 'requires_human_approval')} for ticket in page['tickets']]}
        return _reply({'company': {'id': company.id, 'name': company.name}, 'agentName': row['agent_name'], 'runtimeSessionId': row['runtime_session_id'], 'sessionName': str(runtime.get('name', ''))[:200], 'active': runtime.get('active') is True, 'tasks': tasks})
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return _reply({'error': 'runtime_context_unavailable'}, 503)


def _consumption_approved():
    return current_app.config.get('NEXUS_LIVE_COST_APPROVED') is True or os.environ.get('NEXUS_LIVE_COST_APPROVED') == 'true'


@bp.post('/api/live/omni-context/<int:context_id>/signed-session')
def signed_session(context_id):
    denied = _guard(write=True)
    if denied is not None:
        return denied
    if request.get_json(silent=True) != {}:
        return _reply({'error': 'invalid_request'}, 400)
    row = _owned(context_id)
    if row is None:
        return _reply({'error': 'scope_denied'}, 403)
    if row['conversation_id']:
        return _reply({'error': 'conversation_already_bound'}, 409)
    if not _consumption_approved():
        return _reply({'error': 'consumption_not_approved'}, 403)
    agent_id = current_app.config.get('NEXUS_LIVE_AGENT_ID') or os.environ.get('NEXUS_LIVE_AGENT_ID')
    if not isinstance(agent_id, str) or not agent_id.startswith('agent_') or not _ID.fullmatch(agent_id):
        return _reply({'error': 'provider_agent_not_configured'}, 503)
    key = os.environ.get('ELEVENLABS_API_KEY')
    if not key:
        return _reply({'error': 'provider_not_configured'}, 503)
    from routes.live_voices import session_voice, VoiceUnavailable
    try:
        voice = session_voice(row['company_id'])
        response = requests.get('https://api.elevenlabs.io/v1/convai/conversation/get-signed-url', params={'agent_id': agent_id}, headers={'xi-api-key': key}, timeout=(3, 10), allow_redirects=False)
        response.raise_for_status()
        signed_url = response.json().get('signed_url')
        parsed = urlsplit(signed_url) if isinstance(signed_url, str) else None
        if parsed is None or parsed.scheme != 'wss' or parsed.hostname != 'api.elevenlabs.io' or parsed.path != '/v1/convai/conversation':
            raise ValueError()
        return _reply({'signedUrl': signed_url, **voice})
    except (requests.RequestException, ValueError, TypeError, AttributeError, VoiceUnavailable):
        return _reply({'error': 'provider_or_saved_voice_unavailable'}, 503)


def _presentation_groups(agents):
    """Optional server-owned presentation map; no organization metadata in source."""
    path = current_app.config.get('NEXUS_LIVE_AGENT_GROUPS_FILE') or os.environ.get('NEXUS_LIVE_AGENT_GROUPS_FILE')
    if not path:
        return {}
    try:
        with open(path, encoding='utf-8') as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict) or len(data) > 64:
            return {}
        allowed = set(agents)
        seen = set()
        result = {}
        for label, names in data.items():
            if not isinstance(label, str) or not 1 <= len(label) <= 80 or not isinstance(names, list):
                continue
            members = [name for name in names if isinstance(name, str) and name in allowed and name not in seen]
            members = list(dict.fromkeys(members))
            seen.update(members)
            if members:
                result[label] = members
        return result
    except (OSError, ValueError, TypeError):
        return {}
