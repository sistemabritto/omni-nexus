"""Authenticated result receipts, source revalidation and local voice lookup."""
import json
from tests.backend.test_live_file_sources import files, bind_file
from tests.backend.test_live_continuity_endpoints import enabled, bound, post
from tests.backend.test_managed_live_context import setup, read


def test_receipt_is_private_stable_and_rehydrates_link_without_caching_body(files):
    enabled,_,save=files;app,c,login,mod,_,_=enabled
    path,file=save(text='Zephyr roteiro com evidência sintética')
    ctx=bound(c);binding=bind_file(c,ctx,path)
    result=post(c,ctx,'query',query='Zephyr roteiro');assert result.status_code==200
    receipt=result.json['fileReceipts'][0];url=receipt['reference']
    assert receipt['sha256']==binding['sha256']
    for _ in range(2):
        assert post(c,ctx,'query',query='Zephyr roteiro').json['fileReceipts'][0]['reference']==url
    events=post(c,ctx,'events').json['events']
    found=[e for e in events if e['kind']=='result'];assert len(found)==1
    assert found[0]['links']==[{'label':'Abrir arquivo','url':url}]
    assert 'evidência sintética' in found[0]['text']
    response=c.get(url);assert response.status_code==200 and response.text==file.read_text()
    assert response.mimetype=='text/plain' and response.headers['Cache-Control']=='no-store'
    assert response.headers['X-Content-Type-Options']=='nosniff'
    # Receipt is not a public share; a URL alone has no access authority.
    assert app.test_client().get(url).status_code==401
    login(32);assert c.get(url).status_code==403;login()
    # Metadata only in both receipt table and stored event; displayed text is rebuilt.
    with app.app_context(),mod._store() as conn:
        row=conn.execute('select * from live_file_receipts').fetchone()
        assert 'evidência sintética' not in str(tuple(row))
    from live_conversation_store import ConversationStore,Principal
    store=ConversationStore(app.config['NEXUS_LIVE_CONTINUITY_DB'],lambda *_:True)
    snap=store.snapshot(Principal('31',7),found[0]['logical_id'] if 'logical_id' in found[0] else post(c,ctx,'events').json['logicalConversationId'])
    assert 'evidência sintética' not in str(snap)
    # Reconnect to another context in same owned logical conversation retains result.
    again=bound(c,connection='reconnected')
    restored=post(c,again,'events','reconnected').json['events']
    assert any(e.get('links')==found[0]['links'] for e in restored)
    # Changed source never serves or replays the cached body or old link.
    file.write_text('Zephyr roteiro mudou')
    assert c.get(url).status_code==404
    replay=post(c,again,'events','reconnected').json['events']
    hidden=next(e for e in replay if e['event_id']==found[0]['event_id'])
    assert hidden['retracted'] is True and hidden['links']==[] and hidden['text']==''


def test_revoked_binding_and_other_company_cannot_resolve_receipt(files):
    enabled,_,save=files;_,c,_,_,_,_=enabled
    path,_=save();ctx=bound(c);binding=bind_file(c,ctx,path)
    receipt=post(c,ctx,'query',query='Zephyr').json['fileReceipts'][0]
    foreign=bound(c,8,'foreign')
    assert post(c,foreign,'query','foreign',query='Zephyr').json['fileReceipts']==[]
    assert post(c,foreign,'work-events','foreign',recordType='file_result',recordId=receipt['id']).status_code==403
    post(c,ctx,'file-sources/revoke',id=binding['id'],expectedRevision=1)
    assert c.get(receipt['reference']).status_code==404
    assert not any(e.get('links') for e in post(c,ctx,'events').json['events'])


def test_recording_source_uses_existing_acl_without_workspace_confirmation(enabled):
    from tests.backend.test_live_recording_source import seed
    app,c,_,_,_,_=enabled;seed(app);ctx=bound(c)
    receipt=post(c,ctx,'query',query='Zephyr').json['fileReceipts'][0]
    assert receipt['source']=='recording_script'
    response=c.get(receipt['reference'])
    assert response.status_code==200 and 'roteiro corrente' in response.text
    assert 'OLD' not in response.text and 'SECRET B' not in response.text
    from models import db,Recording
    with app.app_context():
        db.session.get(Recording,'rec-a').company_id=8;db.session.commit()
    assert c.get(receipt['reference']).status_code==404


def test_voice_user_request_automatically_searches_and_places_persistent_link(files,tmp_path):
    import subprocess,threading,os
    from pathlib import Path
    from werkzeug.middleware.proxy_fix import ProxyFix
    from werkzeug.serving import make_server
    enabled,_,save=files;app,c,_,_,_,_=enabled
    path,_=save();ctx=bound(c);bind_file(c,ctx,path)
    save('unbound.md','Zephyr SECRET unbound file')
    app.wsgi_app=ProxyFix(app.wsgi_app,x_host=1)
    server=make_server('127.0.0.1',0,app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    cookie=c.get_cookie('session',domain='example.test')
    fixture=tmp_path/'voice-file.json'
    fixture.write_text(json.dumps({'base':f'http://127.0.0.1:{server.server_port}',
        'cookie':'session='+cookie.value,'voiceFileLookup':True}))
    root=Path(__file__).resolve().parents[2]
    try:
        output=subprocess.run(['node',str(root/'qa/managed-live-context/query-http-tests.cjs'),str(fixture)],
            cwd=root,text=True,capture_output=True,timeout=30,env=dict(os.environ))
        assert output.returncode==0,output.stderr
        assert 'PASS actual HTTP voice file receipt' in output.stdout
    finally:
        server.shutdown();thread.join(timeout=5)


def test_generic_file_request_lists_only_current_authorized_sources_without_reconfirm(files):
    enabled,_,save=files;_,c,_,_,_,_=enabled
    ctx=bound(c)
    first,_=save('plano.md','Conteúdo sintético de planejamento')
    bind_file(c,ctx,first)
    save('fora.md','Conteúdo sem associação autorizada')
    result=post(c,ctx,'query',query='Quais arquivos você tem?')
    assert result.status_code==200
    assert result.json['files']['selection']=='authorized_catalog'
    assert len(result.json['fileReceipts'])==1
    assert result.json['fileReceipts'][0]['title']=='plano.md'
    assert c.get(result.json['fileReceipts'][0]['reference']).status_code==200
    assert 'fora.md' not in result.text


def test_secret_like_recording_is_not_returned_or_receipted(enabled):
    import hashlib
    from tests.backend.test_live_recording_source import seed
    from models import db,RecordingScript
    app,c,_,_,_,_=enabled;seed(app);ctx=bound(c)
    with app.app_context():
        script=db.session.get(RecordingScript,'rec-a-2')
        script.text='Zephyr roteiro password=not-for-the-agent'
        script.sha256=hashlib.sha256(script.text.encode()).hexdigest();db.session.commit()
    result=post(c,ctx,'query',query='Zephyr')
    assert result.status_code==200
    assert result.json['documents']['results']==[] and result.json['fileReceipts']==[]
    assert 'not-for-the-agent' not in result.text


def test_same_chat_renders_private_receipt_link_in_new_tab():
    import subprocess
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(['node','qa/live-file-chat/render-receipt.cjs'],cwd=root,
        text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert 'PASS real chat renders persistent receipt' in result.stdout
