"""Authenticated, disabled Live contract. No credential/provider is loaded here."""
from urllib.parse import urlsplit

from flask import Blueprint, g, jsonify, request
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
    # Deliberately hard-disabled: env/browser flags cannot authorize spend.
    return _reply({'enabled': False, 'freeTierVerified': False})


@bp.before_app_request
def reject_disabled_live_upgrade():
    # Runs before dispatch, including Werkzeug's websocket routing mismatch.
    # There is intentionally no upgrade, socket, microphone or provider session.
    if request.path != '/api/live/ws':
        return None
    denied = _session_guard()
    if denied is not None:
        return denied
    if not _origin_allowed(required=True):
        return _reply({'error': 'origin_forbidden'}, 403)
    return _reply({'error': 'live_disabled'}, 503)


@bp.get('/api/live/ws')
def live_ws_disabled():
    return _reply({'error': 'live_disabled'}, 503)
