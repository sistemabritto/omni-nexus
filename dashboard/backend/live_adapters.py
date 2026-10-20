"""Named Live adapters with schemas, native ACL, reviewable effects and backups.

Legacy automation configuration is workspace-global, not a tenant memory store.
Only the server-bound workspace administrator may propose these operations;
every mutation requires an exact human approval, regardless of Harness trust.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path
from flask_login import current_user
from models import Company,db,has_permission,audit
from live_adapter_errors import AdapterError
from live_workspace_actions import native,clean,_SECRET,FIELDS

POLICY=Path(__file__).resolve().parents[2]/'config/live-adapters-access.json'
RESOURCES={'heartbeats':'heartbeats','routines':'config','triggers':'triggers',
           'integrations':'integrations','skills':'skills','materials':'workspace',
           'internet':'integrations','github':'integrations','removal':'config'}
OPERATIONS={
    'heartbeats':{'create','update','configure_alerts','read_alerts'},
    'routines':{'create','update'},
    'triggers':{'create','update'},
    'integrations':{'create','update','test','configuration'},
    'skills':{'execute'},'materials':{'edit'},'internet':{'search'},
    'github':{'commit','ci','rollout','status'},'removal':{'remove'},
}
READS={('heartbeats','read_alerts'),('integrations','configuration'),('internet','search'),('github','status')}
SLUG=r'[a-z0-9][a-z0-9_-]{0,99}'
DAYS={'monday','tuesday','wednesday','thursday','friday','saturday','sunday'}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def binding(row):
    from models import Company,db,has_permission
    if int(current_user.get_id())!=row['user_id'] or current_user.role!='admin':raise PermissionError()
    company=db.session.get(Company,row['company_id'])
    data=json.loads(POLICY.read_text())
    item=next((x for x in data.get('bindings',[]) if x.get('companyId')==row['company_id'] and x.get('userId')==row['user_id'] and x.get('companySlug',company.slug if company else None)==getattr(company,'slug',None)),None)
    if data.get('version')!=1 or not company or company.status!='active' or not item or item.get('workspaceAdministration') is not True:raise PermissionError()
    return data


def parse(row,parameters):
    if set(parameters)!={'adapter','operation','argumentsJson'}:raise ValueError('invalid_adapter_request')
    adapter,operation,raw=(parameters[k] for k in ('adapter','operation','argumentsJson'))
    if not isinstance(adapter,str) or adapter not in OPERATIONS or operation not in OPERATIONS[adapter] or not isinstance(raw,str) or len(raw)>128000 or _SECRET.search(raw):raise ValueError('invalid_adapter_request')
    args=json.loads(raw)
    if not isinstance(args,dict):raise ValueError('invalid_adapter_arguments')
    if _SECRET.search(json.dumps(args,ensure_ascii=False)):raise AdapterError('sensitive_adapter_input')
    binding(row)
    permission='view' if (adapter,operation) in READS or adapter=='skills' else 'execute' if adapter=='triggers' else 'manage'
    if not has_permission(current_user.role,RESOURCES[adapter],permission):raise PermissionError()
    return adapter,operation,args


def approval_required(parameters):
    return (parameters.get('adapter'),parameters.get('operation')) not in READS


def identifier(value,routine=False):
    pattern=r'(daily|weekly|monthly)/[a-z0-9_-]{1,128}' if routine else r'[A-Za-z0-9_-]{1,128}'
    if not isinstance(value,str) or not re.fullmatch(pattern,value):raise ValueError('invalid_adapter_identifier')
    return value


def fields(args,required,optional=()):
    if set(args)-set(required)-set(optional) or not set(required)<=set(args):raise ValueError('invalid_adapter_fields')


def text(value,limit=200):
    if not isinstance(value,str) or not 1<=len(value.strip())<=limit or any(ord(c)<32 for c in value):raise ValueError('invalid_adapter_text')
    return value


def validate_schedule(body,create=False):
    if create and body.get('frequency') not in ('daily','weekly','monthly'):raise ValueError('invalid_schedule')
    if 'time' in body and (not isinstance(body['time'],str) or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',body['time'])):raise ValueError('invalid_schedule')
    if 'interval' in body and (type(body['interval']) is not int or not 1<=body['interval']<=43200):raise ValueError('invalid_schedule')
    if 'day' in body and body['day'] not in DAYS:raise ValueError('invalid_schedule')
    if 'days' in body and (not isinstance(body['days'],list) or not body['days'] or len(body['days'])>7 or any(d not in DAYS for d in body['days'])):raise ValueError('invalid_schedule')
    if 'enabled' in body and type(body['enabled']) is not bool:raise ValueError('invalid_enabled')
    if create and not ('time' in body or 'interval' in body):raise ValueError('missing_schedule')
    if body.get('frequency')=='monthly':raise AdapterError('monthly_scheduler_not_supported')


def _target(adapter,ident):
    if adapter=='routines':
        frequency,slug=identifier(ident,True).split('/')
        data=native('GET','/api/settings/routines')
        target=next((r for r in data.get(frequency,[]) if r.get('slug')==slug),None)
        if target is None:raise AdapterError('adapter_resource_not_found',404)
        return target
    if adapter=='integrations':
        # The native custom integration API has no GET-by-slug route.
        data=native('GET','/api/integrations')
        target=next((r for r in data.get('integrations',[]) if r.get('slug') in (ident,'custom-int-'+ident)),None)
        if target is None:raise AdapterError('adapter_resource_not_found',404)
        return {k:v for k,v in target.items() if k in ('slug','name','description','category','envKeys','kind')}
    path={'heartbeats':'/api/heartbeats/','triggers':'/api/triggers/'}[adapter]+identifier(ident)
    data=native('GET',path)
    keys={'heartbeats':FIELDS['heartbeats']|{'id','wake_triggers','handler','goal_id'},
          'triggers':FIELDS['triggers']|{'id','type','source','action_type','action_payload'}}[adapter]
    return {k:v for k,v in data.items() if k in keys}


def prepare(row,parameters):
    """Validate and resolve a proposal, without making a configuration change."""
    adapter,operation,args=parse(row,parameters)
    target=None;method=path=body=None
    if adapter=='heartbeats':
        if operation=='create':
            fields(args,{'id','agent','interval_seconds','decision_prompt'},{'max_turns','timeout_seconds','wake_triggers'})
            if not re.fullmatch(r'[a-z0-9-]{1,100}',args['id']):raise ValueError('invalid_heartbeat_id')
            body={**args,'enabled':False,'wake_triggers':args.get('wake_triggers',['interval']),
                  'max_turns':args.get('max_turns',10),'timeout_seconds':args.get('timeout_seconds',600)}
            _validate_heartbeat(row,body)
            method,path='POST','/api/heartbeats'
        elif operation=='update':
            fields(args,{'identifier','changes'});ident=identifier(args['identifier']);body=args['changes']
            if not isinstance(body,dict) or not body or set(body)-FIELDS['heartbeats']-{'wake_triggers'}:raise ValueError('invalid_heartbeat_fields')
            target=_target(adapter,ident);_validate_heartbeat(row,body)
            method,path='PATCH','/api/heartbeats/'+ident
        else:
            fields(args,{'identifier'}, {'enabled','categories','cooldownSeconds','quietStart','quietEnd','timezone'} if operation=='configure_alerts' else ())
            ident=identifier(args['identifier']);target=_target(adapter,ident)
            if operation=='configure_alerts':
                from live_heartbeat_alerts import validate,read
                alerts=read(ident);target={'heartbeat':target,'alerts':alerts}
                validate({**alerts['preferences'],**{k:v for k,v in args.items() if k!='identifier'}})
    elif adapter=='routines':
        if operation=='create':
            fields(args,{'name','script','frequency'}, {'time','interval','day','days'})
            text(args['name']);validate_schedule(args,True)
            if args['script'] not in binding(row).get('routineExecutors',[]):raise ValueError('routine_executor_unavailable')
            body={**args,'enabled':False};method,path='POST','/api/settings/routines'
        else:
            fields(args,{'identifier','changes'});ident=identifier(args['identifier'],True);body=args['changes']
            if not isinstance(body,dict) or not body or set(body)-FIELDS['routines']:raise ValueError('invalid_routine_fields')
            validate_schedule(body);target=_target(adapter,ident)
            if 'name' in body:text(body['name'])
            if ident.startswith('monthly/'):raise AdapterError('monthly_scheduler_not_supported')
            method,path='PUT','/api/settings/routines/'+ident
    elif adapter=='triggers':
        if operation=='create':
            fields(args,{'name','type','source','action_type','action_payload','agent'}, {'event_filter','condition'})
            text(args['name'])
            if args['type'] not in ('event','webhook') or args['source'] not in ('github','linear','telegram','discord','stripe','custom'):raise ValueError('invalid_trigger')
            if args['action_type']!='script' or args['action_payload'] not in binding(row).get('routineExecutors',[]):raise ValueError('trigger_executor_unavailable')
            body={k:v for k,v in args.items() if k!='condition'};body['enabled']=False
            method,path='POST','/api/triggers'
        else:
            fields(args,{'identifier','changes'});ident=identifier(args['identifier']);body=args['changes']
            if not ident.isdecimal() or not isinstance(body,dict) or not body or set(body)-FIELDS['triggers']-{'condition'}:raise ValueError('invalid_trigger_fields')
            target=_target(adapter,ident);body=dict(body);method,path='PATCH','/api/triggers/'+ident
        _validate_agent(row,body.get('agent'))
        condition=args.get('condition') if operation=='create' else body.pop('condition',None)
        if condition is not None:
            from live_trigger_conditions import validate
            validate(condition)
            if body.get('event_filter'):raise ValueError('choose_filter_or_condition')
            body['event_filter']={'$condition':condition}
        if 'event_filter' in body and not isinstance(body['event_filter'],dict):raise ValueError('invalid_event_filter')
        if '$condition' in body.get('event_filter',{}):
            from live_trigger_conditions import validate
            if set(body['event_filter'])!={'$condition'}:raise ValueError('invalid_event_filter')
            validate(body['event_filter']['$condition'])
        if 'enabled' in body and type(body['enabled']) is not bool:raise ValueError('invalid_enabled')
    elif adapter=='integrations':
        if operation in ('create','update'):
            fields(args,{'slug','displayName'} if operation=='create' else {'slug'}, {'displayName','description','category','envKeys'})
            slug=args['slug']
            if not isinstance(slug,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,78}[a-z0-9]',slug):raise ValueError('invalid_integration_slug')
            for key in ('displayName','description','category'):
                if key in args:
                    value=text(args[key],500)
                    if any(c in value for c in ('"',"'",'\\')):raise ValueError('invalid_integration_metadata')
            prefix='CUSTOM_'+slug.upper().replace('-','_')+'_'
            keys=args.get('envKeys',[])
            if not isinstance(keys,list) or len(keys)>20 or any(not isinstance(k,str) or not re.fullmatch(prefix+r'[A-Z0-9_]{1,60}',k) for k in keys):raise ValueError('invalid_integration_keys')
            target=_target(adapter,slug) if operation=='update' else None
            method,path,body=('POST','/api/integrations/custom',args) if operation=='create' else ('PATCH','/api/integrations/custom/'+slug,args)
        else:
            fields(args,{'slug'});slug=identifier(args['slug'])
            if operation=='test':
                method,path,body='POST',('/api/integrations/plugin/'+slug+'/test' if slug.startswith('plugin-') else '/api/integrations/'+slug+'/test'),{}
    elif adapter=='removal':
        fields(args,{'area','identifier'})
        area,ident=args['area'],args['identifier']
        if area not in ('heartbeats','routines','triggers','integrations'):raise ValueError('removal_target_unsupported')
        if not has_permission(current_user.role,RESOURCES[area],'manage'):raise PermissionError()
        identifier(ident,area=='routines');target=_target(area,ident)
        if area=='triggers' and not ident.isdecimal():raise ValueError('invalid_trigger_identifier')
        if area=='integrations':
            from routes.live_experience import live
            env=Path(live.WORKSPACE)/'config/.env'
            target={**target,'credentialFileSha256':hashlib.sha256(env.read_bytes()).hexdigest() if env.is_file() else None}
        path={'heartbeats':'/api/heartbeats/','routines':'/api/settings/routines/',
              'triggers':'/api/triggers/','integrations':'/api/integrations/custom/'}[area]+ident
        method,body='DELETE',None
    else:
        from live_adapter_content import prepare as prepare_content
        return prepare_content(row,parameters,adapter,operation,args)
    proof={'target':target,'method':method,'path':path,'body':body,'policy':digest(binding(row))}
    return {'adapter':adapter,'operation':operation,'args':args,'method':method,'path':path,'body':body,
            'target':target,'guard':digest(proof),'scope':'workspace_administration_global',
            'approvalReason':'Configuração global do workspace; confira o alvo e o efeito. Aprovação humana obrigatória mesmo com YOLO ligado.'}


def _validate_agent(row,agent):
    if agent is None:return
    from operational_squad import load_operational_squad
    from routes.live_experience import live
    if not isinstance(agent,str) or not load_operational_squad().get(agent,{}).get('active') or live._scope(row['company_id'],agent) is None:raise PermissionError()


def _validate_heartbeat(row,body):
    _validate_agent(row,body.get('agent'))
    for key,low,high in (('interval_seconds',60,31536000),('max_turns',1,100),('timeout_seconds',30,3600)):
        if key in body and (type(body[key]) is not int or not low<=body[key]<=high):raise ValueError('invalid_heartbeat_value')
    if 'decision_prompt' in body and (not isinstance(body['decision_prompt'],str) or not 20<=len(body['decision_prompt'])<=6000):raise ValueError('invalid_heartbeat_prompt')
    if 'enabled' in body and type(body['enabled']) is not bool:raise ValueError('invalid_enabled')
    if 'wake_triggers' in body:
        from heartbeat_schema import VALID_WAKE_TRIGGERS
        values=body['wake_triggers']
        if not isinstance(values,list) or not values or any(not isinstance(v,str) or v not in VALID_WAKE_TRIGGERS for v in values):raise ValueError('invalid_wake_triggers')


def backup(row,proposal):
    from routes import live_experience as api
    from live_approval_policy import cipher
    root=Path(api.live.WORKSPACE)/'backups/live-adapter-edits';root.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=root/(uuid.uuid4().hex+'.enc')
    import base64
    area=proposal['args'].get('area') if proposal['adapter']=='removal' else proposal['adapter']
    files=[]
    if area=='heartbeats':files=['config/heartbeats.yaml']
    elif area=='routines':files=['config/routines.yaml']
    elif area=='integrations':
        slug=proposal['args'].get('slug',proposal['args'].get('identifier',''))
        files=['.claude/skills/custom-int-'+slug+'/SKILL.md']
        if proposal['adapter']=='removal':files.append('config/.env')
    snapshots={}
    for name in files:
        source=Path(api.live.WORKSPACE)/name
        if source.is_file():
            if source.is_symlink() or source.stat().st_size>2000000:raise ValueError('backup_source_unavailable')
            snapshots[name]=base64.b64encode(source.read_bytes()).decode()
    record=None
    if area=='triggers' and proposal['args'].get('identifier','').isdecimal():
        from models import Trigger
        item=db.session.get(Trigger,int(proposal['args']['identifier']))
        if item:record={column.name:getattr(item,column.name) for column in Trigger.__table__.columns}
    raw=json.dumps({'userId':row['user_id'],'companyId':row['company_id'],'proposal':proposal,
        'filesBase64':snapshots,'databaseRecord':record},ensure_ascii=False,default=str).encode()
    with path.open('xb') as stream:stream.write(cipher().encrypt(raw))
    path.chmod(0o600)
    return path.name


def operate(row,parameters,request_id):
    proposal=prepare(row,parameters)
    adapter,operation,args=proposal['adapter'],proposal['operation'],proposal['args']
    if approval_required(parameters):
        from live_approval_policy import require_approved
        require_approved(row,'adapter_action',parameters,proposal['guard'])
    if (adapter,operation) in READS:
        if adapter=='integrations':return {'configurationUrl':'/integrations','credentialEntry':'integrations_panel_only','message':'Cadastre a credencial no painel. Não envie pelo chat.'}
        if adapter=='heartbeats':
            from live_heartbeat_alerts import read
            return read(args['identifier'])
        from live_adapter_content import execute_read
        return execute_read(row,proposal)
    from routes import live_experience as api
    with api.live._store() as conn:
        api.ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_creation_requests WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        key=digest(parameters)
        if prior:
            if prior['digest']!=key or prior['kind']!='adapter':raise ValueError('idempotency_conflict')
            return {'status':prior['status'],'replayed':True,'message':'Consulte o estado. Não repita uma operação incerta.'}
        conn.execute('INSERT INTO live_creation_requests(user_id,company_id,request_id,digest,kind,record_id,status) VALUES(?,?,?,?,?,?,?)',(row['user_id'],row['company_id'],request_id,key,'adapter',adapter+':'+operation,'uncertain'))
    receipt=backup(row,proposal)
    if adapter=='heartbeats' and operation=='configure_alerts':
        from live_heartbeat_alerts import save
        result=save(row,args)
    elif proposal['method']:
        result=clean(native(proposal['method'],proposal['path'],body=proposal['body']),row['company_id'])
    else:
        from live_adapter_content import execute_write
        result=execute_write(row,proposal,request_id)
    if adapter=='routines' or adapter=='removal' and args['area']=='routines':
        try:native('POST','/api/settings/scheduler/reload',body={})
        except Exception:result={**result,'schedulerReload':'pending; agenda ainda não confirmada'}
    with api.live._store() as conn:conn.execute("UPDATE live_creation_requests SET status='success' WHERE user_id=? AND company_id=? AND request_id=?",(row['user_id'],row['company_id'],request_id))
    audit(current_user,'live_adapter_write',RESOURCES[adapter],adapter+':'+operation)
    return {'adapter':adapter,'operation':operation,'status':'success','data':result,'scope':proposal['scope'],
            'backupId':receipt,**({'credentialEntry':'integrations_panel_only','executorCreated':False} if adapter=='integrations' else {})}


def catalog(row):
    try:policy=binding(row)
    except (PermissionError,OSError,ValueError):return {'status':'scope_not_configured','items':[]}
    import os
    from skill_capability_dispatch import _BINDINGS
    from live_self_healing import _policy
    try:rollout_enabled=_policy().get('rollout',{}).get('enabled') is True
    except (OSError,ValueError):rollout_enabled=False
    return {'status':'available','scope':'workspace_administration_global; memory and materials keep their own company bindings',
            'administrativeWritesRequireHuman':True,'catalogDoesNotAuthorizeExecution':True,
            'skillExecutors':[{'name':b['skill'],'capability':b['id']} for b in _BINDINGS],
            'internet':{'configured':bool(os.environ.get('BRAVE_SEARCH_API_KEY')),'health':'not_inferred_from_credentials'},
            'productionRollout':{'policyEnabled':rollout_enabled,'executable':'requires_verified_workflow_ci_environment_and_human_approval'},
            'routineExecutors':policy.get('routineExecutors',[]),
            'items':[{'adapter':adapter,'operations':sorted(operations)} for adapter,operations in OPERATIONS.items()]}
