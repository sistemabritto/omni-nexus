"""No live Postiz: versioned human approval and per-channel retry evidence."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from postiz_client import PostizAPIError, PostizError


def ready(client):
    job = client.post('/api/media/jobs', json={
        'title':'Release test', 'platform':'instagram', 'caption':'base copy',
        'width':720, 'height':1280, 'duration_seconds':5,
    }).get_json()
    path = Path(job['workspace_path']) / 'output/final.mp4'
    path.write_bytes(b'validated-render-v1')
    url = f"/api/media/jobs/{job['id']}"
    for status in ['preparing','generating','rendering','validating','ready_for_review']:
        response = client.patch(url,json={'status':status,'render_path':str(path),
            'render_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        assert response.status_code == 200
    date = (datetime.now(timezone.utc)+timedelta(days=3)).replace(microsecond=0).isoformat()
    body = {'render_version':'v1','channels':[
        {'platform':'instagram','integration_id':'ig-1','content':'IG copy','scheduled_at_utc':date},
        {'platform':'linkedin','integration_id':'li-1','content':'LI copy','scheduled_at_utc':date},
    ]}
    release = client.put(url+'/release',json=body)
    assert release.status_code == 200
    return url, body, release.get_json(), path


def approve(client,url,release):
    result = client.post(url+'/release/approve',json={'digest':release['digest']})
    assert result.status_code == 200
    return result.get_json()


class FakePostiz:
    def __init__(self):
        self.posts = {}
        self.created = []
        self.scheduled = []
        self.uploads = 0
        self.fail_create = None
        self.fail_schedule = None

    def list_integrations(self):
        return [{'id':'ig-1','identifier':'instagram','disabled':False},
                {'id':'li-1','identifier':'linkedin','disabled':False}]

    def upload_file(self, path):
        self.uploads += 1
        return {'id':'media-1','path':'https://media.invalid/render.mp4'}

    def create_draft(self, **kwargs):
        self.created.append(kwargs)
        if self.fail_create and kwargs['integration_id'] == 'li-1':
            raise self.fail_create
        post_id = 'post-'+kwargs['integration_id']
        self.posts[post_id] = {'id':post_id,'state':'DRAFT','content':kwargs['content'],
            'publishDate':kwargs['now_iso_utc'],'integration':{'id':kwargs['integration_id']},'releaseURL':None}
        return [{'postId':post_id}]

    def change_status(self, post_id, status):
        self.scheduled.append(post_id)
        if self.fail_schedule and post_id == 'post-li-1':
            raise self.fail_schedule
        self.posts[post_id]['state'] = 'QUEUE'

    def list_posts(self, window):
        return list(self.posts.values())


@pytest.fixture
def postiz(monkeypatch):
    import routes.media_jobs as routes
    fake = FakePostiz()
    monkeypatch.setattr(routes.PostizClient,'from_env',lambda:fake)
    return fake


def test_two_channels_require_exact_human_approval_and_do_not_duplicate(admin_client, postiz):
    url, body, release, path = ready(admin_client)
    assert admin_client.post(url+'/release/distribute').status_code == 409
    assert postiz.created == []
    approved = approve(admin_client,url,release)
    assert approved['approved_by'] == 'admin'
    assert approved['approval_valid'] is True
    for _ in range(2):
        response = admin_client.post(url+'/release/distribute')
        assert response.status_code == 200
        channels = response.get_json()['progress']['channels']
        assert {c['state'] for c in channels.values()} == {'scheduled'}
    assert postiz.uploads == 1
    assert len(postiz.created) == len(postiz.scheduled) == 2
    postiz.posts['post-li-1'].update(state='PUBLISHED',releaseURL='https://linkedin.invalid/post/123')
    refreshed = admin_client.post(url+'/release/refresh').get_json()
    assert refreshed['progress']['channels']['li-1']['release_url'] == 'https://linkedin.invalid/post/123'
    assert refreshed['progress']['channels']['ig-1']['release_url'] is None
    for action in ['approve','create-draft','schedule']:
        assert admin_client.post(url+'/'+action).status_code == 409


@pytest.mark.parametrize('change',['render','caption','copy','channel','calendar','version'])
def test_every_approved_component_change_requires_new_approval(admin_client,postiz,change):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    if change == 'render':
        path.write_bytes(b'changed-outside-api')
    elif change == 'caption':
        assert admin_client.patch(url,json={'caption':'changed'}).status_code == 200
    else:
        body['expected_digest'] = release['digest']
        if change == 'copy': body['channels'][0]['content'] = 'new copy'
        if change == 'channel': body['channels'] = body['channels'][:1]
        if change == 'calendar': body['channels'][0]['scheduled_at_utc'] = (datetime.now(timezone.utc)+timedelta(days=4)).isoformat()
        if change == 'version': body['render_version'] = 'v2'
        revised = admin_client.put(url+'/release',json=body)
        assert revised.status_code == 200
        assert not revised.get_json()['approval_valid']
        assert admin_client.post(url+'/release/approve',json={'digest':release['digest']}).status_code == 409
    assert admin_client.post(url+'/release/distribute').status_code == 409
    assert not admin_client.get(url+'/release').get_json()['approval_valid']
    assert postiz.created == []


def test_tokens_and_worker_patch_cannot_forge_human_approval(admin_client, app):
    from flask import g, request
    @app.before_request
    def token():
        g.auth_via_api_token = request.headers.get('X-Test-Token') == 'yes'
    url, body, release, path = ready(admin_client)
    assert admin_client.patch(url,json={'status':'approved'}).status_code == 403
    assert admin_client.post(url+'/release/approve',json={'digest':release['digest']},headers={'X-Test-Token':'yes'}).status_code == 403
    assert admin_client.post(url+'/approve',headers={'X-Test-Token':'yes'}).status_code == 403


def test_partial_retry_resumes_known_post_without_recreating_success(admin_client,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    postiz.fail_schedule = PostizError('network timeout')
    response = admin_client.post(url+'/release/distribute').get_json()
    assert response['progress']['channels']['ig-1']['state'] == 'scheduled'
    assert response['progress']['channels']['li-1']['post_id'] == 'post-li-1'
    postiz.fail_schedule = None
    response = admin_client.post(url+'/release/distribute').get_json()
    assert response['progress']['channels']['li-1']['state'] == 'scheduled'
    assert len(postiz.created) == 2
    assert postiz.scheduled.count('post-ig-1') == 1
    assert postiz.uploads == 1


def test_unknown_create_outcome_stops_instead_of_duplicate(admin_client,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    postiz.fail_create = PostizError('response lost')
    result = admin_client.post(url+'/release/distribute').get_json()
    assert result['progress']['channels']['li-1']['state'] == 'unknown'
    postiz.fail_create = None
    admin_client.post(url+'/release/distribute')
    assert len(postiz.created) == 2
    body['expected_digest'] = release['digest']
    assert admin_client.put(url+'/release',json=body).status_code == 409


def test_known_429_rejection_retries_only_failed_channel(admin_client,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    postiz.fail_create = PostizAPIError('rate limit',status_code=429)
    admin_client.post(url+'/release/distribute')
    postiz.fail_create = None
    result = admin_client.post(url+'/release/distribute').get_json()
    assert result['progress']['channels']['li-1']['state'] == 'scheduled'
    assert len(postiz.created) == 3
    assert postiz.scheduled.count('post-ig-1') == 1


def test_remote_confirmation_requires_account_copy_date_and_queue(admin_client,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    admin_client.post(url+'/release/distribute')
    postiz.posts['post-li-1']['content'] = 'remote edit'
    result = admin_client.post(url+'/release/refresh').get_json()
    assert result['progress']['channels']['li-1']['state'] == 'remote_mismatch'
    assert result['progress']['channels']['li-1']['release_url'] is None


def test_busy_release_refuses_second_dispatch_and_job_edit(admin_client,app,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    with app.app_context():
        import models
        row = models.db.session.get(models.MediaRelease,release['job_id'])
        row.busy = True
        models.db.session.commit()
    assert admin_client.post(url+'/release/distribute').status_code == 409
    assert admin_client.patch(url,json={'caption':'change during upload'}).status_code == 409
    assert postiz.created == []


@pytest.mark.parametrize('field,value',[
    ('content','copy changed remotely'),
    ('publishDate','2030-01-01T00:00:00Z'),
    ('integration',{'id':'different-account'}),
])
def test_remote_copy_calendar_or_channel_change_invalidates_approval(admin_client,postiz,field,value):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    admin_client.post(url+'/release/distribute')
    postiz.posts['post-li-1'][field] = value
    result = admin_client.post(url+'/release/refresh').get_json()
    assert result['progress']['channels']['li-1']['state'] == 'remote_mismatch'
    assert not result['approval_valid']
    assert admin_client.post(url+'/release/distribute').status_code == 409
    assert len(postiz.created) == 2


def test_three_safe_rejections_are_bounded_and_success_channel_is_preserved(admin_client,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    postiz.fail_create = PostizAPIError('limited',status_code=429)
    for _ in range(5):
        result = admin_client.post(url+'/release/distribute').get_json()
    assert result['progress']['channels']['li-1']['attempts'] == 3
    assert result['progress']['channels']['ig-1']['state'] == 'scheduled'
    assert len(postiz.created) == 4


def test_unconnected_account_never_creates_or_uploads(admin_client,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    postiz.list_integrations = lambda: []
    assert admin_client.post(url+'/release/distribute').status_code == 409
    assert postiz.uploads == 0
    assert postiz.created == []


def test_cancel_invalidates_approval_without_automatic_remote_changes(admin_client,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    assert admin_client.post(url+'/cancel').status_code == 200
    assert admin_client.post(url+'/release/distribute').status_code == 409
    assert postiz.created == []


def test_lost_create_response_with_500_never_reposts(admin_client,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    postiz.fail_create = PostizAPIError('uncertain server result',status_code=500)
    for _ in range(2):
        result = admin_client.post(url+'/release/distribute').get_json()
    assert result['progress']['channels']['li-1']['state'] == 'unknown'
    assert len(postiz.created) == 2


def test_crashed_creating_checkpoint_requires_reconciliation(admin_client,app,postiz):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    with app.app_context():
        import models
        row = models.db.session.get(models.MediaRelease,release['job_id'])
        row.progress_json = json.dumps({'channels':{'li-1':{'state':'creating_draft','attempts':1,'post_id':None}}})
        models.db.session.commit()
    result = admin_client.post(url+'/release/distribute').get_json()
    assert result['progress']['channels']['li-1']['state'] == 'unknown'
    assert [call['integration_id'] for call in postiz.created] == ['ig-1']


@pytest.mark.parametrize('remote_state',['DRAFT','ERROR',None])
def test_http_success_or_post_id_alone_does_not_prove_scheduled(admin_client,postiz,remote_state):
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    # A status request returning without error is insufficient evidence.
    postiz.change_status = lambda post_id,status: postiz.posts[post_id].update(state=remote_state)
    result = admin_client.post(url+'/release/distribute').get_json()
    assert all(c['state'] not in ('scheduled','published') for c in result['progress']['channels'].values())
    assert all(c['post_id'] for c in result['progress']['channels'].values())


def test_new_release_table_can_be_added_without_rewriting_existing_jobs(admin_client,app):
    url, body, release, path = ready(admin_client)
    with app.app_context():
        import models
        from sqlalchemy import inspect
        columns = [c['name'] for c in inspect(models.db.engine).get_columns('media_jobs')]
        models.MediaRelease.__table__.drop(models.db.engine)
        models.db.create_all()
        assert 'media_releases' in inspect(models.db.engine).get_table_names()
        assert [c['name'] for c in inspect(models.db.engine).get_columns('media_jobs')] == columns
        job = models.db.session.get(models.MediaJob,release['job_id'])
        assert job.title == 'Release test'
        assert Path(job.render_path).read_bytes() == b'validated-render-v1'


def test_channel_picker_exposes_only_existing_supported_active_accounts(admin_client,postiz):
    postiz.list_integrations = lambda: [
        {'id':'ig-standalone','name':'Minha conta','identifier':'instagram-standalone'},
        {'id':'old','identifier':'linkedin','disabled':True},
        {'id':'other','identifier':'unsupported'},
    ]
    result = admin_client.get('/api/media/channels')
    assert result.status_code == 200
    assert result.get_json() == [{'id':'ig-standalone','name':'Minha conta','platform':'instagram','provider':'instagram-standalone'}]
    assert postiz.created == []


def test_explicit_standalone_account_uses_its_provider_settings(admin_client):
    url, body, release, path = ready(admin_client)
    body['expected_digest'] = release['digest']
    body['channels'] = [dict(body['channels'][0],provider='instagram-standalone')]
    result = admin_client.put(url+'/release',json=body)
    assert result.status_code == 200
    assert result.get_json()['snapshot']['channels'][0]['settings']['__type'] == 'instagram-standalone'


@pytest.mark.parametrize('expire_before_draft',[False,True])
def test_calendar_expiring_during_upload_never_falls_back_to_publish_now(admin_client,postiz,monkeypatch,expire_before_draft):
    import media_release
    url, body, release, path = ready(admin_client)
    approve(admin_client,url,release)
    actual_now = datetime.now(timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return actual_now + (timedelta(days=4) if postiz.created or expire_before_draft else timedelta())
    monkeypatch.setattr(media_release,'datetime',Clock)
    result = admin_client.post(url+'/release/distribute').get_json()
    assert result['progress']['channels']['ig-1']['state'] == 'calendar_expired'
    assert not result['approval_valid']
    assert postiz.scheduled == []
