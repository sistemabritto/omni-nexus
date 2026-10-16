"""Real scoped database retrieval; HTTP test executes actual TS dispatcher."""
import json
import subprocess
import threading
from pathlib import Path
import pytest
from tests.backend.test_live_continuity_endpoints import enabled, bound, post
from tests.backend.test_managed_live_context import setup, read


def seed(app):
    from models import db,Ticket
    with app.app_context():
        for i,title in enumerate(('Alpha','Beta','Gamma','Zephyr roteiro')):
            db.session.add(Ticket(id=f'ticket-{i}',company_id=7,title=title,
                description=title+' resultado',status='resolved',priority='medium',priority_rank=2,
                created_by='personal-fixture',created_at=f'2026-01-0{i+1}',updated_at='2026-01-05'))
        for tid,company in [('foreign',8),('legacy',None)]:
            db.session.add(Ticket(id=tid,company_id=company,title='Zephyr SECRET',description='SECRET tenant',
                status='resolved',priority='medium',priority_rank=2,created_by='fixture',created_at='2026-01-01',updated_at='2026-01-01'))
        db.session.commit()


def prepare_history(enabled):
    app,c,_,mod,_,_=enabled
    seed(app)
    previous=bound(c,connection='previous-provider')
    note=post(c,previous,'notes','previous-provider',requestId='note-1',kind='decision',text='Zephyr obsolete',confirmed=True).json
    post(c,previous,'notes','previous-provider',requestId='note-2',kind='decision',text='Zephyr confirmado na terça',confirmed=True,
         eventId=note['event_id'],expectedRevision=1)
    removed=post(c,previous,'notes','previous-provider',requestId='removed',kind='fact',text='Zephyr REMOVED',confirmed=True).json
    post(c,previous,'notes','previous-provider',requestId='remove',kind='fact',text='Zephyr REMOVED',confirmed=True,
         eventId=removed['event_id'],expectedRevision=1,retract=True)
    from live_conversation_store import ConversationStore,Principal
    store=ConversationStore(app.config['NEXUS_LIVE_CONTINUITY_DB'],lambda *_:True)
    for principal in (Principal('32',7),Principal('31',8)):
        cid=store.create_explicit(principal)
        store.record(principal,cid,kind='decision',text='Zephyr SECRET memory',source='fixture',verified=True)
    current=bound(c,connection='current-provider')
    assert post(c,current,'continuity','current-provider',newConversation=True).status_code==200
    return current


def test_query_finds_work_outside_bootstrap_and_current_revisions_of_owned_history(enabled):
    _,c,_,_,_,_=enabled
    current=prepare_history(enabled)
    bootstrap=read(c,current['contextId'],'current-provider').json
    assert all(t['reference']!='/api/tickets/ticket-3' for t in bootstrap['previousWork']['results'])
    result=post(c,current,'query','current-provider',query='Zephyr')
    assert result.status_code==200
    assert result.headers['Cache-Control']=='no-store'
    assert result.json['work']['results'][0]['reference']=='/api/tickets/ticket-3'
    assert any(m['text']=='Zephyr confirmado na terça' and m['revision']==2 for m in result.json['memory'])
    assert 'SECRET' not in result.text and 'obsolete' not in result.text and 'REMOVED' not in result.text
    assert result.json['excluded']==['unowned_mempalace_index','private_dot_history','arbitrary_mcp_execution']
    # Already-registered zero-argument tool can use the latest persisted question.
    post(c,current,'transcript','current-provider',eventId='query-1',role='user',text='Zephyr')
    context=read(c,current['contextId'],'current-provider').json
    assert 'authorized_company_tickets' not in context['queryResult']['coverage']
    assert any(m['text']=='Zephyr confirmado na terça' for m in context['queryResult']['memory'])


def test_query_rejects_model_tenant_session_mcp_and_unbound_conversation(enabled):
    _,c,login,_,_,_=enabled
    current=bound(c)
    for field in ('companyId','userId','sessionId','palace','mcpServer','tool'):
        assert post(c,current,'query',query='Zephyr',**{field:'foreign'}).status_code==400
    for value in ('', 'x'*201, None, 1):
        assert post(c,current,'query',query=value).status_code==400
    assert post(c,current,'query','foreign-provider',query='Zephyr').status_code==403
    login(32)
    assert post(c,current,'query',query='Zephyr').status_code==403


def test_query_does_not_reactivate_tasks_or_import_legacy(enabled,monkeypatch):
    app,c,_,mod,_,_=enabled
    current=bound(c)
    def forbidden(*args,**kwargs):
        raise AssertionError('query must never execute/import global memory')
    monkeypatch.setattr(mod,'submit_internal_task',forbidden)
    import sys
    monkeypatch.setitem(sys.modules,'mempalace',None)
    assert post(c,current,'query',query='Zephyr').status_code==200
    from models import db,Company
    with app.app_context():
        db.session.get(Company,7).status='inactive';db.session.commit()
    assert post(c,current,'query',query='Zephyr').status_code==403


def test_actual_http_query_and_zero_argument_read_reach_real_dispatcher(enabled,tmp_path):
    app,c,_,_,_,_=enabled
    prepare_history(enabled)
    from models import db,User
    with app.app_context():
        db.session.get(User,31).display_name='Isolated HTTP profile';db.session.commit()
    from werkzeug.middleware.proxy_fix import ProxyFix
    from werkzeug.serving import make_server
    app.wsgi_app=ProxyFix(app.wsgi_app,x_host=1)
    # Browser bootstrap/events/audit/source fetches are concurrent; a serial
    # fixture can starve source requests on an idle keep-alive connection.
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    fixture=tmp_path/'query-http.json'
    cookie=c.get_cookie('session',domain='example.test')
    fixture.write_text(json.dumps({'base':f'http://127.0.0.1:{server.server_port}',
                                   'cookie':'session='+cookie.value,
                                   'expectedProfileName':'Isolated HTTP profile'}))
    root=Path(__file__).resolve().parents[2]
    try:
        result=subprocess.run(['node',str(root/'qa/managed-live-context/query-http-tests.cjs'),str(fixture)],
                              cwd=root,text=True,capture_output=True,timeout=30)
        assert result.returncode==0,result.stderr
        assert 'PASS actual HTTP' in result.stdout
    finally:
        server.shutdown();thread.join(timeout=5)


def test_matching_excerpts_preserve_late_ticket_comment_and_memory_evidence(enabled):
    app,c,_,_,_,_=enabled
    current=prepare_history(enabled)
    from models import db,Ticket,TicketComment
    with app.app_context():
        ticket=db.session.get(Ticket,'ticket-3')
        ticket.description='prefix '*120+'Zephyr roteiro autorizado no final'
        db.session.add(TicketComment(id='late-comment',ticket_id=ticket.id,
            body='prefix '*120+'Zephyr detalhe do roteiro',author='fixture',created_at='2026-01-06'))
        db.session.commit()
    post(c,current,'notes','current-provider',requestId='late-note',kind='decision',
         text='prefix '*120+'Zephyr decisão corrente no final',confirmed=True)
    result=post(c,current,'query','current-provider',query='Zephyr')
    assert result.status_code==200
    work=result.json['work']['results'][0]
    assert 'Zephyr roteiro autorizado' in work['text'] and len(work['text'])<=600
    assert 'Zephyr detalhe' in work['comments'][0]['text'] and len(work['comments'][0]['text'])<=600
    assert work['comments'][0]['reference'].endswith('#late-comment')
    assert any('Zephyr decisão corrente' in m['text'] for m in result.json['memory'])
    assert all(len(m['text'])<=600 for m in result.json['memory'])
    assert 'SECRET' not in result.text and 'REMOVED' not in result.text and 'obsolete' not in result.text
    post(c,current,'transcript','current-provider',eventId='late-query',role='user',text='Zephyr')
    context=read(c,current['contextId'],'current-provider').json
    assert 'Zephyr roteiro autorizado' in context['previousWork']['results'][0]['text']
    assert any('Zephyr decisão corrente' in m['text'] for m in context['queryResult']['memory'])


def test_matching_excerpt_handles_literal_terms_unicode_and_absent_matches():
    from live_query_excerpt import matching_excerpt
    assert matching_excerpt('x'*800+'RÓTEIRO validado',['róteiro']).endswith('RÓTEIRO validado')
    assert matching_excerpt('x'*800+'a.b literal',['a.b']).endswith('a.b literal')
    assert matching_excerpt('safe prefix',[])=='safe prefix'
    assert matching_excerpt(None,['term'])==''
