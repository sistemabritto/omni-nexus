"""HTTP and real upgrade smoke inside the network-isolated image."""
import http.cookiejar
import json
import os
import sqlite3
import subprocess
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus

base = 'http://127.0.0.1:8080'
def request(path, opener=None, body=None, headers=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=payload, headers=headers or {})
    if payload is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with (opener or urllib.request.build_opener()).open(req, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as response:
        return response.code, dict(response.headers), response.read()

for attempt in range(120):
    try:
        if request('/api/version')[0] == 200:
            break
    except (OSError, TimeoutError):
        pass
    time.sleep(1)
else:
    raise SystemExit('image application did not become ready within 120 seconds')

assert request('/api/live/status')[0] == 401
assert request('/api/auth/me')[0] == 401
assert request('/api/live/status', headers={'Authorization': 'Bearer fixture-agent-token'})[0] == 403
assert request('/api/live/status')[0] == 401
status, _, html = request('/live')
assert status == 200 and b'<html' in html
main = re.search(rb'<script[^>]+src="([^"]+\.js)"', html)
assert main
status, _, bundle = request(main.group(1).decode())
assert status == 200 and b'LiveConversation-' in bundle
chunk = re.search(rb'LiveConversation-[A-Za-z0-9_-]+\.js', bundle)
assert chunk
assert request('/assets/' + chunk.group().decode())[0] == 200

jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
assert request('/api/auth/login', browser, {'username': 'smoke-admin', 'password': 'Fixture!Smoke42'})[0] == 200
cookie = '; '.join(c.name + '=' + c.value for c in jar)
assert cookie
# ProxyFix mirrors the trusted proxy while all TCP remains on loopback.
for hostname in ['nexus.workflowapi.com.br', 'nexus.sistemabritto.com.br']:
    origin = 'https://' + hostname
    headers = {'Cookie': cookie, 'X-Forwarded-Host': hostname, 'X-Forwarded-Proto': 'https', 'Origin': origin}
    status, response_headers, raw = request('/api/live/status', headers=headers)
    assert status == 200
    payload = json.loads(raw)
    assert {k:payload[k] for k in ('enabled','freeTierVerified')} == {'enabled': False, 'freeTierVerified': False}
    assert payload['activeModel'] is None
    assert response_headers.get('Cache-Control') == 'no-store'
    for supplied_origin, expected in [(origin, 503), ('https://evil.invalid', 403)]:
        try:
            connect('ws://127.0.0.1:8080/api/live/ws', origin=supplied_origin,
                    additional_headers={k:v for k,v in headers.items() if k != 'Origin'}, proxy=None)
        except InvalidStatus as error:
            assert error.response.status_code == expected
        else:
            raise AssertionError('disabled Live unexpectedly upgraded')

result = {'image_flask_boot': True, 'live_assets': True, 'anonymous_status': 401,
          'bearer_status': 403, 'authenticated_live_enabled': False,
          'same_origin_disabled_upgrade': 503, 'bad_origin_upgrade': 403,
          'hosts': ['nexus.workflowapi.com.br', 'nexus.sistemabritto.com.br'],
          'network': 'none', 'google_calls': 0, 'default_entrypoint_tested': False}
if os.environ.get('SMOKE_SUPERVISOR') == '1':
    with urllib.request.urlopen('http://127.0.0.1:32352/api/health', timeout=5) as health:
        assert health.status == 200
    with sqlite3.connect('/workspace/dashboard/data/evonexus.db') as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in ['heartbeat_runs', 'scheduled_tasks']:
            if name in tables:
                assert db.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] == 0
    # The mount's basename is NOT gemini_api_key, so auto-discovery cannot
    # satisfy this assertion. Only the supported GEMINI_API_KEY_FILE bridge
    # can populate the application's expected env name. Dummy value only.
    bridged = False
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if b'/workspace/dashboard/backend/app.py' not in (process/'cmdline').read_bytes().split(bytes([0])):
                continue
            bridged = subprocess.run(['grep', '-z', '-q', '-x', '-F',
                'GEMINI_API_KEY=fixture-live-secret-file-smoke', str(process/'environ')],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        except OSError:
            continue
    assert bridged, '_FILE secret must reach real Flask process without enabling Live'
    result.update(default_entrypoint_tested=True, terminal_health=True, fixture_jobs_executed=0,
                  secret_file_env_bridge_verified=True, live_stayed_disabled_with_fixture_key=True)
print(json.dumps(result, sort_keys=True))
Path('/tmp/live-image-smoke-result.json').write_text(json.dumps(result, indent=2)+'\n')
