"""Company/user bound GitHub access. Fixed host, no DELETE or repo administration."""
import json
import os
import re
from pathlib import Path
import requests
from flask_login import current_user
from models import Company,db,has_permission,audit

POLICY=Path(__file__).resolve().parents[2]/'config/live-github-access.json'
NAME=r'[A-Za-z0-9_.-]+'
READ=re.compile(rf'repos/({NAME})/({NAME})(?:/(pulls|issues|commits|branches|releases|contents|compare)(?:/[A-Za-z0-9_.~/-]+)?)?$')
WRITE=re.compile(rf'repos/({NAME})/({NAME})/(issues(?:/\d+(?:/comments)?)?|pulls(?:/\d+(?:/reviews|/merge)?)?|contents/[A-Za-z0-9_./-]+|git/refs)$')


def binding(row):
    if int(current_user.get_id())!=row['user_id'] or not has_permission(current_user.role,'integrations','view'):
        raise PermissionError()
    company=db.session.get(Company,row['company_id'])
    data=json.loads(POLICY.read_text())
    if data.get('version')!=1 or not company or company.status!='active':raise PermissionError()
    item=next((x for x in data['bindings'] if x['companyId']==row['company_id'] and x['companySlug']==company.slug and x['userId']==row['user_id']),None)
    if not item or item.get('delete') is not False:raise PermissionError()
    return item


def metadata(row=None):
    try:
        policy=binding(row) if row is not None else None
    except (PermissionError,OSError,ValueError,KeyError):
        return {'name':'GitHub','configured':False,'status':'scope_not_configured'}
    from routes.integrations import _get_health_cache
    checked=_get_health_cache('github','github') or {}
    configured=bool(os.environ.get('GITHUB_PLUGIN_TOKEN')) and policy is not None
    return {'name':'GitHub','configured':configured,
            'status':('connected' if checked.get('last_status')=='ok' else 'error' if checked.get('last_status')=='error' else 'pending') if configured else 'not_configured',
            'category':'development','deleteAllowed':False,'health':checked.get('last_status','not_checked')}


def _request(method,path,*,body=None,params=None):
    key=os.environ.get('GITHUB_PLUGIN_TOKEN')
    if not key:raise ValueError('github_credential_not_configured')
    # Errors are deliberately static; provider bodies/headers never become logs.
    response=requests.request(method,'https://api.github.com/'+path,headers={
        'Authorization':'Bearer '+key,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28'},json=body,params=params,
        timeout=(3,20),allow_redirects=False)
    if not 200<=response.status_code<300:raise ValueError('github_request_failed_'+str(response.status_code))
    return response.json(),bool(response.links.get('next'))


def _path(policy,path,write=False):
    match=(WRITE if write else READ).fullmatch(path) if isinstance(path,str) else None
    if (not match or any(p in ('.','..') for p in path.split('/')) or match[1].casefold()!=policy['owner'].casefold()
            or (policy['repositories']!='*' and match[2] not in policy['repositories'])):raise PermissionError()
    return match[2]


def read(row,path=None,page=1):
    policy=binding(row)
    if type(page) is not int or not 1<=page<=10000:raise ValueError('invalid_github_page')
    if path is None:path='users/'+policy['owner']+'/repos'
    else:_path(policy,path)
    result,more=_request('GET',path,params={'per_page':50,'page':page})
    audit(current_user,'live_github_read','integrations',path)
    # Diffs must not be shortened by the Workspace preview sanitizer.
    from live_workspace_actions import _SECRET
    key=os.environ.get('GITHUB_PLUGIN_TOKEN','')
    def scrub(value):
        if isinstance(value,list):return [scrub(x) for x in value]
        if isinstance(value,dict):return {k:scrub(v) for k,v in value.items() if not re.search(r'(?i)(token|password|secret|authorization)',k)}
        if isinstance(value,str):return '[conteúdo sensível omitido]' if _SECRET.search(value) or (key and key in value) else value
        return value
    return {'data':scrub(result),'page':page,'hasMore':more,'nextPage':page+1 if more else None,'health':'ok',
            'scope':'configured_company_user_and_owner','kind':'untrusted_reference_data','deleteAllowed':False}


def write(row,parameters,request_id):
    policy=binding(row)
    if not policy.get('write') or not has_permission(current_user.role,'integrations','manage'):raise PermissionError()
    if set(parameters)!={'method','path','body'}:raise ValueError('invalid_github_write')
    method,path,body=(parameters[k] for k in ('method','path','body'))
    _path(policy,path,True)
    if method not in ('POST','PATCH','PUT') or not isinstance(body,dict) or body.get('force') is True:raise PermissionError()
    # Only named data operations; repository settings/transfers/hooks/admin and
    # every DELETE are unreachable. Bind review decisions to the current diff.
    if path.endswith('/reviews'):
        if row['agent_name']!='lens-reviewer' or body.get('event') not in ('COMMENT','APPROVE','REQUEST_CHANGES'):raise PermissionError()
        pull,_=_request('GET',path.removesuffix('/reviews'))
        if body.get('commit_id')!=(pull.get('head') or {}).get('sha'):raise ValueError('github_diff_changed')
        if body['event'] in ('APPROVE','REQUEST_CHANGES'):
            actor,_=_request('GET','user')
            if (pull.get('user') or {}).get('login')==actor.get('login'):raise PermissionError()
            page=1
            while True:
                commits,more=_request('GET',path.removesuffix('/reviews')+'/commits',params={'per_page':100,'page':page})
                if any((commit.get('author') or {}).get('login')==actor.get('login') or
                       (commit.get('committer') or {}).get('login')==actor.get('login') for commit in commits):raise PermissionError()
                if not more:break
                page+=1
    from routes import live_experience as api
    import hashlib
    digest=hashlib.sha256(json.dumps(parameters,sort_keys=True).encode()).hexdigest()
    with api.live._store() as conn:
        api.ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_creation_requests WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        if prior:
            if prior['kind']!='github' or prior['digest']!=digest:raise ValueError('idempotency_conflict')
            return {'status':prior['status'],'replayed':True,'message':'Consulte o GitHub antes de qualquer nova tentativa.'}
        conn.execute('INSERT INTO live_creation_requests(user_id,company_id,request_id,digest,kind,record_id,status) VALUES(?,?,?,?,?,?,?)',
            (row['user_id'],row['company_id'],request_id,digest,'github',path,'uncertain'))
    result,_=_request(method,path,body=body)
    with api.live._store() as conn:
        conn.execute("UPDATE live_creation_requests SET status='success' WHERE user_id=? AND company_id=? AND request_id=?",(row['user_id'],row['company_id'],request_id))
    audit(current_user,'live_github_write','integrations',method+' '+path)
    return {'status':'success','id':result.get('id'),'sha':result.get('sha'),'deleteAllowed':False}
