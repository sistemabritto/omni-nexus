"""The existing Harness trust toggle is the single source of application approval."""
import json
import uuid
import base64
import hashlib
import time
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from flask import current_app
from cryptography.fernet import Fernet
from flask_login import current_user
from routes import managed_live_context as live

MUTATING={'create_artifact','create_image','create_media','update_area','write_document','admin_action','adapter_action'}
_APPROVED=ContextVar('live_approved_action',default=None)


def _key(row,action,parameters,guard):
    return (row['user_id'],row['company_id'],row['agent_name'],action,
            hashlib.sha256(json.dumps(parameters,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),guard)


@contextmanager
def approved_execution(row,action,parameters,guard):
    token=_APPROVED.set(_key(row,action,parameters,guard))
    try:yield
    finally:_APPROVED.reset(token)


def require_approved(row,action,parameters,guard):
    if _APPROVED.get()!=_key(row,action,parameters,guard):raise PermissionError('human_approval_required')


def policy():
    from routes.settings import get_chat_settings
    # Uses the same authenticated reader/default as the Harness UI. Never saves it.
    value=get_chat_settings().get_json()
    if type(value.get('trustMode')) is not bool:raise ValueError('harness_policy_unavailable')
    return {'yoloMode':value['trustMode'],'source':'config/workspace.yaml:chat.trustMode'}


def cipher():
    secret=current_app.secret_key
    if not secret:raise ValueError('approval_encryption_unavailable')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(str(secret).encode()).digest()))


def unpack(value):
    return cipher().decrypt(value[4:].encode()).decode() if value.startswith('enc:') else value


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS live_action_approvals(
      id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,
      agent_name TEXT NOT NULL,request_id TEXT NOT NULL,action TEXT NOT NULL,
      parameters TEXT NOT NULL,status TEXT NOT NULL,result TEXT,
      UNIQUE(user_id,company_id,request_id))''')
    columns={r[1] for r in conn.execute('PRAGMA table_info(live_action_approvals)')}
    for name,kind in (('guard','TEXT'),('expires_at','REAL'),('reason','TEXT'),('preview','TEXT')):
        if name not in columns:
            try:conn.execute('ALTER TABLE live_action_approvals ADD COLUMN '+name+' '+kind)
            except sqlite3.OperationalError as exc:
                if 'duplicate column name' not in str(exc):raise


def admit(row,action,parameters,request_id):
    proposal=None
    if action=='adapter_action':
        from live_adapters import prepare,approval_required
        proposal=prepare(row,parameters)
        if not approval_required(parameters):return None
    elif action not in MUTATING or policy()['yoloMode']:return None
    with live._store() as conn:
        ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_action_approvals WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        raw=json.dumps(parameters,sort_keys=True,ensure_ascii=False)
        if prior:
            if prior['action']!=action or unpack(prior['parameters'])!=raw:raise ValueError('idempotency_conflict')
            identifier=prior['id'];status=prior['status']
        else:
            identifier=uuid.uuid4().hex;status='pending'
            conn.execute('INSERT INTO live_action_approvals(id,user_id,company_id,agent_name,request_id,action,parameters,status,guard,expires_at,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(identifier,row['user_id'],row['company_id'],row['agent_name'],request_id,action,'enc:'+cipher().encrypt(raw.encode()).decode(),status,proposal['guard'] if proposal else None,time.time()+900,proposal.get('approvalReason') if proposal else None))
            if proposal:
                from live_workspace_actions import clean
                preview={'scope':proposal['scope'],'target':clean(proposal.get('target'),row['company_id']),'proposalSha256':proposal['guard']}
                conn.execute('UPDATE live_action_approvals SET preview=? WHERE id=?',('enc:'+cipher().encrypt(json.dumps(preview,ensure_ascii=False).encode()).decode(),identifier))
    return {'approvalRequired':status=='pending','approvalId':identifier,'status':status,
            'message':proposal['approvalReason'] if proposal else 'YOLO Mode desligado: confira e aprove no chat do Live. Não repetir a solicitação.'}


def pending(row):
    with live._store() as conn:
        ensure(conn)
        records=conn.execute("SELECT * FROM live_action_approvals WHERE user_id=? AND company_id=? AND status='pending' ORDER BY rowid LIMIT 10",(int(current_user.get_id()),row['company_id'])).fetchall()
    return [{'id':r['id'],'action':r['action'],'agentName':r['agent_name'],'reason':r['reason'],
             'preview':json.loads(unpack(r['preview'])) if r['preview'] else None,
             'expiresAt':r['expires_at'],'parameters':json.loads(unpack(r['parameters'])) if r['action']=='adapter_action' else __import__('live_workspace_actions').clean(json.loads(unpack(r['parameters'])),row['company_id'])} for r in records]
