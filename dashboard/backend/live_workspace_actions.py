"""Named adapters to existing dashboard routes, under the real human session.

Only fixed loopback routes receive the caller's existing cookie. No service-token
substitution, arbitrary URL, shell, credential changes or automatic retries.
"""
import hashlib
import json
import re
import requests
from flask import current_app,request
from models import db,Ticket,GoalProject,Goal,has_permission
from skill_capability_dispatch import _SECRET as _BASE_SECRET
_SECRET=re.compile(_BASE_SECRET.pattern+r"|(?:senha|password|secret|token|api[_ -]?key)\s*[:=]\s*\S+",re.I)

AREAS={
 'github':('', 'integrations'),
 'heartbeats':('/api/heartbeats','heartbeats'), 'routines':('/api/settings/routines','config'),
 'triggers':('/api/triggers','triggers'), 'integrations':('/api/integrations','integrations'),
 'skills':('/api/skills','skills'), 'mcp':('/api/mcp-servers','config'),
 'plugins':('/api/plugins','plugins'), 'knowledge':('/api/knowledge/connections','knowledge'),
 'memory':('/api/memory','memory'), 'mempalace':('/api/mempalace/status','mempalace'),
 'costs':('/api/costs','costs'), 'providers':('/api/providers','config'),
 'missions':('/api/missions','goals'), 'projects':('/api/projects','goals'),
 'goals':('/api/goals','goals'), 'tickets':('/api/tickets','tickets'),
 'materials':('/api/workspace/tree','workspace')}
FIELDS={
 'heartbeats':{'agent','interval_seconds','max_turns','timeout_seconds','enabled','decision_prompt'},
 'routines':{'name','time','interval','day','days','enabled'},
 'triggers':{'name','agent','enabled','event_filter'},
 'projects':{'slug','title','description','status','due_date','mission_id'},
 'goals':{'slug','title','description','status','due_date','project_id','target_value','current_value'},
 'tickets':{'title','description','status','priority','assignee_agent','project_id','goal_id','due_date'}}


def clean(value,company):
    if isinstance(value,list):return [clean(x,company) for x in value[:40] if not isinstance(x,dict) or x.get('company_id') in (None,company)]
    if isinstance(value,dict):return {str(k):clean(v,company) for k,v in value.items() if not re.search(r'(?i)(secret|token|password|senha|dsn|env|credential|api.?key|authorization)',str(k))}
    if isinstance(value,str):
        if value.lstrip().startswith(('{','[')):
            try:return json.dumps(clean(json.loads(value),company),ensure_ascii=False)
            except ValueError:pass
        return '[conteúdo sensível omitido]' if _SECRET.search(value) else value[:2000]
    return value


def native(method,path,body=None,params=None):
    cookie_name=current_app.config.get('SESSION_COOKIE_NAME','session');cookie=request.cookies.get(cookie_name)
    if not cookie:raise PermissionError('human_cookie_required')
    response=requests.request(method,'http://127.0.0.1:8080'+path,
        headers={'Cookie':cookie_name+'='+cookie,'Origin':request.headers.get('Origin',''),'X-Requested-With':'XMLHttpRequest'},
        json=body,params=params,timeout=(3,20),allow_redirects=False)
    if response.status_code in (401,403):raise PermissionError('native_permission_denied')
    if not 200<=response.status_code<300:raise ValueError('native_operation_failed_'+str(response.status_code))
    return response.json()


def inspect(row,parameters):
    if 'area' not in parameters or set(parameters)-{'area','identifier','page'} or parameters['area'] not in AREAS:raise ValueError('unsupported_area')
    area=parameters['area'];path,resource=AREAS[area]
    if not has_permission(__import__('flask_login').current_user.role,resource,'view'):raise PermissionError()
    if area=='github':
        from live_github import read
        return read(row,parameters.get('identifier'),parameters.get('page',1))
    if area=='mempalace':
        from live_mempalace import inspect as inspect_memory
        return inspect_memory(row,parameters.get('identifier'),parameters.get('page',1))
    if 'page' in parameters:raise ValueError('unsupported_page')
    if area=='skills':
        from live_capabilities import skill_catalog
        if 'identifier' in parameters:raise ValueError('use_read_omni_skill')
        return {'area':area,'scope':'workspace','data':skill_catalog(__import__('routes.live_experience',fromlist=['live']).live.WORKSPACE)}
    if area=='materials':
        from live_asset_reads import shared_sources
        if 'identifier' in parameters:raise ValueError('use_read_omni_artifact')
        return {'area':area,'scope':'active_company_and_user','data':shared_sources(row)}
    if area=='heartbeats':
        identifier=parameters.get('identifier')
        if identifier is not None:
            if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',identifier):raise ValueError('invalid_identifier')
            data=clean(native('GET',path+'/'+identifier),row['company_id'])
        else:
            from operational_squad import load_operational_squad
            roster=load_operational_squad()
            raw=native('GET',path)
            # Project only summary fields BEFORE the generic sanitizer's list cap.
            fields=('id','agent','enabled','interval_seconds','last_run_at','last_status','goal_id')
            items=[{**clean({k:item[k] for k in fields if k in item},row['company_id']),
                    'legacy':not roster.get(item.get('agent'),{}).get('active',False)}
                   for item in raw['heartbeats'] if item.get('company_id') in (None,row['company_id'])]
            data={'heartbeats':items,'total':len(items),'truncated':False,
                  'detailTool':'inspect_omni_area(area=heartbeats, identifier=<id>)'}
        return {'area':area,'scope':'workspace_authorized_by_native_route','data':data,
                'editableFields':sorted(FIELDS[area]),'credentialFieldsExposed':False}
    if 'identifier' in parameters:raise ValueError('unsupported_identifier')
    params={'company_id':row['company_id']} if area in ('projects','goals','tickets') else {'path':'workspace'} if area=='materials' else None
    data=clean(native('GET',path,params=params),row['company_id'])
    # Mission records are global; their project children remain company filtered.
    result={'area':area,'scope':'active_company' if area in ('projects','goals','tickets','materials') else 'workspace','data':data,
            'editableFields':sorted(FIELDS.get(area,[])),'credentialFieldsExposed':False}
    if len(json.dumps(result,ensure_ascii=False))>18000:
        result={'area':area,'scope':result['scope'],'data':str(json.dumps(data,ensure_ascii=False))[:14000],'truncated':True,'editableFields':result['editableFields']}
    return result


def update(row,parameters,request_id):
    from flask_login import current_user
    from routes import live_experience as api
    if set(parameters)!={'area','identifier','changesJson'}:raise ValueError('invalid_workspace_update')
    area,identifier,raw=(parameters[k] for k in ('area','identifier','changesJson'))
    if area=='github':
        if not isinstance(raw,str) or len(raw)>128000:raise ValueError('invalid_github_write')
        from live_github import write
        change=json.loads(raw)
        if not isinstance(change,dict) or not isinstance(identifier,str) or identifier!='/'.join(str(change.get('path','')).split('/')[1:3]):raise ValueError('github_identifier_mismatch')
        return write(row,change,request_id)
    if area not in FIELDS or not isinstance(identifier,str) or not isinstance(raw,str) or len(raw)>12000 or _SECRET.search(raw):raise ValueError('unsupported_workspace_update')
    body=json.loads(raw)
    if not isinstance(body,dict) or not body or set(body)-FIELDS[area]:raise ValueError('unsupported_fields')
    resource=AREAS[area][1];permission='execute' if area=='triggers' else 'manage'
    if not has_permission(current_user.role,resource,permission):raise PermissionError()
    if area in ('projects','goals','tickets'):
        model={'projects':GoalProject,'goals':Goal,'tickets':Ticket}[area]
        if area!='tickets' and not identifier.isdecimal():raise ValueError('invalid_identifier')
        record=db.session.get(model,identifier if area=='tickets' else int(identifier))
        owner=record.project.company_id if area=='goals' and record else getattr(record,'company_id',None)
        if not record or owner!=row['company_id']:raise PermissionError()
        for key in ('project_id','goal_id'):
            if key in body:
                parent=db.session.get(GoalProject if key=='project_id' else Goal,body[key])
                company=parent.project.company_id if key=='goal_id' and parent else getattr(parent,'company_id',None)
                if not parent or company!=row['company_id']:raise PermissionError()
    if 'agent' in body or 'assignee_agent' in body:
        from operational_squad import load_operational_squad
        name=body.get('agent',body.get('assignee_agent'))
        if not api.live._scope(row['company_id'],name) or not load_operational_squad().get(name,{}).get('active'):raise PermissionError()
    if 'enabled' in body and type(body['enabled']) is not bool:raise ValueError('invalid_enabled')
    if area=='routines':
        if not re.fullmatch(r'(daily|weekly|monthly)/[a-zA-Z0-9_-]{1,128}',identifier):raise ValueError('invalid_routine')
        path='/api/settings/routines/'+identifier;method='PUT'
    else:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',identifier):raise ValueError('invalid_identifier')
        path=AREAS[area][0]+'/'+identifier;method='PATCH'
    digest=hashlib.sha256(json.dumps(parameters,sort_keys=True).encode()).hexdigest()
    with api.live._store() as conn:
        api.ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_creation_requests WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        if prior:
            if prior['digest']!=digest or prior['kind']!='workspace':raise ValueError('idempotency_conflict')
            return {'area':area,'identifier':identifier,'status':prior['status'],'replayed':True,'message':'Solicitação já recebida. Consulte a área; não executar novamente.'}
        conn.execute('INSERT INTO live_creation_requests(user_id,company_id,request_id,digest,kind,record_id,status) VALUES(?,?,?,?,?,?,?)',(row['user_id'],row['company_id'],request_id,digest,'workspace',area+':'+identifier,'uncertain'))
    result=clean(native(method,path,body=body),row['company_id'])
    with api.live._store() as conn:conn.execute("UPDATE live_creation_requests SET status='success' WHERE user_id=? AND company_id=? AND request_id=?",(row['user_id'],row['company_id'],request_id))
    if area=='routines':
        try:native('POST','/api/settings/scheduler/reload',body={})
        except (ValueError,PermissionError,requests.RequestException):result={'saved':True,'schedulerReload':'pending; solicite recarga antes de afirmar que a agenda está ativa'}
    from models import audit
    audit(current_user,'live_workspace_update',resource,f'{area}:{identifier}; fields='+','.join(sorted(body)))
    return {'area':area,'identifier':identifier,'status':'success','data':result,'nativePermissionsApplied':True}


def write_document(row,parameters,request_id):
    """Edit known documents with content hash, durable backup and native path ACL."""
    from pathlib import Path
    import os,shutil,uuid
    from flask_login import current_user
    from routes import live_experience as api
    from routes.workspace import _resolve_safe,_check_folder_access,_audit
    if set(parameters)!={'area','name','content','expectedSha256'}:raise ValueError('invalid_document')
    area,name,content,expected=(parameters[k] for k in ('area','name','content','expectedSha256'))
    if area not in ('skills','memory','materials') or not isinstance(name,str) or not isinstance(content,str) or len(content.encode())>128000 or _SECRET.search(content) or '\x00' in content or not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected):raise ValueError('invalid_document')
    if not has_permission(current_user.role,'workspace','manage'):raise PermissionError()
    if area=='skills':
        if not has_permission(current_user.role,'config','manage') or not re.fullmatch('[A-Za-z0-9_-]{1,100}',name):raise PermissionError()
        relative='.claude/skills/'+name+'/SKILL.md'
    elif area=='memory':
        if not has_permission(current_user.role,'memory','manage') or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}\.md',name):raise PermissionError()
        relative='.claude/agent-memory/'+row['agent_name']+'/'+name
    else:
        candidate=Path(name)
        if candidate.is_absolute() or '..' in candidate.parts or candidate.suffix.lower() not in ('.md','.txt','.csv','.json'):raise ValueError('invalid_material_path')
        relative='workspace/'+str(candidate)
    path=_resolve_safe(relative,require_admin=area!='materials');_check_folder_access(relative)
    if not path.is_file() or path.is_symlink():raise ValueError('document_not_found')
    original=path.read_bytes()
    if hashlib.sha256(original).hexdigest()!=expected:raise ValueError('document_changed_read_again')
    if _SECRET.search(original.decode('utf-8')):raise PermissionError()
    backup=Path(api.live.WORKSPACE)/'backups/live-document-edits'/uuid.uuid4().hex
    backup.mkdir(mode=0o700,parents=True);shutil.copy2(path,backup/path.name)
    if (backup/path.name).read_bytes()!=original:raise ValueError('backup_failed')
    temporary=path.with_name(path.name+'.live-'+uuid.uuid4().hex)
    try:
        with temporary.open('x',encoding='utf-8') as out:out.write(content)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('document_changed_read_again')
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()
    _audit('live_document_update',relative,bytes=len(content.encode()))
    return {'area':area,'name':name,'status':'success','sha256':hashlib.sha256(content.encode()).hexdigest(),'backupPreserved':True}


def read_document(row,parameters):
    from pathlib import Path
    from flask_login import current_user
    from routes.workspace import _resolve_safe,_check_folder_access
    if set(parameters)!={'area','name'}:raise ValueError('invalid_document')
    area,name=parameters['area'],parameters['name']
    if not isinstance(name,str) or not has_permission(current_user.role,'workspace','view'):raise PermissionError()
    if area=='skills' and re.fullmatch('[A-Za-z0-9_-]{1,100}',name):
        if not has_permission(current_user.role,'skills','view'):raise PermissionError()
        relative='.claude/skills/'+name+'/SKILL.md'
    elif area=='skills' and name.startswith('squad-role-library/'):
        role=name.removeprefix('squad-role-library/')
        from agent_roster import retirements
        from routes import live_experience as api
        if retirements(api.live.WORKSPACE).get(role)!=row['agent_name']:raise PermissionError()
        relative='.claude/skills/squad-role-library/references/'+role+'.md'
    elif area=='memory':
        if not has_permission(current_user.role,'memory','view'):raise PermissionError()
        candidate=Path(name)
        if candidate.is_absolute() or '..' in candidate.parts or candidate.suffix.lower() not in ('.md','.txt','.json'):raise ValueError('invalid_memory_path')
        if len(candidate.parts)>1:
            from agent_roster import retirements
            from routes import live_experience as api
            if len(candidate.parts)<3 or candidate.parts[0]!='imported-roles' or retirements(api.live.WORKSPACE).get(candidate.parts[1])!=row['agent_name']:raise PermissionError()
        relative='.claude/agent-memory/'+row['agent_name']+'/'+name
    elif area=='materials' and not Path(name).is_absolute() and '..' not in Path(name).parts and Path(name).suffix.lower() in ('.md','.txt','.csv','.json'):
        relative='workspace/'+name
    else:raise ValueError('invalid_document')
    path=_resolve_safe(relative,require_admin=area!='materials');_check_folder_access(relative)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>128000:raise ValueError('document_unavailable')
    raw=path.read_bytes();text=raw.decode('utf-8')
    if _SECRET.search(text):raise PermissionError()
    return {'area':area,'name':name,'content':text[:12000],'truncated':len(text)>12000,'sha256':hashlib.sha256(raw).hexdigest(),'kind':'untrusted_reference_data','scope':'workspace_reference; do not infer company ownership'}


def admin(row,parameters,request_id):
    """Higher-impact native operations: application approval is handled by admit()."""
    from flask_login import current_user
    if set(parameters)!={'operation','argumentsJson'} or not has_permission(current_user.role,'config','manage'):raise PermissionError()
    if not isinstance(parameters['argumentsJson'],str) or len(parameters['argumentsJson'])>12000:raise ValueError('invalid_admin_arguments')
    args=json.loads(parameters['argumentsJson']);operation=parameters['operation']
    if not isinstance(args,dict):raise ValueError('invalid_admin_arguments')
    if operation=='select_provider' and set(args)=={'providerId'}:
        method,path,body='POST','/api/providers/active',{'provider_id':args['providerId']}
    elif operation=='configure_provider' and set(args)=={'providerId','envVars'}:
        identifier=args['providerId']
        if not isinstance(identifier,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',identifier) or not isinstance(args['envVars'],dict) or not all(isinstance(v,str) for v in args['envVars'].values()):raise ValueError('invalid_provider')
        method,path,body='POST','/api/providers/'+identifier+'/config',{'env_vars':args['envVars']}
    elif operation=='enable_plugin' and set(args)=={'slug','enabled'}:
        if not isinstance(args['slug'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',args['slug']) or type(args['enabled']) is not bool:raise ValueError('invalid_plugin')
        method,path,body='PATCH','/api/plugins/'+args['slug'],{'enabled':args['enabled']}
    elif operation=='install_plugin' and set(args)=={'sourceUrl'}:
        from urllib.parse import urlsplit
        value=urlsplit(args['sourceUrl'])
        if value.scheme!='https' or not value.hostname or value.username or value.password:raise ValueError('invalid_plugin_source')
        method,path,body='POST','/api/plugins/install',{'source_url':args['sourceUrl'],'skip_scan':False,'confirmed_verdict':'WARN'}
    elif operation=='test_knowledge' and set(args)=={'connectionId'}:
        if not isinstance(args['connectionId'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',args['connectionId']):raise ValueError('invalid_connection')
        method,path,body='POST','/api/knowledge/connections/'+args['connectionId']+'/test',{}
    else:raise ValueError('unsupported_admin_operation')
    # One shot reservation, including failures/timeouts, prevents repeated installs/config writes.
    from routes import live_experience as api
    digest=hashlib.sha256(json.dumps(parameters,sort_keys=True).encode()).hexdigest()
    with api.live._store() as conn:
        api.ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_creation_requests WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        if prior:
            if prior['digest']!=digest or prior['kind']!='admin':raise ValueError('idempotency_conflict')
            return {'operation':operation,'status':prior['status'],'replayed':True,'message':'Consulte o estado antes de qualquer nova tentativa.'}
        conn.execute('INSERT INTO live_creation_requests(user_id,company_id,request_id,digest,kind,record_id,status) VALUES(?,?,?,?,?,?,?)',(row['user_id'],row['company_id'],request_id,digest,'admin',operation,'uncertain'))
    result=clean(native(method,path,body=body),row['company_id'])
    with api.live._store() as conn:conn.execute("UPDATE live_creation_requests SET status='success' WHERE user_id=? AND company_id=? AND request_id=?",(row['user_id'],row['company_id'],request_id))
    from models import audit
    audit(current_user,'live_admin_action','config',operation) # Never log argument/credential values.
    return {'operation':operation,'status':'success','data':result,'nativePermissionsApplied':True}
