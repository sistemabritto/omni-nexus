"""Metadata-only audit persistence and browser-session isolation."""
import json
import sqlite3
import subprocess
from pathlib import Path
from tests.backend.test_live_continuity_endpoints import enabled,bound,post
from tests.backend.test_managed_live_context import setup


def audit(c,ctx,stage='received',**extra):
    return post(c,ctx,'tool-audit',toolCallId='audit-call',toolName='read_current_omni_session',stage=stage,**extra)


def test_persistent_metadata_duplicate_and_payload_rejection(enabled):
    app,c,_,_,_,_=enabled
    a=bound(c)
    assert audit(c,a).json=={'recorded':True}
    assert audit(c,a).json=={'recorded':True}
    assert post(c,a,'tool-audit',toolCallId='__live_audit_session__',toolName='session',stage='instrumented').status_code==200
    assert post(c,a,'tool-audit',toolCallId='bad',toolName='session',stage='dispatch').status_code==400
    for stage in ('dispatch','response','send_attempt','sent_to_sdk'):
        assert audit(c,a,stage).status_code==200
    result=post(c,a,'tool-audit/read',toolCallId='audit-call')
    assert result.status_code==200
    assert result.headers['Cache-Control']=='no-store'
    assert [e['stage'] for e in result.json['events']]==['received','dispatch','response','send_attempt','sent_to_sdk']
    assert 'not_provider_ack' in result.json['deliveryEvidence']
    for key in ('parameters','query','result','error','payload','userId','companyId'):
        assert audit(c,a,**{key:'PRIVATE_SECRET'}).status_code==400
    assert audit(c,a,stage='PRIVATE_SECRET').status_code==400
    assert post(c,a,'tool-audit',toolCallId='audit-call',toolName='search_omni_context',stage='received').status_code==400
    with sqlite3.connect(app.config['NEXUS_LIVE_CONTEXT_DB']) as db:
        rows=db.execute('SELECT * FROM live_tool_audit').fetchall()
        assert len(rows)==6
        assert 'PRIVATE_SECRET' not in str(rows)
        columns=[x[1] for x in db.execute('PRAGMA table_info(live_tool_audit)')]
        assert 'parameters' not in columns and 'result' not in columns


def test_audit_cannot_cross_user_company_provider_or_revoked_context(enabled):
    app,c,login,_,_,_=enabled
    a=bound(c);assert audit(c,a).status_code==200
    b=bound(c,8,'provider-b')
    assert post(c,b,'tool-audit/read','provider-b').json['events']==[]
    assert post(c,a,'tool-audit/read','provider-b').status_code==403
    login(32)
    assert post(c,a,'tool-audit/read').status_code==403
    login()
    from models import db,Company
    with app.app_context():
        db.session.get(Company,7).status='inactive';db.session.commit()
    assert post(c,a,'tool-audit/read').status_code==403
    assert audit(c,a).status_code==403


def test_audit_exists_before_source_http_and_send_is_reported_separately(enabled,tmp_path):
    app,c,_,_,_,_=enabled
    a=bound(c)
    # Zero tool callbacks means zero persisted stages, not fabricated invocations.
    assert post(c,a,'tool-audit/read').json['events']==[]
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(['node',str(root/'qa/managed-live-context/tool-audit-tests.cjs')],cwd=root,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert 'PASS metadata trace ordering' in result.stdout
