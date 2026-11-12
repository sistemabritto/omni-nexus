"""Startup-only model policy. Catalog discovery does not verify project quota."""

RECOMMENDED_MODEL = 'gemini-3.8-live'
COMPATIBLE_MODELS = frozenset((RECOMMENDED_MODEL, 'gemini-3.1-flash-live-preview',
    'gemini-2.5-flash-native-audio-latest'))
MAX_PROVIDER_ATTEMPTS = 2
ERRORS = frozenset(('provider_auth_failed', 'provider_quota_exhausted',
    'provider_rate_limited', 'provider_network_error', 'provider_model_unavailable',
    'provider_unavailable'))

class ProviderFailure(Exception):
    def __init__(self, category):
        self.category = category if category in ERRORS else 'provider_unavailable'
        super().__init__(self.category)


def provider_failure(error):
    """Inspect only structured codes/reasons; never exception/message strings."""
    if isinstance(error, ProviderFailure):
        return error
    if isinstance(error, dict):
        code = error.get('code')
        status = error.get('status')
        details = error.get('details', [])
    else:
        response = getattr(error, 'response', None)
        code = getattr(response, 'status_code', None) or getattr(error, 'status_code', None)
        status, details = None, []
    if not isinstance(details, list):
        details = []
    if code in (401, 403) or status in ('UNAUTHENTICATED', 'PERMISSION_DENIED'):
        return ProviderFailure('provider_auth_failed')
    if code == 429 or status == 'RESOURCE_EXHAUSTED':
        quota = any(isinstance(d, dict) and (
            d.get('@type') == 'type.googleapis.com/google.rpc.QuotaFailure'
            or d.get('reason') in ('QUOTA_EXCEEDED', 'DAILY_LIMIT_EXCEEDED'))
            for d in details)
        return ProviderFailure('provider_quota_exhausted' if quota else 'provider_rate_limited')
    if code in (404, 501) or status in ('NOT_FOUND', 'UNIMPLEMENTED'):
        return ProviderFailure('provider_model_unavailable')
    if isinstance(error, (OSError, TimeoutError)):
        return ProviderFailure('provider_network_error')
    return ProviderFailure('provider_unavailable')


def csv_models(value):
    return tuple(dict.fromkeys(x.strip() for x in value.split(',') if x.strip() in COMPATIBLE_MODELS))
