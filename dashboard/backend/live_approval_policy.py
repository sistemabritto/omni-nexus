"""The existing Harness trust toggle is the single source of application approval."""
import json
import uuid
import base64
import hashlib
from flask import current_app
from cryptography.fernet import Fernet
from flask_login import current_user
from routes import managed_live_context as live

MUTATING={'create_artifact','create_image','create_media','update_area','write_document','admin_action'}


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


def admit(row,action,parameters,request_id):
    if action not in MUTATING or policy()['yoloMode']:return None
    with live._store() as conn:
        ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_action_approvals WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        raw=json.dumps(parameters,sort_keys=True,ensure_ascii=False)
        if prior:
            if prior['action']!=action or unpack(prior['parameters'])!=raw:raise ValueError('idempotency_conflict')
            identifier=prior['id'];status=prior['status']
        else:
            identifier=uuid.uuid4().hex;status='pending'
            conn.execute('INSERT INTO live_action_approvals(id,user_id,company_id,agent_name,request_id,action,parameters,status) VALUES(?,?,?,?,?,?,?,?)',(identifier,row['user_id'],row['company_id'],row['agent_name'],request_id,action,'enc:'+cipher().encrypt(raw.encode()).decode(),status))
    return {'approvalRequired':status=='pending','approvalId':identifier,'status':status,'message':'YOLO Mode desligado: confira e aprove no chat do Live. Não repetir a solicitação.'}


def pending(row):
    with live._store() as conn:
        ensure(conn)
        records=conn.execute("SELECT * FROM live_action_approvals WHERE user_id=? AND company_id=? AND status='pending' ORDER BY rowid LIMIT 10",(int(current_user.get_id()),row['company_id'])).fetchall()
    return [{'id':r['id'],'action':r['action'],'agentName':r['agent_name'],'parameters':__import__('live_workspace_actions').clean(json.loads(unpack(r['parameters'])),row['company_id'])} for r in records]
