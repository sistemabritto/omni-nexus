"""Exact-revision GitHub jobs; no local shell, force, deletion or production secret."""
import base64
import json
import re
import threading
import time
import uuid
from pathlib import Path,PurePosixPath
from flask import current_app
from models import db,User,Company,has_permission,has_agent_access
from live_adapter_errors import AdapterError
from live_github import _path,_request

ROOT=Path(__file__).resolve().parents[2]
POLICY=ROOT/'config/live-self-healing.json'
SHA=re.compile(r'^[a-f0-9]{40}$')
IMAGE=re.compile(r'^excarplex/evo-nexus-dashboard@sha256:[a-f0-9]{64}$')
PROTECTED=('config/live-','config/providers','config/workspace','config/.env','.env',
           '.github/','dashboard/backend/live_adapter','dashboard/backend/live_self_healing',
           'dashboard/backend/live_approval_policy','scripts/ci/live_rollout','entrypoint.sh','Dockerfile')


def _policy():
    data=json.loads(POLICY.read_text())
    if data.get('version')!=1:raise AdapterError('self_healing_policy_unavailable')
    return data


def _principal(row):
    # A background worker revalidates the real stored principal, not a fabricated
    # browser cookie or a service-account replacement for a user request.
    from live_adapters import POLICY as ACCESS
    db.session.expire_all()
    data=json.loads(ACCESS.read_text());user=db.session.get(User,row['user_id']);company=db.session.get(Company,row['company_id'])
    grant=next((x for x in data.get('bindings',[]) if x.get('userId')==row['user_id'] and x.get('companyId')==row['company_id'] and x.get('workspaceAdministration') is True and x.get('companySlug',getattr(company,'slug',None))==getattr(company,'slug',None)),None)
    if data.get('version')!=1 or not grant or not user or not user.is_active or user.role!='admin' or not company or company.status!='active' or not has_permission(user.role,'integrations','manage') or not has_agent_access(user.role,row['agent_name']):raise PermissionError()
    from operational_squad import load_operational_squad
    if not load_operational_squad().get(row['agent_name'],{}).get('active'):raise PermissionError()
    from live_github import POLICY as GITHUB_POLICY
    scopes=json.loads(GITHUB_POLICY.read_text())
    scope=next((x for x in scopes.get('bindings',[]) if x.get('userId')==user.id and x.get('companyId')==company.id and x.get('companySlug')==company.slug),None)
    if scopes.get('version')!=1 or not scope or scope.get('write') is not True or scope.get('delete') is not False:raise PermissionError()
    return scope


def _head(repository,branch):
    value,_=_request('GET','repos/'+repository+'/git/ref/heads/'+branch)
    result=(value.get('object') or {}).get('sha')
    if not isinstance(result,str) or not SHA.fullmatch(result):raise AdapterError('github_invalid_revision')
    return result


def _workflow(repository,branch,name):
    return _verified_file(repository,branch,'.github/workflows/'+name)


def _verified_file(repository,branch,path):
    value,_=_request('GET','repos/'+repository+'/contents/'+path,params={'ref':branch})
    import hashlib
    try:raw=base64.b64decode(value['content'],validate=False)
    except (KeyError,ValueError,TypeError):raise AdapterError('pipeline_workflow_not_verified') from None
    local=ROOT/path
    if not local.is_file() or raw!=local.read_bytes():raise AdapterError('pipeline_workflow_not_verified')
    return hashlib.sha256(raw).hexdigest()


def prepare(row,parameters,operation,args):
    from live_adapters import fields,digest,POLICY as ACCESS
    if operation=='status':
        fields(args,{'jobId'})
        if not isinstance(args['jobId'],str) or not re.fullmatch('[a-f0-9]{32}',args['jobId']):raise ValueError('invalid_job_id')
        return {'adapter':'github','operation':operation,'args':args,'guard':digest(args),'method':None,
                'scope':'current_authenticated_company_and_user','approvalReason':''}
    required={'repository','branch','headSha'}
    fields(args,required|({'message','files'} if operation=='commit' else {'image','previousImage','ciRunId','buildRunId'} if operation=='rollout' else {'workflow'}),{'createBranch'} if operation=='commit' else ())
    scope=_principal(row);repository=args['repository'];branch=args['branch'];head=args['headSha']
    if not isinstance(repository,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('invalid_repository')
    _path(scope,'repos/'+repository)
    if not isinstance(branch,str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*',branch) or '..' in branch or branch.endswith(('.lock','.')):raise ValueError('invalid_branch')
    if not isinstance(head,str) or not SHA.fullmatch(head):raise ValueError('invalid_revision')
    policy=_policy();proof={'headSha':head,'policy':digest(policy),'access':digest(json.loads(ACCESS.read_text())),'githubAccess':digest(scope)}
    if operation=='commit':
        if row['agent_name'] not in ('bolt-executor','hawk-debugger'):raise PermissionError()
        repo,_=_request('GET','repos/'+repository)
        if branch in ('main','master','develop',repo.get('default_branch')):raise PermissionError()
        if type(args.get('createBranch',False)) is not bool:raise ValueError('invalid_branch_creation')
        if not isinstance(args['message'],str) or not 1<=len(args['message'])<=500:raise ValueError('invalid_commit_message')
        files=args['files']
        if not isinstance(files,list) or not 1<=len(files)<=20:raise ValueError('invalid_commit_files')
        seen=set()
        for file in files:
            fields(file,{'path','content'})
            path=file['path'];content=file['content']
            if not isinstance(path,str) or len(path)>300 or '\\' in path or any(ord(c)<32 for c in path) or str(PurePosixPath(path))!=path or PurePosixPath(path).is_absolute() or any(p in ('.','..') or p.startswith('.') for p in PurePosixPath(path).parts) or path.startswith(PROTECTED):raise PermissionError()
            if path in seen or not isinstance(content,str) or not 1<=len(content.encode())<=100000 or '\x00' in content:raise ValueError('invalid_commit_file')
            seen.add(path)
        try:actual=_head(repository,branch);proof['branchExists']=True
        except AdapterError as exc:
            if exc.code!='github_resource_not_found' or not args.get('createBranch'):raise
            commit,_=_request('GET','repos/'+repository+'/git/commits/'+head)
            if commit.get('sha')!=head:raise AdapterError('github_invalid_revision')
            actual=head;proof['branchExists']=False
    else:
        actual=_head(repository,branch)
        name=args.get('workflow') if operation=='ci' else policy.get('rollout',{}).get('workflow')
        if operation=='ci' and name not in policy.get('ciWorkflows',[]):raise PermissionError()
        if operation=='rollout':
            rollout=policy.get('rollout',{})
            if rollout.get('enabled') is not True or rollout.get('repository')!=repository or rollout.get('environment')!='production':raise AdapterError('pipeline_rollout_not_configured')
            if not all(isinstance(args[k],str) and IMAGE.fullmatch(args[k]) for k in ('image','previousImage')):raise ValueError('invalid_rollout_image')
            for key,workflow in (('ciRunId','ci.yml'),('buildRunId','docker-publish-britto.yml')):
                if type(args[key]) is not int or args[key]<1:raise ValueError('invalid_ci_run')
                run,_=_request('GET',f'repos/{repository}/actions/runs/{args[key]}')
                if run.get('head_sha')!=head or run.get('conclusion')!='success' or run.get('status')!='completed' or run.get('path','').split('@')[0]!='.github/workflows/'+workflow:raise AdapterError('pipeline_ci_not_verified')
            environment,_=_request('GET','repos/'+repository+'/environments/production')
            if rollout.get('requireEnvironmentReview') is True and not any(rule.get('type')=='required_reviewers' and rule.get('reviewers') for rule in environment.get('protection_rules',[])):raise AdapterError('pipeline_production_review_not_configured')
        proof['workflowSha256']=_workflow(repository,branch,name)
        if operation=='rollout':proof['executorSha256']=_verified_file(repository,branch,'scripts/ci/live_rollout.py')
    if actual!=head:raise AdapterError('github_diff_changed',409)
    return {'adapter':'github','operation':operation,'args':args,'target':proof,'method':None,'path':None,'body':None,
            'guard':digest({'parameters':parameters,'proof':proof}),'scope':'current_authenticated_company_and_user',
            'approvalReason':'Confira repositório, branch, SHA e diff/CI. Produção exige imagem por digest, versão anterior e sua aprovação humana, mesmo com YOLO ligado.'}


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS live_pipeline_jobs(
       id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,agent_name TEXT NOT NULL,
       operation TEXT NOT NULL,request_id TEXT NOT NULL,parameters TEXT NOT NULL,status TEXT NOT NULL,
       result TEXT,created_at REAL NOT NULL,UNIQUE(user_id,company_id,request_id))''')


def submit(row,proposal,request_id):
    from routes.live_experience import live
    from live_approval_policy import cipher
    ident=uuid.uuid4().hex
    with live._store() as conn:
        ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT id,status FROM live_pipeline_jobs WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        if prior:return {'jobId':prior['id'],'status':prior['status'],'replayed':True}
        conn.execute('INSERT INTO live_pipeline_jobs(id,user_id,company_id,agent_name,operation,request_id,parameters,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
            (ident,row['user_id'],row['company_id'],row['agent_name'],proposal['operation'],request_id,'enc:'+cipher().encrypt(json.dumps(proposal).encode()).decode(),'pending',time.time()))
    app=current_app._get_current_object()
    threading.Thread(target=run_job,args=(app,dict(row),ident),daemon=True).start()
    return {'jobId':ident,'status':'pending','message':'Job registrado; consulte github/status. Isso ainda não confirma commit, CI ou rollout.'}


def run_job(app,row,ident):
    with app.app_context():
        from routes.live_experience import live
        from live_approval_policy import unpack
        with live._store() as conn:
            ensure(conn);conn.execute('BEGIN IMMEDIATE')
            job=conn.execute("SELECT * FROM live_pipeline_jobs WHERE id=? AND status='pending'",(ident,)).fetchone()
            if not job:return
            conn.execute("UPDATE live_pipeline_jobs SET status='running' WHERE id=?",(ident,))
        state='uncertain';result={'error':'pipeline_result_uncertain'}
        try:
            proposal=json.loads(unpack(job['parameters']));_principal(row)
            result=perform(row,proposal,ident);state='success' if proposal['operation']=='commit' else 'dispatched'
        except PermissionError:state='blocked';result={'error':'scope_denied'}
        except AdapterError as exc:result={'error':exc.code}
        except Exception:pass  # No exception text/provider body/credential reaches logs or results.
        with live._store() as conn:conn.execute('UPDATE live_pipeline_jobs SET status=?,result=? WHERE id=?',(state,json.dumps(result),ident))


def perform(row,proposal,job_id):
    args=proposal['args'];repository=args['repository'];branch=args['branch'];head=args['headSha'];prefix='repos/'+repository
    def request(method,path,**kwargs):
        _principal(row)  # Revocation checked before each outbound operation.
        return _request(method,prefix+path,**kwargs)[0]
    if proposal['operation']=='commit':
        commit=request('GET','/git/commits/'+head);tree=(commit.get('tree') or {}).get('sha')
        if not isinstance(tree,str) or not SHA.fullmatch(tree):raise AdapterError('github_invalid_revision')
        if proposal['target']['branchExists'] and _head(repository,branch)!=head:raise AdapterError('github_diff_changed',409)
        tree_result=request('POST','/git/trees',body={'base_tree':tree,'tree':[
            {'path':f['path'],'mode':'100644','type':'blob','content':f['content']} for f in args['files']]})
        sha=tree_result.get('sha')
        if not isinstance(sha,str) or not SHA.fullmatch(sha):raise AdapterError('github_invalid_revision')
        new_commit=request('POST','/git/commits',body={'message':args['message'],'tree':sha,'parents':[head]})
        sha=new_commit.get('sha')
        if not isinstance(sha,str) or not SHA.fullmatch(sha):raise AdapterError('github_invalid_revision')
        if proposal['target']['branchExists']:
            if _head(repository,branch)!=head:raise AdapterError('github_diff_changed',409)
            request('PATCH','/git/refs/heads/'+branch,body={'sha':sha,'force':False})
        else:request('POST','/git/refs',body={'ref':'refs/heads/'+branch,'sha':sha})
        if _head(repository,branch)!=sha:raise AdapterError('pipeline_result_uncertain')
        return {'sha':sha,'branch':branch,'url':f'https://github.com/{repository}/commit/{sha}','forcePush':False,'deleted':False}
    if _head(repository,branch)!=head:raise AdapterError('github_diff_changed',409)
    if proposal['operation']=='ci':name=args['workflow'];inputs={'live_request_id':job_id}
    else:
        # Re-evaluate CI and the protected environment at execution, too.
        parameters={'adapter':'github','operation':'rollout','argumentsJson':json.dumps(args)}
        fresh=prepare(row,parameters,'rollout',args)
        if fresh['target']!=proposal['target']:raise AdapterError('approval_target_changed',409)
        name=_policy()['rollout']['workflow'];inputs={'live_request_id':job_id,'expected_sha':head,
            'image':args['image'],'previous_image':args['previousImage'],
            'ci_run_id':str(args['ciRunId']),'build_run_id':str(args['buildRunId'])}
    _workflow(repository,branch,name)
    result=request('POST','/actions/workflows/'+name+'/dispatches',body={'ref':branch,'inputs':inputs})
    return {'headSha':head,'workflow':name,'requestId':job_id,'runId':result.get('workflow_run_id'),
            'url':f'https://github.com/{repository}/actions','dispatched':True,'executionComplete':False}


def status(row,ident):
    from routes.live_experience import live
    with live._store() as conn:
        ensure(conn);item=conn.execute('SELECT * FROM live_pipeline_jobs WHERE id=? AND user_id=? AND company_id=?',(ident,row['user_id'],row['company_id'])).fetchone()
    if not item:raise PermissionError()
    result=json.loads(item['result']) if item['result'] else None
    if item['status']=='dispatched':
        _principal(row)
        from live_approval_policy import unpack
        args=json.loads(unpack(item['parameters']))['args'];repository=args['repository']
        runs,_=_request('GET','repos/'+repository+'/actions/runs',params={'event':'workflow_dispatch','head_sha':args['headSha'],'per_page':50})
        matches=[r for r in runs.get('workflow_runs',[]) if r.get('display_title')=='Live '+ident and r.get('head_sha')==args['headSha']]
        if len(matches)==1:
            run=matches[0];result={**result,'runId':run['id'],'runStatus':run['status'],'conclusion':run.get('conclusion'),'url':run['html_url'],'executionComplete':run['status']=='completed'}
            if run['status']=='completed':
                state='success' if run.get('conclusion')=='success' else 'failed'
                with live._store() as conn:conn.execute('UPDATE live_pipeline_jobs SET status=?,result=? WHERE id=?',(state,json.dumps(result),ident))
                return {'jobId':ident,'status':state,'operation':item['operation'],'result':result}
    return {'jobId':ident,'status':item['status'],'operation':item['operation'],'result':result,
            'message':'Se o worker foi interrompido em running/uncertain, não repetir automaticamente; reconcilie o GitHub.'}
