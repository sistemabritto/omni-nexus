"""Regression cases from read-only Postiz records: delivery is not public publishing."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from media_release import native_video_id,observe_post

DATE=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()


def observe(platform,approved_settings,url,**patch):
    channel={'platform':platform,'integration_id':'own-account','content':'approved exact copy','scheduled_at_utc':DATE,'settings':approved_settings}
    post={'id':'existing-post','state':'PUBLISHED','integration':{'id':'own-account'},'content':channel['content'],'publishDate':DATE,'releaseURL':url,**patch}
    return observe_post(SimpleNamespace(list_posts=lambda window:[post]),channel,'existing-post')


@pytest.mark.parametrize('method',['UPLOAD','DIRECT_POST'])
def test_tiktok_inbox_is_not_publication(method):
    result=observe('tiktok',{'content_posting_method':method,'privacy_level':'PUBLIC_TO_EVERYONE'},'https://www.tiktok.com/messages?lang=en',releaseId='missing')
    assert result['state']=='awaiting_confirmation'
    assert result['release_url'] is None and result['native_post_id'] is None
    assert 'app' in result['error']


@pytest.mark.parametrize('visibility',['private','unlisted'])
def test_youtube_restricted_delivery_is_not_public(visibility):
    result=observe('youtube',{'type':visibility},'https://www.youtube.com/watch?v=J-dok2GA4po')
    assert result['state']=='awaiting_confirmation' and result['release_url'] is None
    assert result['native_post_id']=='J-dok2GA4po'


def test_remote_visibility_must_match_approved_visibility():
    result=observe('youtube',{'type':'public'},'https://www.youtube.com/watch?v=thhQQk9FHzk',settings='{"type":"private"}')
    assert result['state']=='remote_mismatch' and result['release_url'] is None


@pytest.mark.parametrize('platform,url,identity',[('youtube','https://www.youtube.com/watch?v=thhQQk9FHzk','thhQQk9FHzk'),('youtube','https://youtu.be/thhQQk9FHzk','thhQQk9FHzk'),('youtube','https://www.youtube.com/shorts/thhQQk9FHzk','thhQQk9FHzk'),('tiktok','https://www.tiktok.com/@sistemabritto/video/7688834241236438279','7688834241236438279')])
def test_public_native_permalink_keeps_independent_native_id(platform,url,identity):
    result=observe(platform,{'type':'public'} if platform=='youtube' else {'privacy_level':'PUBLIC_TO_EVERYONE'},url)
    assert result['state']=='published' and result['native_post_id']==identity and result['release_url']==url
    assert result['error'] is None


@pytest.mark.parametrize('platform,url',[('tiktok','https://www.tiktok.com/messages?lang=en'),('tiktok','https://www.tiktok.com/@sistemabritto'),('tiktok','https://www.tiktok.com.evil.invalid/@sistemabritto/video/7688834241236438279'),('youtube','https://youtube.com/redirect?q=anything'),('youtube','https://youtube.com/watch?v=thhQQk9FHzk&v=J-dok2GA4po'),('youtube','https://youtube.com/channel/UCXv8K9QVHgUWoYvYptTpDkg'),('youtube','https://user:secret@youtube.com/watch?v=thhQQk9FHzk'),('youtube','http://youtube.com/watch?v=thhQQk9FHzk'),('youtube','https://youtube.com:444/watch?v=thhQQk9FHzk')])
def test_inbox_profile_spoof_and_ambiguous_urls_are_not_video_evidence(platform,url):
    assert native_video_id(platform,url) is None


def test_missing_remote_post_clears_old_url_and_identity():
    result=observe_post(SimpleNamespace(list_posts=lambda window:[]),{'scheduled_at_utc':DATE},'existing-post')
    assert result['state']=='awaiting_confirmation' and result['release_url'] is None and result['native_post_id'] is None


def test_inbox_reconciliation_never_uploads_schedules_or_creates_again(monkeypatch):
    import json
    import media_release as release_module
    channel={'platform':'tiktok','integration_id':'own-account','content':'approved exact copy','scheduled_at_utc':DATE,'settings':{'__type':'tiktok','privacy_level':'PUBLIC_TO_EVERYONE','content_posting_method':'UPLOAD'}}
    snapshot={'channels':[channel]}
    release=SimpleNamespace(snapshot_json=json.dumps(snapshot),progress_json=json.dumps({'channels':{'own-account':{'post_id':'existing-post','state':'awaiting_confirmation','attempts':1}}}))
    monkeypatch.setattr(release_module,'assert_current',lambda job,revision:snapshot)
    class ExistingPost:
        def list_integrations(self):return [{'id':'own-account','identifier':'tiktok','disabled':False}]
        def list_posts(self,window):return [{'id':'existing-post','state':'PUBLISHED','integration':{'id':'own-account'},'content':channel['content'],'publishDate':DATE,'releaseURL':'https://www.tiktok.com/messages?lang=en'}]
        def upload_file(self,*args,**kwargs):pytest.fail('re-upload existing media')
        def create_draft(self,*args,**kwargs):pytest.fail('duplicate draft')
        def change_status(self,*args,**kwargs):pytest.fail('re-schedule delivered post')
    def save(progress):release.progress_json=json.dumps(progress)
    for _ in range(2):
        result=release_module.distribute(object(),release,ExistingPost(),save)
        assert result['channels']['own-account']['state']=='awaiting_confirmation'
        assert result['channels']['own-account']['post_id']=='existing-post'
        assert result['channels']['own-account']['attempts']==1
