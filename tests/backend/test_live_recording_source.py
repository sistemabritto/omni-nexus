"""Current recording scripts reuse canonical ACL; no media/reference retrieval."""
import hashlib
import json
from tests.backend.test_live_continuity_endpoints import enabled,bound,post
from tests.backend.test_managed_live_context import setup,read


def seed(app):
    from models import db,Recording,RecordingScript
    with app.app_context():
        for rid,company in [('rec-a',7),('rec-b',8),('broken',7),('missing-current',7)]:
            db.session.add(Recording(id=rid,company_id=company,created_by=31,title='Zephyr roteiro '+rid,
                origin_type='manual',origin_id=rid,script_revision=2,created_at='2026-01-01'))
            for number in (1,2):
                if rid=='missing-current' and number==2:
                    continue
                text=('Zephyr SECRET B' if company==8 else 'Zephyr roteiro corrente' if number==2 else 'Zephyr OLD')
                digest=hashlib.sha256(text.encode()).hexdigest() if rid!='broken' else '0'*64
                db.session.add(RecordingScript(id=rid+'-'+str(number),recording_id=rid,number=number,
                    text=text,sha256=digest,created_at='2026-01-02',
                    references_json=json.dumps([{'label':'external','reference':'https://do-not-fetch.invalid'}])))
        db.session.commit()


def test_query_returns_only_current_script_with_source_revision_hash(enabled,monkeypatch):
    app,c,_,mod,_,_=enabled
    seed(app)
    context=bound(c)
    # Runtime validation remains the fixture; any external request is forbidden.
    original_get=mod.requests.get
    def guarded_get(url,**kwargs):
        assert 'do-not-fetch' not in url
        return original_get(url,**kwargs)
    monkeypatch.setattr(mod.requests,'get',guarded_get)
    response=post(c,context,'query',query='Zephyr')
    assert response.status_code==200
    docs=response.json['documents']['results']
    assert len(docs)==1
    assert docs[0]['reference']=='/api/recordings/rec-a'
    assert docs[0]['revision']==2
    assert docs[0]['sha256']==hashlib.sha256('Zephyr roteiro corrente'.encode()).hexdigest()
    assert docs[0]['text']=='Zephyr roteiro corrente'
    assert 'OLD' not in response.text and 'SECRET B' not in response.text
    assert 'do-not-fetch' not in response.text
    assert post(c,context,'query',query='Zephyr',companyId=8).status_code==400
    post(c,context,'transcript',eventId='question',role='user',text='Zephyr')
    output=read(c,context['contextId'],'provider-a').json
    assert output['queryResult']['documents']['results'][0]['scriptId']=='rec-a-2'


def test_adapter_uses_existing_user_company_grant_and_revocation(enabled):
    app,_,_,_,_,_=enabled
    seed(app)
    from flask_login import login_user
    from models import db,User,RecordingAccess
    from live_recording_source import search_current_scripts
    with app.test_request_context('/'):
        user=db.session.get(User,32);user.role='viewer';db.session.commit();login_user(user)
        assert search_current_scripts(7,['Zephyr'])['status']=='denied'
        db.session.add(RecordingAccess(user_id=32,company_id=7,level='reader'));db.session.commit()
        allowed=search_current_scripts(7,['Zephyr'])
        assert len(allowed['results'])==1
        assert search_current_scripts(8,['Zephyr'])['status']=='denied'
        db.session.delete(db.session.get(RecordingAccess,(32,7)));db.session.commit()
        assert search_current_scripts(7,['Zephyr'])['status']=='denied'


def test_revoked_recording_source_does_not_block_authorized_live_memory(enabled,monkeypatch):
    app,c,_,_,_,_=enabled
    seed(app)
    context=bound(c)
    post(c,context,'notes',requestId='decision',kind='decision',text='Zephyr decisão confirmada',confirmed=True)
    import recordings_access
    from flask import abort
    monkeypatch.setattr(recordings_access,'require_company',lambda *_args,**_kw:abort(404))
    response=post(c,context,'query',query='Zephyr')
    assert response.status_code==200
    assert response.json['documents']['status']=='denied'
    assert response.json['documents']['results']==[]
    assert any('decisão confirmada' in item['text'] for item in response.json['memory'])
