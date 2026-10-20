"""Owned Live capabilities, durable artifacts and entry to the existing media queue."""
import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path
from flask import Blueprint, request, send_file, current_app
from flask_login import current_user
from models import Company, MediaJob, db, has_permission, has_agent_access
from operational_squad import load_operational_squad
from skill_capability_dispatch import _SECRET
from live_adapter_errors import AdapterError
from routes import managed_live_context as live

bp=Blueprint('live_experience', __name__)
ID=re.compile(r'^[a-f0-9]{32}$')


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS live_artifacts(
      id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, company_id INTEGER NOT NULL,
      context_id INTEGER NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL,
      title TEXT NOT NULL, extension TEXT NOT NULL, mime TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(user_id,company_id,request_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS live_creation_requests(
      user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,request_id TEXT NOT NULL,
      digest TEXT NOT NULL,kind TEXT NOT NULL,record_id TEXT NOT NULL,status TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,company_id,request_id))''')


def artifact_root():
    # Dedicated downloads enforce user/company ownership. Keep bytes outside
    # every root exposed by the general Workspace file manager.
    return Path(live.WORKSPACE)/'dashboard/data/live-artifacts'


def artifact_record(row, artifact_id):
    if not ID.fullmatch(artifact_id):
        raise PermissionError()
    with live._store() as conn:
        ensure(conn)
        item=conn.execute('SELECT * FROM live_artifacts WHERE id=? AND user_id=? AND company_id=?',
                          (artifact_id,int(current_user.get_id()),row['company_id'])).fetchone()
    if item is None or live._scope(row['company_id'],row['agent_name']) is None:
        raise PermissionError()
    result=dict(item)
    with live._store() as conn:
        ensure(conn)
        job=conn.execute("SELECT status FROM live_creation_requests WHERE kind='image' AND record_id=?",(artifact_id,)).fetchone()
    result['status']=job['status'] if job else 'ready'
    return result


def artifact_payload(item):
    return {'artifactId':item['id'],'title':item['title'],'format':item['extension'],
            'reference':'/api/live/artifacts/'+item['id'],'status':item.get('status','ready')}


def publish_artifact(row, item):
    store,principal=live._continuity_store(row);logical=live._continuity_id(row)
    if not store or not logical:
        raise ValueError('continuity_unavailable')
    store.record(principal,logical,kind='result',text=json.dumps(artifact_payload(item),ensure_ascii=False),
                 source='/api/live/artifacts/'+item['id'],verified=True,request_key='artifact:'+item['id'])


def create_artifact(row, parameters, request_id):
    if not has_permission(current_user.role,'workspace','manage'):
        raise PermissionError()
    if set(parameters)!={'title','format','content'}:
        raise ValueError('invalid_artifact')
    title,fmt,content=(parameters[k] for k in ('title','format','content'))
    if (not isinstance(title,str) or not 1<=len(title.strip())<=160 or fmt not in ('md','txt','csv','json','svg')
            or not isinstance(content,str) or not 1<=len(content.encode())<=128000 or '\x00' in content or _SECRET.search(content)):
        raise ValueError('invalid_or_sensitive_artifact')
    if fmt=='json':
        json.loads(content)
    if fmt=='svg':
        from xml.etree import ElementTree as ET
        if re.search(r'<!DOCTYPE|<!ENTITY',content,re.I):raise ValueError('unsafe_svg')
        try:svg=ET.fromstring(content)
        except ET.ParseError as exc:raise ValueError('invalid_svg') from exc
        if svg.tag.split('}')[-1]!='svg':raise ValueError('invalid_svg')
        for element in svg.iter():
            if element.tag.split('}')[-1] not in ('svg','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan','title','desc','defs','linearGradient','radialGradient','stop'):
                raise ValueError('unsafe_svg')
            if any(k.lower().startswith('on') or k.split('}')[-1] in ('href','src') or 'url(' in str(v).lower() for k,v in element.attrib.items()):
                raise ValueError('unsafe_svg')
    digest=hashlib.sha256(json.dumps(parameters,sort_keys=True).encode()).hexdigest()
    with live._store() as conn:
        ensure(conn)
        conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_artifacts WHERE user_id=? AND company_id=? AND request_id=?',
                           (row['user_id'],row['company_id'],request_id)).fetchone()
        if prior:
            if prior['digest']!=digest:raise ValueError('idempotency_conflict')
            item=dict(prior)
        else:
            identifier=uuid.uuid4().hex;root=artifact_root();root.mkdir(parents=True,exist_ok=True)
            if root.is_symlink():raise PermissionError()
            with (root/(identifier+'.'+fmt)).open('x',encoding='utf-8') as output:output.write(content)
            mime={'md':'text/markdown','txt':'text/plain','csv':'text/csv','json':'application/json','svg':'image/svg+xml'}[fmt]
            conn.execute('INSERT INTO live_artifacts(id,user_id,company_id,context_id,request_id,digest,title,extension,mime) VALUES(?,?,?,?,?,?,?,?,?)',
                         (identifier,row['user_id'],row['company_id'],row['id'],request_id,digest,title.strip(),fmt,mime))
            item=dict(conn.execute('SELECT * FROM live_artifacts WHERE id=?',(identifier,)).fetchone())
    publish_artifact(row,item)
    return artifact_payload(item)


def assets(row):
    with live._store() as conn:
        ensure(conn)
        items=[artifact_payload(artifact_record(row,x['id'])) for x in conn.execute('SELECT * FROM live_artifacts WHERE user_id=? AND company_id=? ORDER BY created_at DESC,id DESC',
               (row['user_id'],row['company_id'])).fetchall()]
    media=[]
    if has_permission(current_user.role,'media_jobs','view'):
        for job in MediaJob.query.filter_by(company_id=row['company_id']).order_by(MediaJob.created_at.desc()).limit(8).all():
            _,record=live._authorized_work_record(row,'media_job',job.id)
            media.append({'jobId':job.id,'title':str(job.title)[:160],'status':job.status,'links':record.get('links',[])})
    from live_asset_reads import shared_sources
    return {'artifacts':items,'media':media,'sharedMaterials':shared_sources(row),
            'scope':'current_company_and_authorized_user_sources','mediaIsRecentSample':True}


def create_media(row, parameters, request_id):
    if not has_permission(current_user.role,'media_jobs','execute'):
        raise PermissionError()
    if set(parameters)!={'title','brief','durationSeconds','format'}:
        raise ValueError('invalid_media_request')
    if (not isinstance(parameters['title'],str) or not 1<=len(parameters['title'].strip())<=160
            or not isinstance(parameters['brief'],str) or not 10<=len(parameters['brief'])<=6000
            or type(parameters['durationSeconds']) not in (int,float) or not 3<=parameters['durationSeconds']<=120
            or parameters['format'] not in ('vertical','landscape','square')):
        raise ValueError('invalid_media_request')
    job_id='live-'+uuid.uuid5(uuid.NAMESPACE_URL,f"{row['user_id']}:{row['company_id']}:{request_id}").hex
    digest=hashlib.sha256(json.dumps(parameters,sort_keys=True).encode()).hexdigest()
    with live._store() as conn:
        ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_creation_requests WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        if prior and (prior['digest']!=digest or prior['kind']!='video'):raise ValueError('idempotency_conflict')
        if not prior:conn.execute('INSERT INTO live_creation_requests(user_id,company_id,request_id,digest,kind,record_id,status) VALUES(?,?,?,?,?,?,?)',(row['user_id'],row['company_id'],request_id,digest,'video',job_id,'reserved'))
    if prior and not db.session.get(MediaJob,job_id):raise ValueError('media_request_uncertain_do_not_retry_automatically')
    if not prior:
        from routes.media_jobs import create_media_job
        fmt=parameters['format'];width,height={'vertical':(1080,1920),'landscape':(1920,1080),'square':(1080,1080)}[fmt]
        result=create_media_job(data_override={'title':parameters['title'],'brief':parameters['brief'],
            'job_type':'social_clip','company_id':row['company_id'],'platform':'instagram',
            'format':fmt,'width':width,'height':height,'fps':30,'duration_seconds':parameters['durationSeconds'],
            'publication_mode':'draft'}, job_id_override=job_id)
        if isinstance(result,tuple) and result[1]!=201:raise ValueError('media_queue_unavailable')
    kind,record=live._authorized_work_record(row,'media_job',job_id)
    store,principal=live._continuity_store(row);logical=live._continuity_id(row)
    store.record(principal,logical,kind=kind,text=json.dumps({k:v for k,v in record.items() if k!='links'},ensure_ascii=False),
                 source=record['reference'],verified=True,request_key='live-media:'+job_id)
    return {'jobId':job_id,'status':db.session.get(MediaJob,job_id).status,'reference':record['reference'],
            'message':'Criação enviada à fila de mídia. Não está concluída e não foi publicada.'}


@bp.post('/api/live/omni-context/<int:context_id>/experience')
def experience(context_id):
    row,data,denied=live._continuity_request(context_id)
    if denied is not None:return denied
    if (set(data)!={'conversationId','action','parameters','requestId'} or not isinstance(data['parameters'],dict)
            or not isinstance(data['requestId'],str) or not live._ID.fullmatch(data['requestId'])):
        return live._reply({'error':'invalid_experience_request'},400)
    action,parameters=data['action'],data['parameters']
    try:roster=load_operational_squad()
    except (OSError,ValueError):return live._reply({'error':'operational_squad_unavailable'},503)
    from live_approval_policy import admit
    try:approval=admit(row,action,parameters,data['requestId'])
    except AdapterError as exc:return live._reply({'error':exc.code},exc.status)
    except PermissionError:return live._reply({'error':'scope_denied'},403)
    except (ValueError,TypeError,KeyError):return live._reply({'error':'invalid_adapter_request'},400)
    except (OSError,sqlite3.Error):return live._reply({'error':'approval_policy_unavailable'},503)
    return live._reply(approval) if approval is not None else execute(row,action,parameters,data['requestId'],roster)


def execute(row,action,parameters,request_id,roster):
    try:
        if action in ('handoff','create_artifact','create_media','create_image','update_area','write_document','admin_action','adapter_action') and not roster.get(row['agent_name'],{}).get('active'):
            raise PermissionError()
        if action=='handoff':
            if set(parameters)!={'agentName','reason'} or not isinstance(parameters['reason'],str) or len(parameters['reason'])>300:
                raise ValueError('invalid_handoff')
            target=parameters['agentName']
            if not isinstance(target,str) or not roster.get(target,{}).get('active') or live._scope(row['company_id'],target) is None:
                raise PermissionError()
            return live._reply({'agentName':target,'authorized':True})
        if action=='capabilities':
            if set(parameters)-{'query'} or not isinstance(parameters.get('query',''),str) or len(parameters.get('query',''))>150:
                raise ValueError('invalid_query')
            from live_capabilities import skill_catalog,integration_catalog
            from live_adapters import catalog as adapters
            result={'skills':skill_catalog(live.WORKSPACE,parameters.get('query','')),'integrations':integration_catalog(row),'adapters':adapters(row)}
        elif action=='skill':
            if 'name' not in parameters or set(parameters)-{'name','offset'}:raise ValueError('invalid_skill')
            from live_capabilities import read_skill
            result=read_skill(live.WORKSPACE,parameters['name'],parameters.get('offset',0))
        elif action=='assets':
            if parameters:raise ValueError('invalid_assets')
            result=assets(row)
        elif action=='artifact':
            if 'artifactId' not in parameters or set(parameters)-{'artifactId','offset'} or not isinstance(parameters['artifactId'],str):raise ValueError('invalid_artifact')
            from live_asset_reads import read_source,text_page
            if ':' in parameters['artifactId']:return live._reply(read_source(row,parameters['artifactId'],parameters.get('offset',0)))
            item=artifact_record(row,parameters['artifactId']);path=artifact_root()/(item['id']+'.'+item['extension'])
            if path.is_symlink() or artifact_root().is_symlink():raise PermissionError()
            if item['extension']=='png':return live._reply({**artifact_payload(item),'kind':'image_metadata','contentAvailable':False})
            with path.open(encoding='utf-8') as stream:content=stream.read(128001)
            if len(content)>128000:raise ValueError('artifact_too_large')
            if _SECRET.search(content):raise PermissionError()
            result={**artifact_payload(item),**text_page(content,parameters.get('offset',0)),'kind':'untrusted_reference_data'}
        elif action=='create_artifact':result=create_artifact(row,parameters,request_id)
        elif action=='create_media':result=create_media(row,parameters,request_id)
        elif action=='admin_action':
            from live_workspace_actions import admin
            result=admin(row,parameters,request_id)
        elif action=='adapter_action':
            from live_adapters import operate
            result=operate(row,parameters,request_id)
        elif action=='read_document':
            from live_workspace_actions import read_document
            result=read_document(row,parameters)
        elif action=='write_document':
            from live_workspace_actions import write_document
            result=write_document(row,parameters,request_id)
        elif action=='inspect_area':
            from live_workspace_actions import inspect
            result=inspect(row,parameters)
        elif action=='update_area':
            from live_workspace_actions import update
            result=update(row,parameters,request_id)
        elif action=='create_image':
            from live_image_jobs import create_image
            result=create_image(row,parameters,request_id)
        else:raise ValueError('unsupported_action')
        return live._reply(result)
    except AdapterError as exc:
        current_app.logger.warning('live_adapter_failed context=%s agent=%s action=%s reason=%s',row['id'],row['agent_name'],action,exc.code)
        return live._reply({'error':exc.code},exc.status)
    except PermissionError:return live._reply({'error':'scope_denied'},403)
    except (ValueError,TypeError,KeyError):return live._reply({'error':'invalid_or_unavailable_experience_request'},400)
    except (OSError,sqlite3.Error,live.requests.RequestException):return live._reply({'error':'experience_unavailable'},503)


@bp.post('/api/live/omni-context/<int:context_id>/approvals')
def approvals(context_id):
    row,data,denied=live._continuity_request(context_id)
    if denied is not None:return denied
    from live_approval_policy import pending,policy,ensure,unpack,approved_execution
    if set(data)=={'conversationId'}:return live._reply({'pending':pending(row),'policy':policy()})
    if set(data)!={'conversationId','approvalId','decision'} or not isinstance(data['approvalId'],str) or not ID.fullmatch(data['approvalId']) or data['decision'] not in ('approve','reject'):return live._reply({'error':'invalid_approval'},400)
    with live._store() as conn:
        ensure(conn);conn.execute('BEGIN IMMEDIATE')
        item=conn.execute("SELECT * FROM live_action_approvals WHERE id=? AND user_id=? AND company_id=? AND status='pending'",(data['approvalId'],row['user_id'],row['company_id'])).fetchone()
        if not item:return live._reply({'error':'approval_unavailable'},409)
        item=dict(item);conn.execute('UPDATE live_action_approvals SET status=? WHERE id=?',('executing' if data['decision']=='approve' else 'rejected',item['id']))
    if data['decision']=='reject':return live._reply({'status':'rejected'})
    try:
        roster=load_operational_squad()
        if not roster.get(item['agent_name'],{}).get('active') or live._scope(row['company_id'],item['agent_name']) is None:return live._reply({'error':'scope_denied'},403)
        import time
        if item['expires_at'] and item['expires_at']<time.time():
            with live._store() as conn:conn.execute("UPDATE live_action_approvals SET status='expired' WHERE id=?",(item['id'],))
            return live._reply({'error':'approval_expired'},409)
        approved_row={**dict(row),'agent_name':item['agent_name']};parameters=json.loads(unpack(item['parameters']))
        if item['action']=='adapter_action':
            from live_adapters import prepare
            proposal=prepare(approved_row,parameters)
            if proposal['guard']!=item['guard']:
                with live._store() as conn:conn.execute("UPDATE live_action_approvals SET status='stale' WHERE id=?",(item['id'],))
                return live._reply({'error':'approval_target_changed'},409)
        with approved_execution(approved_row,item['action'],parameters,item['guard']):
            result=execute(approved_row,item['action'],parameters,item['request_id'],roster)
        response=result[0] if isinstance(result,tuple) else result
        status='applied' if response.status_code<300 else 'failed'
        with live._store() as conn:conn.execute('UPDATE live_action_approvals SET status=? WHERE id=?',(status,item['id']))
        return result
    except PermissionError:return live._reply({'error':'scope_denied'},403)
    except AdapterError as exc:return live._reply({'error':exc.code},exc.status)
    except (OSError,ValueError,sqlite3.Error):return live._reply({'error':'approval_result_uncertain'},503)


@bp.post('/api/live/omni-context/<int:context_id>/attachments')
def attach(context_id):
    denied=live._guard(write=True)
    if denied is not None:return denied
    row=live._owned(context_id)
    if row is None or not row['conversation_id'] or request.form.get('conversationId')!=row['conversation_id']:
        return live._reply({'error':'scope_denied'},403)
    if request.content_length is None or request.content_length>140000:
        return live._reply({'error':'attachment_too_large'},413)
    file=request.files.get('file')
    if file is None or Path(file.filename or '').suffix.lower() not in ('.txt','.md','.csv','.json'):
        return live._reply({'error':'unsupported_attachment'},400)
    try:
        try:roster=load_operational_squad()
        except (OSError,ValueError):return live._reply({'error':'operational_squad_unavailable'},503)
        if not roster.get(row['agent_name'],{}).get('active'):raise PermissionError()
        if current_app.config.get('NEXUS_LIVE_CONTINUITY_ENABLED') is not True:return live._reply({'error':'continuity_disabled'},503)
        runtime=live.requests.get(live.TERMINAL_HTTP_BASE+'/api/sessions/'+row['runtime_session_id'],timeout=(3,10),allow_redirects=False)
        runtime.raise_for_status()
        if runtime.json().get('id')!=row['runtime_session_id']:raise PermissionError()
        content=file.read(128001).decode('utf-8');fmt=Path(file.filename).suffix[1:].lower()
        result=create_artifact(row,{'title':Path(file.filename).name[:160],'format':fmt,'content':content},'upload-'+uuid.uuid4().hex)
        return live._reply(result,201)
    except (ValueError,UnicodeError):return live._reply({'error':'invalid_or_sensitive_attachment'},400)
    except PermissionError:return live._reply({'error':'scope_denied'},403)
    except (OSError,sqlite3.Error,live.requests.RequestException):return live._reply({'error':'attachment_unavailable'},503)


@bp.get('/api/live/artifacts/<artifact_id>')
def download(artifact_id):
    denied=live._guard()
    if denied is not None:return denied
    try:
        if not ID.fullmatch(artifact_id):raise PermissionError()
        with live._store() as conn:
            ensure(conn);item=conn.execute('SELECT * FROM live_artifacts WHERE id=? AND user_id=?',(artifact_id,int(current_user.get_id()))).fetchone()
        if not item or Company.query.filter_by(id=item['company_id'],status='active').first() is None or not has_permission(current_user.role,'workspace','view'):
            raise PermissionError()
        root=artifact_root()
        path=root/(item['id']+'.'+item['extension'])
        if root.is_symlink() or path.is_symlink() or not path.is_file():raise PermissionError()
        response=send_file(path,mimetype=item['mime'],as_attachment=True,download_name=item['title'].removesuffix('.'+item['extension'])+'.'+item['extension'])
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"})
        return response
    except (PermissionError,OSError):return live._reply({'error':'artifact_unavailable'},404)
