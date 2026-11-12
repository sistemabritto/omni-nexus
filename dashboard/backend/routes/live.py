"""Cookie-authenticated Live audio; opt-in server configuration, disabled by default."""
from urllib.parse import urlsplit

from flask import Blueprint, current_app, g, jsonify, request
from flask_sock import Sock
from pathlib import Path
from live_transport import LiveConfig, LeaseStore, run_session
from flask_login import current_user

bp = Blueprint('live', __name__)
ALLOWED_ORIGINS = frozenset(('https://nexus.sistemabritto.com.br', 'https://nexus.workflowapi.com.br'))


def _reply(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response


def _session_guard():
    if not current_user.is_authenticated:
        return _reply({'error': 'unauthorized'}, 401)
    # A configured agent token is not a person's browser session.
    if getattr(g, 'auth_via_api_token', False):
        return _reply({'error': 'cookie_session_required'}, 403)
    return None


def _origin_allowed(required=False):
    origin = request.headers.get('Origin')
    if not origin:
        return not required
    return origin in ALLOWED_ORIGINS and urlsplit(origin).netloc == request.host


@bp.get('/api/live/status')
def live_status():
    denied = _session_guard()
    if denied is not None:
        return denied
    if not _origin_allowed():
        return _reply({'error': 'origin_forbidden'}, 403)
    config = LiveConfig.environment()
    return _reply({'enabled': bool(config.ready), 'freeTierVerified': bool(config.ready)})


@bp.before_app_request
def guard_live_upgrade():
    # Runs before dispatch, including Werkzeug's websocket routing mismatch.
    # Authentication, origin and activation are checked before any upgrade.
    if request.path != '/api/live/ws':
        return None
    denied = _session_guard()
    if denied is not None:
        return denied
    if not _origin_allowed(required=True):
        return _reply({'error': 'origin_forbidden'}, 403)
    if not LiveConfig.environment().ready:
        return _reply({'error': 'live_disabled'}, 503)
    if not request.environ.get('wsgi.websocket') and request.headers.get('Upgrade', '').lower() != 'websocket':
        return _reply({'error': 'websocket_required'}, 426)
    return None


@bp.get('/api/live/ws')
def live_ws_disabled():
    return _reply({'error': 'live_disabled'}, 503)


_sock = Sock()


@_sock.route('/api/live/ws', bp=bp)
def live_audio_socket(client):
    client.max_message_size = 32000
    # Defense in depth: guards run before upgrade and again in handler.
    if _session_guard() is not None or not _origin_allowed(required=True):
        client.close()
        return
    config = LiveConfig.environment()
    if not config.ready:
        client.close()
        return
    path = current_app.config.get('LIVE_LIMITS_PATH') or str(Path(__file__).resolve().parents[2] / 'data' / 'live-limits.sqlite3')
    store = LeaseStore(path)
    token = None
    try:
        token = store.acquire(str(current_user.get_id()))
        if token is None:
            client.send('{"error":"session_rate_limit"}')
            client.close()
            return
        run_session(client, config)
    except Exception:
        # Neither credentials, provider errors nor audio reach logs.
        try:
            client.close()
        except Exception:
            pass
    finally:
        if token is not None:
            store.release(token)
