"""Regression coverage for the production media retry hot loop (no external I/O)."""
import importlib.util
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from media_retry import MAX_ATTEMPTS, failure_state, migrate_retry_state
from media_executor import MediaExecutionError, run_opencode_media_job

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def create(client):
    r = client.post('/api/media/jobs', json={
        'title': 'Retry regression', 'platform': 'instagram', 'width': 720,
        'height': 1280, 'duration_seconds': 6,
    })
    assert r.status_code == 201
    return r.get_json()


@pytest.mark.parametrize('error', [
    'Manifesto de entrada não encontrado: /input/job.json',
    'Manifesto de entrada inválido: invalid JSON',
    'Manifesto inválido: schema mismatch',
])
def test_permanent_errors_terminal(error):
    assert failure_state(1, error, now=NOW) == ('failed', None)


@pytest.mark.parametrize('error', ['HTTP 429 rate limit', 'network timeout', '503 overloaded'])
def test_transient_errors_back_off(error, monkeypatch):
    monkeypatch.setattr('media_retry.random.uniform', lambda *_: 1)
    status, due = failure_state(2, error, now=NOW)
    assert status == 'retryable_failure'
    assert datetime.fromisoformat(due.replace('Z', '+00:00')) == NOW + timedelta(seconds=120)


def test_attempt_ceiling():
    assert failure_state(MAX_ATTEMPTS, '429', now=NOW) == ('failed', None)
    assert failure_state(1511188, 'timeout', now=NOW) == ('failed', None)


@pytest.mark.parametrize('content', ['{broken', '[]'])
def test_invalid_input_never_invokes_provider(tmp_path, monkeypatch, content):
    (tmp_path / 'input').mkdir()
    (tmp_path / 'input/job.json').write_text(content)
    monkeypatch.setattr('media_executor.invoke_with_fallback', lambda **_: pytest.fail('provider called'))
    with pytest.raises(MediaExecutionError, match='Manifesto de entrada inválido'):
        run_opencode_media_job(tmp_path)


def test_missing_input_never_invokes_provider(tmp_path, monkeypatch):
    monkeypatch.setattr('media_executor.invoke_with_fallback', lambda **_: pytest.fail('provider called'))
    with pytest.raises(MediaExecutionError, match='Manifesto de entrada não encontrado'):
        run_opencode_media_job(tmp_path)


@pytest.mark.parametrize('failure_at', ['scaffold', 'manifest'])
def test_creation_failure_does_not_queue_orphan(admin_client, app, monkeypatch, failure_at):
    import models
    if failure_at == 'scaffold':
        def fail(_):
            raise OSError('Read-only file system')
        monkeypatch.setattr('routes.media_jobs.ensure_job_scaffold', fail)
    else:
        def fail(*_, **__):
            raise OSError('No space left on device')
        monkeypatch.setattr(Path, 'write_text', fail)
    r = admin_client.post('/api/media/jobs', json={
        'title': 'No orphan', 'platform': 'instagram', 'width': 720,
        'height': 1280, 'duration_seconds': 6,
    })
    assert r.status_code == 503
    with app.app_context():
        assert models.MediaJob.query.count() == 0


def test_wait_survives_requests_and_other_jobs_advance(admin_client, app, monkeypatch):
    import models
    blocked = create(admin_client)
    admin_client.post(f"/api/media/jobs/{blocked['id']}/run")
    failed = admin_client.patch(f"/api/media/jobs/{blocked['id']}", json={
        'status': 'retryable_failure', 'last_error': 'HTTP 429',
    }).get_json()
    assert failed['next_retry_at']
    ready = create(admin_client)
    eligible = admin_client.get('/api/media/jobs?eligible=true').get_json()
    assert [j['id'] for j in eligible] == [ready['id']]
    assert admin_client.post(f"/api/media/jobs/{ready['id']}/run").status_code == 200
    assert admin_client.post(f"/api/media/jobs/{blocked['id']}/run").status_code == 409
    # Eligibility is persisted, and a fresh API request can claim after the due time.
    with app.app_context():
        j = models.db.session.get(models.MediaJob, blocked['id'])
        j.next_retry_at = '2000-01-01T00:00:00.000000Z'
        models.db.session.commit()
    assert admin_client.post(f"/api/media/jobs/{blocked['id']}/run").status_code == 200


def test_permanent_failure_patch_terminal_and_unlocks(admin_client):
    j = create(admin_client)
    admin_client.post(f"/api/media/jobs/{j['id']}/run")
    r = admin_client.patch(f"/api/media/jobs/{j['id']}", json={
        'status': 'retryable_failure', 'last_error': 'Manifesto inválido: schema',
    })
    assert r.get_json()['status'] == 'failed'
    assert r.get_json()['locked_at'] is None
    assert r.get_json()['next_retry_at'] is None


def test_fifth_attempt_terminal_and_claim_cannot_bypass_ceiling(admin_client, app):
    import models
    j = create(admin_client)
    with app.app_context():
        row = models.db.session.get(models.MediaJob, j['id'])
        row.attempt_count = MAX_ATTEMPTS - 1
        models.db.session.commit()
    assert admin_client.post(f"/api/media/jobs/{j['id']}/run").get_json()['attempt_count'] == MAX_ATTEMPTS
    r = admin_client.patch(f"/api/media/jobs/{j['id']}", json={
        'status': 'retryable_failure', 'last_error': 'timeout',
    })
    assert r.get_json()['status'] == 'failed'
    assert admin_client.get('/api/media/jobs?eligible=true').get_json() == []
    # Old retryable rows are guarded even if an old worker explicitly POSTs /run.
    with app.app_context():
        row = models.db.session.get(models.MediaJob, j['id'])
        row.status = 'retryable_failure'
        models.db.session.commit()
    assert admin_client.post(f"/api/media/jobs/{j['id']}/run").get_json()['error'] == 'retry_limit_reached'


def test_migration_additive_idempotent_preserves_legacy_evidence():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE media_jobs (id TEXT, status TEXT, attempt_count INTEGER, last_error TEXT, locked_at TEXT, locked_by TEXT)')
    c.executemany('INSERT INTO media_jobs VALUES (?,?,?,?,?,?)', [
        ('exhausted', 'retryable_failure', 1511188, 'missing manifest', None, None),
        ('transient', 'retryable_failure', 1, 'timeout', None, None),
        ('active', 'generating', 6, None, 'now', 'worker'),
    ])
    migrate_retry_state(c)
    migrate_retry_state(c)
    assert c.execute("SELECT status,last_error FROM media_jobs WHERE id='exhausted'").fetchone() == ('failed', 'missing manifest')
    assert c.execute("SELECT status FROM media_jobs WHERE id='transient'").fetchone()[0] == 'retryable_failure'
    assert c.execute("SELECT status FROM media_jobs WHERE id='active'").fetchone()[0] == 'generating'


def test_watchdog_reap_waits_and_honors_ceiling():
    import ops_watchdog as watchdog
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE media_jobs (id TEXT, status TEXT, attempt_count INTEGER, last_error TEXT, locked_at TEXT, locked_by TEXT, next_retry_at TEXT, updated_at TEXT)')
    c.executemany('INSERT INTO media_jobs VALUES (?,?,?,?,?,?,?,?)', [
        ('recoverable', 'generating', 1, None, 'old', 'worker', None, '2000'),
        ('exhausted', 'rendering', MAX_ATTEMPTS, None, 'old', 'worker', None, '2000'),
    ])
    assert watchdog._reap_orphaned_media_jobs(c) == 2
    assert c.execute("SELECT status,locked_at FROM media_jobs WHERE id='recoverable'").fetchone() == ('retryable_failure', None)
    assert c.execute("SELECT next_retry_at FROM media_jobs WHERE id='recoverable'").fetchone()[0]
    assert c.execute("SELECT status,next_retry_at FROM media_jobs WHERE id='exhausted'").fetchone() == ('failed', None)


@pytest.fixture
def worker():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('media_retry_test_worker', root / 'media_worker/worker.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_moves_past_empty_queued_list_and_requests_due_only(worker, monkeypatch):
    calls = []
    def get(path, params):
        calls.append(params)
        return [] if params['status'] == 'queued' else [{'id': 'due'}]
    monkeypatch.setattr(worker.evo, 'get', get)
    monkeypatch.setattr(worker.evo, 'post', lambda path, body: {'id': 'due'})
    assert worker._claim_next_job()['id'] == 'due'
    assert all(p['eligible'] == 'true' for p in calls)


def test_worker_429_waits_without_claiming(worker, monkeypatch):
    import requests
    response = requests.Response()
    response.status_code = 429
    sleeps = []
    def get(*_, **__):
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(worker.evo, 'get', get)
    monkeypatch.setattr(worker.evo, 'post', lambda *_: pytest.fail('claim during 429'))
    monkeypatch.setattr(worker.time, 'sleep', sleeps.append)
    assert worker._claim_next_job() is None
    assert worker._claim_next_job() is None
    assert sleeps == [60, 120]


def test_worker_manifest_failure_is_terminal(worker, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, '_patch', lambda jid, **fields: calls.append(fields))
    worker._fail_job('bad', 'Manifesto inválido: bad schema')
    assert calls == [{'status': 'failed', 'last_error': 'Manifesto inválido: bad schema'}]
