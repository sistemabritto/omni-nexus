"""Adapters for existing skill execution, bound text edits, search and CI jobs."""
import hashlib
import ipaddress
import json
import os
import re
from datetime import datetime,timezone
from urllib.parse import urlsplit
import requests
from live_adapter_errors import AdapterError


def prepare(row,parameters,adapter,operation,args):
    from live_adapters import fields,digest,binding
    target=None
    if adapter=='materials':
        fields(args,{'artifactId','content','expectedSha256'})
        if not isinstance(args['content'],str) or not 1<=len(args['content'].encode())<=128000 or '\x00' in args['content']:raise ValueError('invalid_material_content')
        if not isinstance(args['expectedSha256'],str) or not re.fullmatch('[a-f0-9]{64}',args['expectedSha256']):raise ValueError('invalid_material_digest')
        target=_material(row,args['artifactId'])
        if target['sha256']!=args['expectedSha256']:raise AdapterError('material_changed_read_again',409)
    elif adapter=='skills':
        fields(args,{'name','capability','input'})
        from skill_capability_dispatch import _BINDINGS,_read_skill
        selected=next((s for s in _BINDINGS if s['id']==args['capability'] and s['skill']==args['name']),None)
        if selected is None:raise AdapterError('skill_executor_unavailable')
        fields(args['input'],{'query'})
        if not isinstance(args['input']['query'],str) or not 1<=len(args['input']['query'])<=200:raise ValueError('invalid_skill_input')
        from routes.live_experience import live
        target={'skillSha256':_read_skill(live.WORKSPACE,args['name'])['sha256']}
    elif adapter=='internet':
        fields(args,{'query'},{'count','freshness','domains'})
        if not isinstance(args['query'],str) or not 1<=len(args['query'])<=300:raise ValueError('invalid_search_query')
        if type(args.get('count',5)) is not int or not 1<=args.get('count',5)<=10:raise ValueError('invalid_search_count')
        if args.get('freshness') not in (None,'pd','pw','pm','py'):raise ValueError('invalid_search_freshness')
        domains=args.get('domains',[])
        if not isinstance(domains,list) or len(domains)>5 or any(not isinstance(d,str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}\.)+[A-Za-z]{2,63}',d) for d in domains):raise ValueError('invalid_search_domains')
    elif adapter=='github':
        from live_self_healing import prepare as prepare_github
        return prepare_github(row,parameters,operation,args)
    else:raise ValueError('unsupported_adapter')
    return {'adapter':adapter,'operation':operation,'args':args,'method':None,'path':None,'body':None,
            'target':target,'guard':digest({'parameters':parameters,'target':target,'policy':digest(binding(row))}),
            'scope':'current_authenticated_company_and_user',
            'approvalReason':'Confira a skill/capacidade ou a edição textual vinculada, incluindo seu hash. Não autoriza scripts arbitrários.'}


def _material(row,artifact_id):
    from routes import live_experience as api
    from live_asset_reads import shared_sources
    from live_file_sources import _table,resolve_binding,FileSourceDenied
    if not isinstance(artifact_id,str) or not re.fullmatch(r'file:[a-f0-9]{32}',artifact_id):raise AdapterError('material_type_read_only')
    source=next((s for s in shared_sources(row)['items'] if s['artifactId']==artifact_id),None)
    if source is None:raise PermissionError()
    with api.live._store() as conn:
        _table(conn)
        bound=conn.execute('SELECT * FROM live_file_sources WHERE id=? AND user_id=? AND company_id=? AND active=1',(artifact_id[5:],row['user_id'],row['company_id'])).fetchone()
        if not bound:raise PermissionError()
        try:resolve_binding(conn,row,bound['id'],bound['sha256'],bound['revision'])
        except FileSourceDenied:raise PermissionError() from None
    return {k:bound[k] for k in ('id','path','sha256','revision')}


def execute_write(row,proposal,request_id):
    args=proposal['args']
    if proposal['adapter']=='materials':
        from routes import live_experience as api
        from live_workspace_actions import write_document
        from live_file_sources import _read
        target=_material(row,args['artifactId'])
        result=write_document(row,{'area':'materials','name':target['path'].removeprefix('workspace/'),
            'content':args['content'],'expectedSha256':args['expectedSha256']},request_id)
        verified=_read(target['path'])
        if verified['sha256']!=result['sha256']:raise AdapterError('material_update_uncertain',409)
        with api.live._store() as conn:
            conn.execute('BEGIN IMMEDIATE')
            changed=conn.execute('UPDATE live_file_sources SET sha256=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND company_id=? AND revision=? AND sha256=? AND active=1',
                (verified['sha256'],target['id'],row['user_id'],row['company_id'],target['revision'],target['sha256']))
            if changed.rowcount!=1:raise AdapterError('material_update_uncertain',409)
            conn.execute('''CREATE TABLE IF NOT EXISTS live_material_edits(
              id TEXT PRIMARY KEY,user_id INTEGER,company_id INTEGER,agent_name TEXT,source_id TEXT,
              previous_sha256 TEXT,new_sha256 TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('INSERT INTO live_material_edits(id,user_id,company_id,agent_name,source_id,previous_sha256,new_sha256) VALUES(?,?,?,?,?,?,?)',
                (request_id,row['user_id'],row['company_id'],row['agent_name'],target['id'],target['sha256'],verified['sha256']))
        return {**result,'artifactId':args['artifactId'],'revision':target['revision']+1,'historicalAuthorshipPreserved':True}
    if proposal['adapter']=='skills':
        from routes.live_experience import live
        from skill_capability_dispatch import dispatch_query,persist_receipt,fit_context_budget
        result=dispatch_query(args['input']['query'],root=live.WORKSPACE,row=row,read_files=live._query_files,
            verify_scope=lambda:live._owned(row['id']) is not None and live._guard() is None,binding_id=args['capability'])
        with live._store() as conn:persist_receipt(conn,row,result)
        return fit_context_budget({},result,max_chars=20000)
    from live_self_healing import submit
    return submit(row,proposal,request_id)


def execute_read(row,proposal):
    if proposal['adapter']=='internet':return search(proposal['args'])
    from live_self_healing import status
    return status(row,proposal['args']['jobId'])


def _public_url(value):
    try:
        url=urlsplit(value)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.port not in (None,443):return False
        host=url.hostname.lower()
        if host=='localhost' or host.endswith(('.localhost','.local','.internal','.lan')) or '.' not in host:return False
        try:return ipaddress.ip_address(host).is_global
        except ValueError:return True
    except (ValueError,TypeError):return False


def search(args):
    """Fixed provider API only. Result URLs are cited, never fetched with our cookies."""
    key=os.environ.get('BRAVE_SEARCH_API_KEY')
    if not key:raise AdapterError('web_search_not_configured')
    query=args['query'];domains=args.get('domains',[])
    if domains:query+=' ('+' OR '.join('site:'+d for d in domains)+')'
    params={'q':query,'count':args.get('count',5),'safesearch':'strict','country':'BR','search_lang':'pt-br'}
    if args.get('freshness'):params['freshness']=args['freshness']
    try:
        response=requests.get('https://api.search.brave.com/res/v1/web/search',params=params,
            headers={'X-Subscription-Token':key,'Accept':'application/json'},timeout=(3,15),allow_redirects=False)
        if response.status_code!=200:raise AdapterError('web_search_provider_unavailable',503)
        data=response.json()
    except (requests.RequestException,ValueError) as exc:
        if isinstance(exc,AdapterError):raise
        raise AdapterError('web_search_provider_unavailable',503) from None
    from live_workspace_actions import _SECRET
    items=[]
    for item in (data.get('web') or {}).get('results',[])[:10]:
        url=item.get('url');title=str(item.get('title',''))[:250];description=str(item.get('description',''))[:1200]
        if not _public_url(url) or any(key in v or _SECRET.search(v) for v in (url,title,description)):continue
        if domains and not any(urlsplit(url).hostname==d or urlsplit(url).hostname.endswith('.'+d) for d in domains):continue
        items.append({'title':title,'url':url,'description':description})
    return {'provider':'brave','health':'verified_by_this_request','results':items,
            'queriedAt':datetime.now(timezone.utc).isoformat(),'kind':'untrusted_reference_data',
            'contentFetched':False,'internalCredentialsSentToResultSites':False}
