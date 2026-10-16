"""Personal Nexus Live read tool through the authenticated browser; no provider calls."""
import os
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import requests
from flask import Blueprint, current_app, g, jsonify, request, send_file
from flask_login import current_user
from sqlalchemy import or_
from live_conversation_store import ContinuityDenied
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
    except (requests.RequestException, ValueError, TypeError, AttributeError, sqlite3.Error, ContinuityDenied):
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
        display_name = str(current_user.display_name or '').strip()[:120]
        authenticated_user = {'displayName': display_name or None, 'nameAvailable': bool(display_name), 'source': 'authenticated_profile'}
        payload = {'authenticatedUser': authenticated_user, 'company': {'id': company.id, 'name': company.name}, 'agentName': row['agent_name'], 'runtimeSessionId': row['runtime_session_id'], 'sessionName': str(runtime.get('name', ''))[:200], 'active': runtime.get('active') is True, 'tasks': tasks, **({'agentIdentity': _agent_identity(row), 'continuity': _continuity_payload(row), 'previousWork': _previous_work_for_context(row)} if current_app.config.get('NEXUS_LIVE_CONTINUITY_ENABLED') is True else {})}
        if current_app.config.get('NEXUS_LIVE_CONTINUITY_ENABLED') is True:
            query_result = _query_for_current_turn(row)
            while (query_result['memory'] or query_result.get('documents', {}).get('results')) and len(json.dumps({**payload, 'queryResult': query_result}, ensure_ascii=False)) > 23500:
                (query_result['memory'] or query_result['documents']['results']).pop()
            if len(json.dumps({**payload, 'queryResult': query_result}, ensure_ascii=False)) > 23500:
                query_result = {'memory': [], 'coverage': 'context_budget_exhausted'}
            payload['queryResult'] = query_result
        return _reply(payload)
    except (requests.RequestException, ValueError, TypeError, AttributeError, sqlite3.Error, ContinuityDenied):
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
    except (requests.RequestException, ValueError, TypeError, AttributeError, VoiceUnavailable, sqlite3.Error, ContinuityDenied):
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


# Opt-in continuity; no legacy source is imported and no provider call is made.
def _continuity_store(row):
    from live_conversation_store import ConversationStore, Principal
    if current_app.config.get('NEXUS_LIVE_CONTINUITY_ENABLED') is not True:
        return None, None
    path = current_app.config.get('NEXUS_LIVE_CONTINUITY_DB') or WORKSPACE / 'dashboard/data/live-continuity.sqlite3'
    principal = Principal(str(current_user.get_id()), row['company_id'])
    def allowed(p, _cid):
        owned = _owned(row['id'])
        return (owned is not None and p == principal and _guard() is None
                and has_permission(current_user.role, 'memory', 'view'))
    return ConversationStore(path, allowed), principal


def _continuity_id(row, *, new=False):
    store, principal = _continuity_store(row)
    if store is None:
        return None
    # A binding is immutable for a runtime context. Explicit new conversation
    # needs a fresh context to avoid redirecting an already-open provider call.
    with _store() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS continuity_bindings(context_id INTEGER PRIMARY KEY, logical_id TEXT NOT NULL)')
        bound = conn.execute('SELECT logical_id FROM continuity_bindings WHERE context_id=?', (row['id'],)).fetchone()
        if bound:
            if new:
                raise ValueError('fresh_context_required')
            return bound['logical_id']
    # Do not hold the context DB write transaction while ACL checks reopen it.
    cid = store.create_explicit(principal) if new else store.latest(principal, create_if_missing=True)
    with _store() as conn:
        conn.execute('INSERT OR IGNORE INTO continuity_bindings VALUES(?,?)', (row['id'], cid))
        return conn.execute('SELECT logical_id FROM continuity_bindings WHERE context_id=?', (row['id'],)).fetchone()['logical_id']


def _continuity_payload(row):
    cid = _continuity_id(row)
    if cid is None:
        return {'status': 'disabled'}
    store, principal = _continuity_store(row)
    snap = store.snapshot(principal, cid, history_limit=30)
    # Current revisions only. Never send audit history, retracted facts or the
    # unbounded full structured summary to a provider.
    selected = []
    remaining = 6000
    for item in reversed(snap['current_context']):
        item = _visible_event(row, dict(item))
        if item.get('retracted'):
            continue
        item['text'] = item['text'][:600]
        size = len(json.dumps(item, ensure_ascii=False))
        if size > remaining:
            break
        selected.append(item)
        remaining -= size
    structured = {'facts': [], 'inferences': [], 'decisions': [], 'pending': [], 'preferences': []}
    buckets = {'fact': 'facts', 'decision': 'decisions', 'pending': 'pending', 'preference': 'preferences'}
    for item in reversed(selected):
        if item['kind'] not in ('transcript', 'progress', 'result'):
            bucket = buckets.get(item['kind'], 'inferences') if item['verified'] else 'inferences'
            structured[bucket].append(item)
    return {'status': 'available', 'logicalConversationId': cid,
            'summaryRevision': snap['summary_revision'], 'summary': structured,
            'kind': 'untrusted_reference_data', 'current': list(reversed(selected)),
            'truncated': len(selected) < len(snap['current_context'])}


def _continuity_request(context_id):
    denied = _guard(write=True)
    if denied is not None:
        return None, None, denied
    if current_app.config.get('NEXUS_LIVE_CONTINUITY_ENABLED') is not True:
        return None, None, _reply({'error': 'continuity_disabled'}, 503)
    row = _owned(context_id)
    data = request.get_json(silent=True)
    if (row is None or not isinstance(data, dict) or not row['conversation_id']
            or data.get('conversationId') != row['conversation_id']):
        return None, None, _reply({'error': 'scope_denied'}, 403)
    if not has_permission(current_user.role, 'memory', 'view'):
        return None, None, _reply({'error': 'memory_access_denied'}, 403)
    try:
        response = requests.get(TERMINAL_HTTP_BASE + '/api/sessions/' + row['runtime_session_id'], timeout=(3, 10), allow_redirects=False)
        response.raise_for_status()
        if response.json().get('id') != row['runtime_session_id']:
            raise ValueError()
    except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError):
        return None, None, _reply({'error': 'runtime_context_unavailable'}, 503)
    return row, data, None


@bp.post('/api/live/omni-context/<int:context_id>/continuity')
def resume_continuity(context_id):
    from live_conversation_store import ContinuityDenied
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    if set(data) not in ({'conversationId'}, {'conversationId', 'newConversation'}):
        return _reply({'error': 'invalid_request'}, 400)
    if 'newConversation' in data and data['newConversation'] is not True:
        return _reply({'error': 'invalid_request'}, 400)
    try:
        _continuity_id(row, new=data.get('newConversation', False))
        return _reply(_continuity_payload(row))
    except ContinuityDenied:
        return _reply({'error': 'scope_denied'}, 403)
    except ValueError:
        return _reply({'error': 'fresh_context_required'}, 409)
    except sqlite3.Error:
        return _reply({'error': 'continuity_unavailable'}, 503)


@bp.post('/api/live/omni-context/<int:context_id>/transcript')
def record_live_transcript(context_id):
    from live_conversation_store import ContinuityDenied
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    if (set(data) != {'conversationId', 'eventId', 'role', 'text'}
            or data['role'] not in ('user', 'assistant')
            or not isinstance(data['eventId'], str) or not _ID.fullmatch(data['eventId'])
            or not isinstance(data['text'], str) or not 1 <= len(data['text'].strip()) <= 4000):
        return _reply({'error': 'invalid_transcript'}, 400)
    try:
        cid = _continuity_id(row)
        store, principal = _continuity_store(row)
        # Browser-origin transcript is an unverified declaration, never a fact.
        # Include provider connection in key: event IDs need not be globally unique.
        key = hashlib.sha256((row['conversation_id'] + ':' + data['eventId']).encode()).hexdigest()
        result = store.record(principal, cid, kind='transcript', text=data['text'],
                              source='browser:' + data['role'] + ':' + row['conversation_id'],
                              request_key=key)
        return _reply({'saved': True, **result})
    except ContinuityDenied:
        return _reply({'error': 'scope_denied'}, 403)
    except ValueError:
        return _reply({'error': 'transcript_conflict'}, 409)
    except sqlite3.Error:
        return _reply({'error': 'continuity_unavailable'}, 503)


@bp.post('/api/live/omni-context/<int:context_id>/notes')
def record_confirmed_note(context_id):
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    required = {'conversationId', 'requestId', 'kind', 'text', 'confirmed'}
    optional = {'eventId', 'expectedRevision', 'retract'}
    if (not required <= set(data) or set(data) - required - optional
            or data['confirmed'] is not True
            or data['kind'] not in ('fact', 'decision', 'pending', 'preference')
            or not isinstance(data['requestId'], str) or not _ID.fullmatch(data['requestId'])
            or ('eventId' in data) != ('expectedRevision' in data)):
        return _reply({'error': 'explicit_confirmation_required'}, 400)
    try:
        cid = _continuity_id(row)
        store, principal = _continuity_store(row)
        result = store.record(principal, cid, kind=data['kind'], text=data['text'],
                              source='user-confirmation:' + str(current_user.get_id()), verified=True,
                              event_id=data.get('eventId'), expected_revision=data.get('expectedRevision'),
                              retract=data.get('retract', False), request_key=hashlib.sha256(('note:' + data['requestId']).encode()).hexdigest())
        return _reply({'saved': True, **result})
    except ContinuityDenied:
        return _reply({'error': 'scope_denied'}, 403)
    except (ValueError, TypeError):
        return _reply({'error': 'note_conflict_or_invalid'}, 409)
    except sqlite3.Error:
        return _reply({'error': 'continuity_unavailable'}, 503)


@bp.post('/api/live/omni-context/<int:context_id>/work-search')
def search_previous_work(context_id):
    """Search only records with explicit company ownership; never dereference files."""
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    if (set(data) != {'conversationId', 'query'} or not isinstance(data['query'], str)
            or not 1 <= len(data['query'].strip()) <= 200):
        return _reply({'error': 'invalid_query'}, 400)
    try:
        return _reply(_work_payload(row, data['query']))
    except PermissionError:
        return _reply({'error': 'ticket_access_denied'}, 403)


def _work_payload(row, query):
    from routes.tickets import read_company_ticket_page
    from models import TicketComment
    stop = {'qual', 'quais', 'sobre', 'anterior', 'anteriores', 'trabalho', 'trabalhos', 'feito', 'fizemos', 'lembra', 'voce', 'você', 'para', 'como', 'está', 'esta'}
    terms = [t for t in re.findall(r'[^\W_]+(?:-[^\W_]+)*', query.lower()) if len(t) >= 4 and t not in stop][:4]
    tickets = {}
    if not terms:
        # A fresh logical conversation has no user query yet. Show a bounded,
        # honestly labelled completed-work sample through the same ticket ACL.
        response = read_company_ticket_page(row['company_id'], statuses=('resolved', 'closed', 'archived'), limit=3)
        if isinstance(response, tuple):
            raise PermissionError()
        tickets = {ticket['id']: ticket for ticket in response.get_json()['tickets']}
    for term in terms:
        response = read_company_ticket_page(row['company_id'], limit=3, query=term)
        if isinstance(response, tuple):
            raise PermissionError()
        for ticket in response.get_json()['tickets']:
            tickets[ticket['id']] = ticket
    results = []
    for ticket in list(tickets.values())[:3]:
        if ticket.get('company_id') != row['company_id']:
            continue
        refs = []
        comments = [] if not terms else TicketComment.query.filter_by(ticket_id=ticket['id']).filter(
            or_(*(TicketComment.body.ilike('%' + term + '%') for term in terms))).order_by(TicketComment.created_at.desc()).limit(2).all()
        for comment in comments:
            refs.append({'reference': '/api/tickets/' + ticket['id'] + '/comments#' + comment.id,
                         'revision': hashlib.sha256(comment.body.encode()).hexdigest(),
                         'authoredAt': comment.created_at, 'text': comment.body[:600]})
        excerpt = {'reference': '/api/tickets/' + ticket['id'],
                   'title': ticket['title'][:200], 'status': ticket['status'],
                   'text': (ticket.get('description') or '')[:600],
                   'updatedAt': ticket['updated_at'], 'comments': refs}
        excerpt['revision'] = hashlib.sha256(json.dumps(excerpt, sort_keys=True).encode()).hexdigest()
        results.append(excerpt)
    if _owned(row['id']) is None:
        raise PermissionError()
    return {'kind': 'untrusted_reference_data', 'source': 'authorized_company_tickets',
            'results': results, 'limit': 3, 'coverage': 'tickets_and_matching_comments_only' if terms else 'completed_ticket_sample_only'}


def _agent_identity(row):
    """Publish only an explicitly curated Live identity, never the raw persona."""
    root = AGENTS_DIR.resolve()
    path = (root / (row['agent_name'] + '.md')).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ContinuityDenied('agent_identity_unavailable')
    text = path.read_text(encoding='utf-8')
    for marker in ('# Persistent Agent Memory', '## MEMORY.md'):
        text = text.split(marker, 1)[0]
    heading = re.search(r'^## Live Identity\s*$', text, flags=re.MULTILINE)
    identity = {'agentName': row['agent_name'], 'source': 'curated_live_identity',
                'status': 'unavailable', 'persona': '', 'truncated': False,
                'legacyMemoryImported': False}
    if heading is None:
        return identity
    text = re.split(r'^#{1,2} ', text[heading.end():], maxsplit=1, flags=re.MULTILINE)[0].strip()
    # Obvious credential material blocks the whole section. This is defense
    # in depth; the explicit section still requires human editorial review.
    sensitive = r'(?i)(?:api[_ -]?key|password|senha|secret|token)\s*[:=]\s*\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|https?://[^\s/]+:[^\s/]+@|\bAKIA[A-Z0-9]{16}\b'
    if not text or re.search(sensitive, text):
        return identity
    return {**identity, 'status': 'available', 'persona': text[:2500], 'truncated': len(text) > 2500}


def _previous_work_for_context(row):
    cid = _continuity_id(row)
    store, principal = _continuity_store(row)
    snap = store.snapshot(principal, cid, history_limit=30)
    query = next((e['text'][:200] for e in reversed(snap['current_context'])
                  if e['kind'] == 'transcript' and e['source'].startswith('browser:user:')), '')
    try:
        return _work_payload(row, query)
    except PermissionError:
        return {'status': 'denied', 'results': []}


def _authorized_work_record(row, record_type, record_id):
    """Server derives every link from an existing, company-owned record."""
    from models import Ticket, MediaJob
    if not isinstance(record_id, str) or not _ID.fullmatch(record_id):
        raise PermissionError()
    if record_type == 'live_task':
        from live_task_dispatch import owned, payload, TaskDenied
        try:
            return payload(owned(row, record_id))
        except TaskDenied:
            raise PermissionError() from None
    if record_type == 'ticket' and has_permission(current_user.role, 'tickets', 'view'):
        obj = Ticket.query.filter_by(id=record_id, company_id=row['company_id']).first()
        if obj is None:
            raise PermissionError()
        text = obj.title[:200] + ' — ' + obj.status
        detail = (obj.description or '')[:600]
        reference = '/api/tickets/' + obj.id
        links = [{'label': 'Trabalho original', 'url': reference}]
        done = obj.status in ('resolved', 'closed', 'archived')
    elif record_type == 'media_job' and has_permission(current_user.role, 'media_jobs', 'view'):
        obj = MediaJob.query.filter_by(id=record_id, company_id=row['company_id']).first()
        if obj is None:
            raise PermissionError()
        text = obj.title[:200] + ' — ' + obj.status
        detail = (obj.progress_message or '')[:600]
        reference = '/api/media/jobs/' + obj.id
        links = [{'label': 'Trabalho original', 'url': reference}]
        if _existing_artifact(obj) is not None:
            links.append({'label': 'Vídeo', 'url': '/api/live/omni-context/' + str(row['id']) + '/artifacts/' + obj.id + '/video'})
        done = obj.status in ('ready_for_review', 'approved', 'draft_created', 'scheduled', 'published')
    else:
        raise PermissionError()
    result = {'recordType': record_type, 'recordId': record_id, 'reference': reference,
              'text': text + ('\n' + detail if detail else ''), 'status': obj.status,
              'updatedAt': obj.updated_at, 'links': links}
    # Context IDs and ephemeral signed URLs do not affect record revision/dedup.
    result['revision'] = hashlib.sha256(json.dumps({k:v for k,v in result.items() if k != 'links'},sort_keys=True).encode()).hexdigest()
    return ('result' if done else 'progress'), result


def _existing_artifact(job):
    if not job.render_path:
        return None
    from media_workspace import media_workspace_root
    try:
        root = media_workspace_root().resolve()
        path = Path(job.render_path).resolve()
        return path if root in path.parents and path.is_file() else None
    except (OSError, ValueError):
        return None


def _visible_event(row, item):
    if item['kind'] not in ('progress', 'result'):
        return item
    try:
        stored = json.loads(item['text'])
        _, current = _authorized_work_record(row, stored['recordType'], stored['recordId'])
        item.update(text=stored['text'], links=current['links'], reference=stored['reference'],
                    recordRevision=stored['revision'], recordUpdatedAt=stored['updatedAt'])
    except (ValueError, KeyError, TypeError, PermissionError):
        # Reference was moved/revoked/deleted: never replay cached content/links.
        item.update(text='', links=[], source='unavailable', retracted=True)
    return item


@bp.post('/api/live/omni-context/<int:context_id>/work-events')
def persist_work_event(context_id):
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    if set(data) != {'conversationId', 'recordType', 'recordId'}:
        return _reply({'error': 'invalid_work_event'}, 400)
    try:
        kind, record = _authorized_work_record(row, data['recordType'], data['recordId'])
        cid = _continuity_id(row)
        store, principal = _continuity_store(row)
        # Stable across retries/reconnects. No browser-supplied output or URL.
        key = hashlib.sha256((kind + ':' + record['reference'] + ':' + record['revision']).encode()).hexdigest()
        # Persist stable original reference only; artifact URLs are recomputed on read.
        persisted = {k:v for k,v in record.items() if k != 'links'}
        result = store.record(principal, cid, kind=kind, text=json.dumps(persisted,ensure_ascii=False),
                              source=record['reference'], verified=True, request_key=key)
        return _reply({'saved': True, **result})
    except (PermissionError, ContinuityDenied):
        return _reply({'error': 'scope_denied'}, 403)
    except (ValueError, TypeError):
        return _reply({'error': 'invalid_work_event'}, 400)
    except sqlite3.Error:
        return _reply({'error': 'continuity_unavailable'}, 503)


@bp.post('/api/live/omni-context/<int:context_id>/events')
def read_conversation_events(context_id):
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    if set(data) not in ({'conversationId'}, {'conversationId', 'after'}):
        return _reply({'error': 'invalid_cursor'}, 400)
    try:
        cid = _continuity_id(row)
        store, principal = _continuity_store(row)
        events = store.events_since(principal, cid, after=data.get('after', 0))
        events = [_visible_event(row, event) for event in events]
        return _reply({'logicalConversationId': cid, 'events': events,
                       'next': events[-1]['seq'] if events else data.get('after', 0),
                       'hasMore': len(events) == 100})
    except ContinuityDenied:
        return _reply({'error': 'scope_denied'}, 403)
    except ValueError:
        return _reply({'error': 'invalid_cursor'}, 400)
    except sqlite3.Error:
        return _reply({'error': 'continuity_unavailable'}, 503)


@bp.get('/api/live/omni-context/<int:context_id>/artifacts/<string:job_id>/video')
def continuity_artifact(context_id, job_id):
    denied = _guard()
    if denied is not None:
        return denied
    if current_app.config.get('NEXUS_LIVE_CONTINUITY_ENABLED') is not True:
        return _reply({'error': 'continuity_disabled'}, 503)
    row = _owned(context_id)
    if row is None or not has_permission(current_user.role, 'memory', 'view'):
        return _reply({'error': 'scope_denied'}, 403)
    try:
        _authorized_work_record(row, 'media_job', job_id)
        from models import MediaJob
        job = MediaJob.query.filter_by(id=job_id, company_id=row['company_id']).first()
        path = _existing_artifact(job)
        if path is None:
            return _reply({'error': 'artifact_unavailable'}, 404)
        response = send_file(str(path), mimetype='video/mp4', conditional=True)
        response.headers['Cache-Control'] = 'no-store'
        return response
    except PermissionError:
        return _reply({'error': 'scope_denied'}, 403)


# Internal text-only jobs reuse the persistent orchestration queue, never shell input.
@bp.post('/api/live/omni-context/<int:context_id>/tasks')
def submit_internal_task(context_id):
    from live_task_dispatch import submit, emit, payload, TaskDenied, OPERATIONS
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    if (set(data) != {'conversationId', 'requestId', 'operation', 'ticketId'}
            or not isinstance(data.get('requestId'), str) or not _ID.fullmatch(data['requestId'])
            or not isinstance(data.get('ticketId'), str) or not _ID.fullmatch(data['ticketId'])
            or not isinstance(data.get('operation'), str) or data['operation'] not in OPERATIONS):
        return _reply({'error': 'invalid_internal_task'}, 400)
    if not has_permission(current_user.role, 'tickets', 'view'):
        return _reply({'error': 'scope_denied'}, 403)
    try:
        binding, created = submit(row, _continuity_id(row), data['requestId'], data['operation'], data['ticketId'])
        emit(binding)
        _, record = payload(binding)
        return _reply({'jobId': binding.job_id, 'status': record['status'], 'reference': record['reference'],
                       'replayed': not created, 'mode': 'internal_text_no_tools'}, 201 if created else 200)
    except TaskDenied as exc:
        return _reply({'error': str(exc)}, 503 if str(exc) == 'live_tasks_disabled' else 403)
    except ValueError:
        return _reply({'error': 'idempotency_conflict'}, 409)
    except sqlite3.Error:
        return _reply({'error': 'internal_task_unavailable'}, 503)


@bp.post('/api/live/omni-context/<int:context_id>/tasks/<string:job_id>/status')
@bp.post('/api/live/omni-context/<int:context_id>/tasks/<string:job_id>/cancel')
def internal_task_status(context_id, job_id):
    from live_task_dispatch import owned, payload, emit, cancel, TaskDenied
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    if set(data) != {'conversationId'}:
        return _reply({'error': 'invalid_internal_task'}, 400)
    try:
        binding = owned(row, job_id)
        if request.path.endswith('/cancel'):
            cancel(binding)
        emit(binding)  # Repair a missed event, never rerun a job.
        _, record = payload(binding)
        return _reply({'jobId': job_id, **record})
    except TaskDenied:
        return _reply({'error': 'scope_denied'}, 403)


@bp.get('/api/live/tasks/<string:job_id>')
def internal_task_result(job_id):
    from live_task_dispatch import payload, TaskDenied
    from models import LiveTaskBinding
    denied = _guard()
    if denied is not None:
        return denied
    binding = LiveTaskBinding.query.filter_by(job_id=job_id, user_id=int(current_user.get_id())).first()
    if binding is None:
        return _reply({'error': 'scope_denied'}, 403)
    try:
        _, record = payload(binding)
        from models import db, OrchestrationJob
        job = db.session.get(OrchestrationJob, job_id)
        return _reply({'jobId': job_id, **record, 'output': job.stage_result if job.status == 'success' else None})
    except TaskDenied:
        return _reply({'error': 'scope_denied'}, 403)


@bp.get('/api/execution/decisions/<string:job_id>')
def execution_decision_result(job_id):
    """Private observed trace, guarded by the same live task ownership/resource ACL."""
    from models import db, LiveTaskBinding, ExecutionRouteDecision
    from live_task_dispatch import _scope, TaskDenied
    denied = _guard()
    if denied is not None:
        return denied
    binding = LiveTaskBinding.query.filter_by(job_id=job_id, user_id=int(current_user.get_id())).first()
    decision = db.session.get(ExecutionRouteDecision, job_id) if binding else None
    if (decision is None or decision.user_id != binding.user_id
            or decision.company_id != binding.company_id):
        return _reply({'error': 'scope_denied'}, 403)
    try:
        _scope(binding)
        return _reply({'jobId': job_id, 'operation': decision.operation, **json.loads(decision.trace)})
    except TaskDenied:
        return _reply({'error': 'scope_denied'}, 403)


@bp.post('/api/live/omni-context/<int:context_id>/query')
def query_authorized_context(context_id):
    """Read-only query tool over existing scoped Live history and ticket API."""
    row, data, denied = _continuity_request(context_id)
    if denied is not None:
        return denied
    if (set(data) != {'conversationId', 'query'} or not isinstance(data['query'], str)
            or not 1 <= len(data['query'].strip()) <= 200):
        return _reply({'error': 'invalid_query'}, 400)
    try:
        return _reply(_query_payload(row, data['query']))
    except ValueError:
        return _reply({'error': 'query_too_broad'}, 400)
    except ContinuityDenied:
        return _reply({'error': 'scope_denied'}, 403)
    except sqlite3.Error:
        return _reply({'error': 'continuity_unavailable'}, 503)


def _query_payload(row, query, *, include_work=True):
    query = query.strip()[:200]
    terms = list(dict.fromkeys(re.findall(r'[^\W_]+(?:-[^\W_]+)*', query.lower())))
    stop = {'qual','quais','sobre','anterior','anteriores','lembra','voce','você','para','como','que','uma','dos','das'}
    terms = [t for t in terms if len(t) >= 3 and t not in stop][:4]
    if not terms:
        return {'kind': 'untrusted_reference_data', 'memory': [], 'work': {'results': []}, 'coverage': 'query_too_broad'}
    try:
        store, principal = _continuity_store(row)
        memories = []
        for hit in store.search(principal, terms, limit=5):
            hit = _visible_event(row, hit)
            if hit.get('retracted'):
                continue
            memories.append({'conversationId': hit['logical_id'], 'eventId': hit['event_id'],
                             'revision': hit['revision'], 'kind': hit['kind'],
                             'text': hit['text'][:600], 'source': hit['source'],
                             'verified': bool(hit['verified']), 'links': hit.get('links', [])})
        try:
            work = _work_payload(row, query) if include_work else {'source': 'previousWork', 'results': []}
        except PermissionError:
            work = {'status': 'denied', 'results': []}
        if _owned(row['id']) is None:
            raise ContinuityDenied()
        from live_recording_source import search_current_scripts
        documents = search_current_scripts(row['company_id'], terms)
        if _owned(row['id']) is None:
            raise ContinuityDenied()
        return {'kind': 'untrusted_reference_data', 'memory': memories, 'documents': documents,
                       'work': work, 'coverage': ['owned_live_conversations', 'authorized_recording_scripts'] + (['authorized_company_tickets'] if include_work else []),
                       'excluded': ['unowned_mempalace_index', 'private_dot_history', 'arbitrary_mcp_execution'],
                       'limits': {'memory': 5, 'work': 3, 'excerptCharacters': 600, 'documents': 3}}
    except ContinuityDenied:
        raise



def _query_for_current_turn(row):
    cid = _continuity_id(row)
    store, principal = _continuity_store(row)
    snap = store.snapshot(principal, cid, history_limit=30)
    query = next((e['text'][:200] for e in reversed(snap['current_context'])
                  if e['kind'] == 'transcript' and e['source'].startswith('browser:user:')), '')
    result = _query_payload(row, query, include_work=False)
    while (result['memory'] or result.get('documents', {}).get('results')) and len(json.dumps(result, ensure_ascii=False)) > 4000:
        (result['memory'] or result['documents']['results']).pop()
    return result


def _tool_audit_request(context_id):
    denied = _guard(write=True)
    if denied is not None:
        return None, None, denied
    row = _owned(context_id)
    data = request.get_json(silent=True)
    if (row is None or not isinstance(data, dict) or not row['conversation_id']
            or data.get('conversationId') != row['conversation_id']):
        return None, None, _reply({'error': 'scope_denied'}, 403)
    return row, data, None


@bp.post('/api/live/omni-context/<int:context_id>/tool-audit')
def append_tool_audit(context_id):
    row, data, denied = _tool_audit_request(context_id)
    if denied is not None:
        return denied
    from live_tool_audit import append
    try:
        with _store() as conn:
            append(conn, row, data)
        return _reply({'recorded': True})
    except ValueError:
        return _reply({'error': 'invalid_audit_metadata'}, 400)
    except sqlite3.Error:
        return _reply({'error': 'audit_unavailable'}, 503)


@bp.post('/api/live/omni-context/<int:context_id>/tool-audit/read')
def read_tool_audit(context_id):
    row, data, denied = _tool_audit_request(context_id)
    if denied is not None:
        return denied
    if set(data) not in ({'conversationId'}, {'conversationId', 'toolCallId'}):
        return _reply({'error': 'invalid_audit_metadata'}, 400)
    from live_tool_audit import read
    try:
        with _store() as conn:
            events = read(conn, row, data.get('toolCallId'))
        return _reply({'events': events, 'limit': 200,
                       'deliveryEvidence': 'browser_reported_sdk_send_not_provider_ack'})
    except ValueError:
        return _reply({'error': 'invalid_audit_metadata'}, 400)
    except sqlite3.Error:
        return _reply({'error': 'audit_unavailable'}, 503)
