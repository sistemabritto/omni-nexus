"""One-shot image generation. Persistent reservations prevent replayed paid calls.

No automatic recovery/retry after worker loss: the user must inspect an uncertain
request before asking for a new one. Existing provider configuration is read only.
"""
import base64
import hashlib
import struct
import zlib
import json
import os
import threading
import uuid
import requests
from flask import current_app
from flask_login import current_user
from models import has_permission

MODEL='gpt-image-2'


def verify_png(raw):
    if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw)>20000000:raise ValueError('invalid_png')
    offset=8;chunks=0;seen_data=False
    while offset+12<=len(raw):
        length=struct.unpack('>I',raw[offset:offset+4])[0];kind=raw[offset+4:offset+8]
        end=offset+8+length
        if end+4>len(raw) or chunks>4096:raise ValueError('invalid_png')
        if zlib.crc32(raw[offset+4:end])&0xffffffff!=struct.unpack('>I',raw[end:end+4])[0]:raise ValueError('invalid_png_crc')
        if not chunks:
            if kind!=b'IHDR' or length!=13:raise ValueError('invalid_png_header')
            width,height=struct.unpack('>II',raw[offset+8:offset+16])
            if not width or not height or width*height>4000000:raise ValueError('invalid_image_dimensions')
        if kind==b'IDAT':seen_data=True
        offset=end+4;chunks+=1
        if kind==b'IEND':
            if length or offset!=len(raw) or not seen_data:raise ValueError('invalid_png_end')
            return
    raise ValueError('incomplete_png')


def create_image(row,parameters,request_id):
    from routes import live_experience as api
    if not has_permission(current_user.role,'workspace','manage') or not has_permission(current_user.role,'media_jobs','execute'):
        raise PermissionError()
    if (set(parameters)!={'title','prompt','format'} or not isinstance(parameters['title'],str)
            or not 1<=len(parameters['title'].strip())<=160 or not isinstance(parameters['prompt'],str)
            or not 10<=len(parameters['prompt'])<=6000 or api._SECRET.search(parameters['prompt'])
            or parameters['format'] not in ('square','landscape','portrait')):
        raise ValueError('invalid_image')
    key=os.environ.get('OPENAI_API_KEY','').strip()
    if not key:raise ValueError('openai_image_not_configured')
    digest=hashlib.sha256(json.dumps(parameters,sort_keys=True).encode()).hexdigest()
    identifier=uuid.uuid4().hex
    with api.live._store() as conn:
        api.ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_creation_requests WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        if prior:
            if prior['digest']!=digest or prior['kind']!='image':raise ValueError('idempotency_conflict')
            identifier=prior['record_id']
        else:
            pending=conn.execute("SELECT count(*) FROM live_creation_requests WHERE user_id=? AND company_id=? AND kind='image' AND status='processing'",(row['user_id'],row['company_id'])).fetchone()[0]
            if pending:raise ValueError('image_already_processing_inspect_before_retry')
            conn.execute('INSERT INTO live_creation_requests(user_id,company_id,request_id,digest,kind,record_id,status) VALUES(?,?,?,?,?,?,?)',(row['user_id'],row['company_id'],request_id,digest,'image',identifier,'processing'))
            conn.execute('INSERT INTO live_artifacts(id,user_id,company_id,context_id,request_id,digest,title,extension,mime) VALUES(?,?,?,?,?,?,?,?,?)',(identifier,row['user_id'],row['company_id'],row['id'],request_id,digest,parameters['title'].strip(),'png','image/png'))
    item=api.artifact_record(row,identifier)
    api.publish_artifact(row,item)
    if not prior:
        app=current_app._get_current_object()
        threading.Thread(target=generate,args=(app,identifier,dict(parameters),key),daemon=True,name='live-image-'+identifier[:8]).start()
    return {**api.artifact_payload(item),'message':'Imagem solicitada. Consulte os materiais para acompanhar; não repetir automaticamente.'}


def generate(app,identifier,parameters,key):
    from routes import live_experience as api
    status='failed'
    with app.app_context():
        try:
            size={'square':'1024x1024','landscape':'1536x1024','portrait':'1024x1536'}[parameters['format']]
            # Fixed official endpoint; no credential forwarding to arbitrary URLs.
            response=requests.post('https://api.openai.com/v1/images/generations',headers={'Authorization':'Bearer '+key},
                json={'model':MODEL,'prompt':parameters['prompt'],'size':size,'quality':'medium','n':1,'output_format':'png'},
                timeout=(5,180),allow_redirects=False)
            response.raise_for_status()
            encoded=response.json()['data'][0]['b64_json']
            if len(encoded)>28000000:raise ValueError('image_too_large')
            raw=base64.b64decode(encoded,validate=True)
            verify_png(raw)
            root=api.artifact_root()
            if root.is_symlink():raise ValueError('unsafe_root')
            root.mkdir(parents=True,exist_ok=True)
            with (root/(identifier+'.png')).open('xb') as output:output.write(raw)
            status='ready'
        except requests.Timeout:status='uncertain'
        except Exception:
            # Provider bodies, credentials and prompts never enter public errors/logs.
            status='failed'
        finally:
            with api.live._store() as conn:
                api.ensure(conn);conn.execute('UPDATE live_creation_requests SET status=? WHERE record_id=? AND kind=?',(status,identifier,'image'))
