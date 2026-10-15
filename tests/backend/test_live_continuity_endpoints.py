"""Authenticated endpoints, real temporary databases and actual TS dispatcher."""
import json
import os
import subprocess
from pathlib import Path
import pytest
from tests.backend.test_managed_live_context import setup, create, link, read, ORIGIN


@pytest.fixture
def enabled(setup, tmp_path):
    app, client, login, mod, runtime, calls = setup
    app.config.update(NEXUS_LIVE_CONTINUITY_ENABLED=True,
                      NEXUS_LIVE_CONTINUITY_DB=str(tmp_path/'memory.sqlite3'))
    login()
    yield setup


def bound(client, company=7, connection='provider-a'):
    ctx = create(client, company).json
    assert link(client, ctx['contextId'], connection).status_code == 200
    return ctx


def post(client, ctx, action, connection='provider-a', **data):
    return client.post(f"/api/live/omni-context/{ctx['contextId']}/{action}",
                       json={'conversationId': connection, **data}, headers=ORIGIN)


def test_disconnect_reload_reconnect_delivers_persisted_context_to_provider(enabled, tmp_path):
    app,c,login,mod,runtime,calls = enabled
    ctx = bound(c)
    body = dict(eventId='evt-1', role='user', text='Lembrar prazo na terça')
    first = post(c,ctx,'transcript',**body)
    assert first.status_code == 200
    assert post(c,ctx,'transcript',**body).json == first.json
    conflict = post(c,ctx,'transcript',**dict(body,text='payload diferente'))
    assert conflict.status_code == 409
    note = post(c,ctx,'notes',requestId='note-1',kind='pending',text='Entregar na terça',confirmed=True)
    assert note.status_code == 200
    original = read(c,ctx['contextId'],'provider-a').json['continuity']
    assert len(original['current']) == 2
    # New browser/provider connection/runtime; logical conversation stays stable.
    ctx2 = bound(c,connection='provider-b')
    output = read(c,ctx2['contextId'],'provider-b')
    assert output.status_code == 200
    resumed = output.json['continuity']
    assert resumed['logicalConversationId'] == original['logicalConversationId']
    assert resumed['current'] == original['current']
    fixture = tmp_path/'provider-fixture.json'
    fixture.write_text(json.dumps({'context':ctx2,'response':output.json}))
    root = Path(__file__).resolve().parents[2]
    # Existing installed TypeScript only. No npm install/provider SDK activation.
    result = subprocess.run(['node',str(root/'qa/managed-live-context/continuity-provider-test.cjs'),str(fixture)],
                            cwd=root,env={**os.environ},text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'PASS' in result.stdout


def test_company_user_and_provider_binding_acl(enabled):
    app,c,login,mod,runtime,calls = enabled
    a = bound(c)
    post(c,a,'transcript',eventId='x',role='user',text='A secret')
    b = bound(c,8,'provider-b')
    response = read(c,b['contextId'],'provider-b')
    assert 'A secret' not in response.text
    assert post(c,a,'transcript','provider-b',eventId='x',role='user',text='bad').status_code == 403
    login(32)
    assert post(c,a,'continuity').status_code == 403
    login()
    from models import db,Company
    with app.app_context():
        db.session.get(Company,7).status='inactive';db.session.commit()
    assert read(c,a['contextId'],'provider-a').status_code == 403


def test_explicit_new_and_corrections_do_not_resurrect_prior_revisions(enabled):
    _,c,_,_,_,_ = enabled
    a = bound(c)
    note = post(c,a,'notes',requestId='n1',kind='preference',text='Azul',confirmed=True).json
    assert post(c,a,'notes',requestId='n2',kind='preference',text='Verde',confirmed=True,
                eventId=note['event_id'],expectedRevision=1).status_code == 200
    assert 'Azul' not in read(c,a['contextId'],'provider-a').text
    a2 = bound(c,connection='provider-b')
    fresh = post(c,a2,'continuity','provider-b',newConversation=True)
    assert fresh.status_code == 200
    assert fresh.json['current'] == []
    assert post(c,a2,'continuity','provider-b',newConversation=True).status_code == 409


def test_no_tenant_or_verification_injection_and_origin_required(enabled):
    _,c,_,_,_,_ = enabled
    a = bound(c)
    assert post(c,a,'transcript',eventId='x',role='user',text='bad',companyId=8).status_code == 400
    assert post(c,a,'transcript',eventId='x',role='user',text='bad',verified=True).status_code == 400
    assert post(c,a,'notes',requestId='n1',kind='fact',text='bad',confirmed=False).status_code == 400
    assert c.post(f"/api/live/omni-context/{a['contextId']}/transcript",json={}).status_code == 403


def test_previous_work_is_selective_owned_referenced_and_survives_reconnect(enabled,tmp_path):
    app,c,_,_,_,_=enabled
    from models import db,Ticket,TicketComment
    with app.app_context():
        for tid,company,title in [('a',7,'Roteiro lançamento'),('b',8,'Roteiro SECRET B'),('legacy',None,'Roteiro SECRET LEGACY')]:
            db.session.add(Ticket(id=tid,company_id=company,title=title,description='Resultado '+title,
                status='resolved',priority='medium',priority_rank=2,created_by='personal-fixture',created_at='2026-01-01',updated_at='2026-01-02'))
        db.session.add(TicketComment(id='comment-a',ticket_id='a',author='fixture',body='Roteiro aprovado versão dois',created_at='2026-01-03'))
        db.session.commit()
    a=bound(c)
    result=post(c,a,'work-search',query='Qual roteiro anterior?')
    assert result.status_code == 200
    assert len(result.json['results']) == 1
    assert result.json['results'][0]['reference']=='/api/tickets/a'
    assert result.json['results'][0]['comments'][0]['revision']
    assert 'SECRET' not in result.text
    assert post(c,a,'work-search',query='roteiro',companyId=8).status_code==400
    post(c,a,'transcript',eventId='question-1',role='user',text='Qual roteiro anterior?')
    a2=bound(c,connection='provider-b')
    r=read(c,a2['contextId'],'provider-b')
    assert r.status_code==200
    assert r.json['previousWork']['results'][0]['reference']=='/api/tickets/a'
    assert 'SECRET' not in r.text
    fixture=tmp_path/'prior-work-provider.json'
    fixture.write_text(json.dumps({'context':a2,'response':r.json,'expectedReference':'/api/tickets/a'}))
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(['node',str(root/'qa/managed-live-context/continuity-provider-test.cjs'),str(fixture)],cwd=root,text=True,capture_output=True)
    assert result.returncode==0,result.stderr


def test_disabled_flag_does_not_create_continuity_storage(setup,tmp_path):
    app,c,login,_,_,_=setup;login()
    path=tmp_path/'must-not-exist.db';app.config['NEXUS_LIVE_CONTINUITY_DB']=str(path)
    a=bound(c)
    assert post(c,a,'continuity').status_code==503
    assert 'continuity' not in read(c,a['contextId'],'provider-a').json
    assert not path.exists()


def test_written_progress_result_links_are_idempotent_and_replayed(enabled,tmp_path):
    app,c,_,_,_,_=enabled
    from models import db,Ticket
    with app.app_context():
        db.session.add(Ticket(id='job-a',company_id=7,title='Roteiro anterior',description='Entregue revisão 2',
            status='in_progress',priority='medium',priority_rank=2,created_by='personal-fixture',created_at='2026-01-01',updated_at='2026-01-02'))
        db.session.commit()
    a=bound(c)
    progress=post(c,a,'work-events',recordType='ticket',recordId='job-a')
    assert progress.status_code==200
    assert post(c,a,'work-events',recordType='ticket',recordId='job-a').json==progress.json
    assert post(c,a,'work-events',recordType='ticket',recordId='job-a',url='https://invented.invalid').status_code==400
    events=post(c,a,'events').json
    assert len(events['events'])==1
    assert events['events'][0]['kind']=='progress'
    assert events['events'][0]['links']==[{'label':'Trabalho original','url':'/api/tickets/job-a'}]
    cursor=events['next']
    with app.app_context():
        ticket=db.session.get(Ticket,'job-a');ticket.status='resolved';ticket.updated_at='2026-01-03';db.session.commit()
    result=post(c,a,'work-events',recordType='ticket',recordId='job-a')
    assert result.status_code==200
    incremental=post(c,a,'events',after=cursor).json
    assert len(incremental['events'])==1
    assert incremental['events'][0]['kind']=='result'
    a2=bound(c,connection='provider-b')
    assert post(c,a2,'work-events','provider-b',recordType='ticket',recordId='job-a').json==result.json
    replay=post(c,a2,'events','provider-b').json
    assert replay['logicalConversationId']==events['logicalConversationId']
    assert len(replay['events'])==2
    assert post(c,a2,'events','provider-b',after=replay['next']).json['events']==[]
    output=read(c,a2['contextId'],'provider-b').json
    fixture=tmp_path/'written-provider.json'
    fixture.write_text(json.dumps({'context':a2,'response':output,'expectedWrittenReference':'/api/tickets/job-a'}))
    root=Path(__file__).resolve().parents[2]
    process=subprocess.run(['node',str(root/'qa/managed-live-context/continuity-provider-test.cjs'),str(fixture)],cwd=root,text=True,capture_output=True)
    assert process.returncode==0,process.stderr
    # Moving a referenced work item to another company revokes cached text/links.
    with app.app_context():
        db.session.get(Ticket,'job-a').company_id=8;db.session.commit()
    revoked=post(c,a2,'events','provider-b').json['events']
    assert all(e['retracted'] and e['text']=='' and e['links']==[] for e in revoked)
    assert '/api/tickets/job-a' not in str(read(c,a2['contextId'],'provider-b').json['continuity']['current'])


def test_media_links_require_owned_existing_artifact_and_revalidate_download(enabled,tmp_path,monkeypatch):
    app,c,_,mod,_,_=enabled
    from models import db,MediaJob
    import media_workspace
    root=tmp_path/'media';root.mkdir();video=root/'fixture.mp4';video.write_bytes(b'fixture-only')
    monkeypatch.setattr(media_workspace,'media_workspace_root',lambda:root)
    with app.app_context():
        for jid,company in [('media-a',7),('media-b',8),('media-unowned',None)]:
            db.session.add(MediaJob(id=jid,company_id=company,title='Fixture render',platform='instagram',
                width=1080,height=1920,duration_seconds=10,status='ready_for_review',render_path=str(video),
                created_at='fixture',updated_at='fixture'))
        db.session.commit()
    a=bound(c)
    for jid in ('media-b','media-unowned','unknown'):
        assert post(c,a,'work-events',recordType='media_job',recordId=jid).status_code==403
    assert post(c,a,'work-events',recordType='media_job',recordId='media-a').status_code==200
    written=post(c,a,'events').json['events'][0]
    link=written['links'][1]['url']
    assert link.startswith(f"/api/live/omni-context/{a['contextId']}/artifacts/media-a/video")
    assert c.get(link).data==b'fixture-only'
    b=bound(c,8,'provider-b')
    assert c.get(f"/api/live/omni-context/{b['contextId']}/artifacts/media-a/video").status_code==403
    video.unlink()
    assert c.get(link).status_code==404
    assert len(post(c,a,'events').json['events'][0]['links'])==1


def test_event_cursor_corrections_use_same_id_and_invalid_cursor_is_rejected(enabled):
    _,c,_,_,_,_=enabled
    a=bound(c)
    note=post(c,a,'notes',requestId='first',kind='decision',text='Versão 1',confirmed=True).json
    first=post(c,a,'events').json
    post(c,a,'notes',requestId='correct',kind='decision',text='Versão 2',confirmed=True,
         eventId=note['event_id'],expectedRevision=1)
    second=post(c,a,'events',after=first['next']).json
    assert len(second['events'])==1
    assert second['events'][0]['event_id']==note['event_id']
    assert second['events'][0]['revision']==2
    assert post(c,a,'events',after=-1).status_code==400
    assert post(c,a,'events',after=True).status_code==400
