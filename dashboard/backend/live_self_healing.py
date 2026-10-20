"""Approved GitHub jobs and exact-evidence recovery; no local shell or force."""
import base64
import json
import re
import sqlite3
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
    try:
        data=json.loads(POLICY.read_text())
    except (OSError,ValueError):
        raise AdapterError('self_healing_policy_unavailable') from None
    if (not isinstance(data,dict) or data.get('version')!=1
            or not isinstance(data.get('rollout'),dict)
            or not isinstance(data.get('ciWorkflows'),list)):
        raise AdapterError('self_healing_policy_unavailable')
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
    if operation not in ('status','commit','ci','rollout'):raise ValueError('invalid_pipeline_operation')
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
    columns={r[1] for r in conn.execute('PRAGMA table_info(live_pipeline_jobs)')}
    for name,kind in (('checkpoint','TEXT'),('updated_at','REAL')):
        if name not in columns:
            try:conn.execute('ALTER TABLE live_pipeline_jobs ADD COLUMN '+name+' '+kind)
            except sqlite3.OperationalError as exc:
                if 'duplicate column name' not in str(exc):raise


def diagnostics(row):
    """Describe application gates, never infer authority from a token or YOLO."""
    try:
        policy=_policy()
        available=True
    except AdapterError:
        policy={}
        available=False
    return {
        'policyAvailable':available,
        'mutationsRequireHumanApproval':True,
        'commitAgentEligible':row['agent_name'] in ('bolt-executor','hawk-debugger'),
        'protectedBranchesAllowed':False,
        'automaticReplayAllowed':False,
        'recoveryMode':'observe_exact_remote_evidence_only',
        'rolloutPolicyEnabled':policy.get('rollout',{}).get('enabled') is True,
        'credentialPermissionsVerified':False,
        'ciRevisionGuarantee':'checked_before_dispatch_and_on_observation_not_atomic',
        'activationRequires':'separate_operator_approval_and_runtime_validation',
    }


def _execution_scope(row,proposal):
    """Revalidate the approved scope before every outbound worker operation."""
    from live_adapters import digest,POLICY as ACCESS
    scope=_principal(row)
    _path(scope,'repos/'+proposal['args']['repository'])
    proof=proposal['target']
    if (digest(_policy())!=proof.get('policy')
            or digest(json.loads(ACCESS.read_text()))!=proof.get('access')
            or digest(scope)!=proof.get('githubAccess')):
        raise AdapterError('approval_target_changed',409)
    return scope


def _save_checkpoint(ident,checkpoint):
    from routes.live_experience import live
    from live_approval_policy import cipher
    encrypted='enc:'+cipher().encrypt(json.dumps(checkpoint).encode()).decode()
    with live._store() as conn:
        changed=conn.execute(
            "UPDATE live_pipeline_jobs SET checkpoint=?,updated_at=? WHERE id=? AND status='running'",
            (encrypted,time.time(),ident)).rowcount
    if changed!=1:raise AdapterError('pipeline_job_not_running',409)


def submit(row,proposal,request_id):
    from routes.live_experience import live
    from live_approval_policy import cipher,unpack
    ident=uuid.uuid4().hex
    with live._store() as conn:
        ensure(conn);conn.execute('BEGIN IMMEDIATE')
        prior=conn.execute('SELECT * FROM live_pipeline_jobs WHERE user_id=? AND company_id=? AND request_id=?',(row['user_id'],row['company_id'],request_id)).fetchone()
        if prior:
            if (prior['agent_name']!=row['agent_name'] or prior['operation']!=proposal['operation']
                    or json.loads(unpack(prior['parameters']))!=proposal):
                raise ValueError('idempotency_conflict')
            return {'jobId':prior['id'],'status':prior['status'],'replayed':True}
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
            # Do not allow the thread's caller to substitute the persisted owner.
            if any(job[key]!=row.get(key) for key in ('user_id','company_id','agent_name')):return
            row={key:job[key] for key in ('user_id','company_id','agent_name')}
            conn.execute("UPDATE live_pipeline_jobs SET status='running',updated_at=? WHERE id=?",(time.time(),ident))
        state='uncertain';result={'error':'pipeline_result_uncertain'}
        progress={}
        def checkpoint(value):
            _save_checkpoint(ident,value)
            progress.update(value)
        try:
            proposal=json.loads(unpack(job['parameters']));_principal(row)
            result=perform(row,proposal,ident,checkpoint=checkpoint)
            state='success' if proposal['operation']=='commit' else 'dispatched'
        except PermissionError:
            state='uncertain' if progress else 'blocked'
            result={'error':'scope_denied'}
        except AdapterError as exc:result={'error':exc.code}
        except Exception:pass  # No exception text/provider body/credential reaches logs or results.
        # A concurrent status read may already have reconciled a completed run.
        # Never downgrade that terminal evidence to dispatched/uncertain.
        with live._store() as conn:conn.execute(
            "UPDATE live_pipeline_jobs SET status=?,result=?,updated_at=? WHERE id=? AND status='running'",
            (state,json.dumps(result),time.time(),ident))


def perform(row,proposal,job_id,checkpoint=None):
    args=proposal['args'];repository=args['repository'];branch=args['branch'];head=args['headSha'];prefix='repos/'+repository
    parameters={'adapter':'github','operation':proposal['operation'],'argumentsJson':json.dumps(args)}
    # Approval and execution happen in different requests/threads. Re-run all
    # branch, agent, file, workflow and policy checks, not just user liveness.
    fresh=prepare(row,parameters,proposal['operation'],args)
    if fresh['target']!=proposal['target']:raise AdapterError('approval_target_changed',409)
    def request(method,path,**kwargs):
        _execution_scope(row,proposal)
        return _request(method,prefix+path,**kwargs)[0]
    def current_head():
        result=(request('GET','/git/ref/heads/'+branch).get('object') or {}).get('sha')
        if not isinstance(result,str) or not SHA.fullmatch(result):raise AdapterError('github_invalid_revision')
        return result
    if proposal['operation']=='commit':
        commit=request('GET','/git/commits/'+head);tree=(commit.get('tree') or {}).get('sha')
        if not isinstance(tree,str) or not SHA.fullmatch(tree):raise AdapterError('github_invalid_revision')
        if proposal['target']['branchExists'] and current_head()!=head:raise AdapterError('github_diff_changed',409)
        tree_result=request('POST','/git/trees',body={'base_tree':tree,'tree':[
            {'path':f['path'],'mode':'100644','type':'blob','content':f['content']} for f in args['files']]})
        sha=tree_result.get('sha')
        if not isinstance(sha,str) or not SHA.fullmatch(sha):raise AdapterError('github_invalid_revision')
        new_commit=request('POST','/git/commits',body={'message':args['message'],'tree':sha,'parents':[head]})
        sha=new_commit.get('sha')
        if not isinstance(sha,str) or not SHA.fullmatch(sha):raise AdapterError('github_invalid_revision')
        # Persist the exact candidate before updating a visible ref. If the
        # response is lost later, status can observe this SHA without replaying.
        if checkpoint:checkpoint({'stage':'commit_created','sha':sha})
        if proposal['target']['branchExists']:
            if current_head()!=head:raise AdapterError('github_diff_changed',409)
            request('PATCH','/git/refs/heads/'+branch,body={'sha':sha,'force':False})
        else:request('POST','/git/refs',body={'ref':'refs/heads/'+branch,'sha':sha})
        if current_head()!=sha:raise AdapterError('pipeline_result_uncertain')
        return {'sha':sha,'branch':branch,'url':f'https://github.com/{repository}/commit/{sha}','forcePush':False,'deleted':False}
    if current_head()!=head:raise AdapterError('github_diff_changed',409)
    if proposal['operation']=='ci':name=args['workflow'];inputs={'live_request_id':job_id}
    else:
        # Re-evaluate CI and the protected environment at execution, too.
        parameters={'adapter':'github','operation':'rollout','argumentsJson':json.dumps(args)}
        fresh=prepare(row,parameters,'rollout',args)
        if fresh['target']!=proposal['target']:raise AdapterError('approval_target_changed',409)
        name=_policy()['rollout']['workflow'];inputs={'live_request_id':job_id,'expected_sha':head,
            'image':args['image'],'previous_image':args['previousImage'],
            'ci_run_id':str(args['ciRunId']),'build_run_id':str(args['buildRunId'])}
    if _workflow(repository,branch,name)!=proposal['target']['workflowSha256']:
        raise AdapterError('approval_target_changed',409)
    if checkpoint:checkpoint({'stage':'dispatch_intent','workflow':name})
    result=request('POST','/actions/workflows/'+name+'/dispatches',body={'ref':branch,'inputs':inputs})
    run_id=result.get('workflow_run_id')
    if checkpoint and type(run_id) is int and run_id>0:
        checkpoint({'stage':'dispatch_intent','workflow':name,'runId':run_id})
    return {'headSha':head,'workflow':name,'requestId':job_id,'runId':result.get('workflow_run_id'),
            'url':f'https://github.com/{repository}/actions','dispatched':True,'executionComplete':False}


def status(row,ident):
    from routes.live_experience import live
    with live._store() as conn:
        ensure(conn);item=conn.execute('SELECT * FROM live_pipeline_jobs WHERE id=? AND user_id=? AND company_id=?',(ident,row['user_id'],row['company_id'])).fetchone()
    if not item:raise PermissionError()
    from live_approval_policy import unpack
    repository=json.loads(unpack(item['parameters']))['args']['repository']
    _path(_principal(row),'repos/'+repository)
    result=json.loads(item['result']) if item['result'] else None
    recovery='not_needed'
    if item['status'] in ('running','uncertain','dispatched'):
        observed=_observe(row,item,result)
        if observed:
            state,result=observed
            with live._store() as conn:
                # Compare-and-set avoids racing a worker or another observer.
                conn.execute(
                    'UPDATE live_pipeline_jobs SET status=?,result=?,updated_at=? WHERE id=? AND status=?',
                    (state,json.dumps(result),time.time(),ident,item['status']))
                item=conn.execute('SELECT * FROM live_pipeline_jobs WHERE id=?',(ident,)).fetchone()
            result=json.loads(item['result']) if item['result'] else None
            recovery='exact_remote_evidence'
        else:
            recovery='inconclusive_no_replay'
    elif item['status']=='pending':
        recovery='awaiting_worker_no_replay'
    return {'jobId':ident,'status':item['status'],'operation':item['operation'],'result':result,
            'recovery':{'mode':'observation_only','evidence':recovery,'automaticReplayAllowed':False},
            'message':'A consulta reconcilia somente evidência exata. Sem evidência, não repita a operação; revisão do operador é necessária.'}


def _observe(row,item,result):
    """Bounded read-only recovery, including lost responses and stopped workers.

    Absence of evidence is NEVER evidence that a mutation did not happen.
    Legacy jobs without the necessary checkpoint remain unresolved.
    """
    from live_approval_policy import unpack
    proposal=json.loads(unpack(item['parameters']))
    args=proposal['args'];repository=args['repository'];branch=args['branch']
    checkpoint=json.loads(unpack(item['checkpoint'])) if item['checkpoint'] else {}

    def read(path,**kwargs):
        scope=_principal(row)
        _path(scope,'repos/'+repository)  # Also recheck the repository allowlist.
        return _request('GET','repos/'+repository+path,**kwargs)

    if item['operation']=='commit':
        expected=checkpoint.get('sha')
        if checkpoint.get('stage')!='commit_created' or not isinstance(expected,str) or not SHA.fullmatch(expected):
            return None
        value,_=read('/git/ref/heads/'+branch)
        if (value.get('object') or {}).get('sha')!=expected:return None
        return 'success',{'sha':expected,'branch':branch,
            'url':f'https://github.com/{repository}/commit/{expected}',
            'forcePush':False,'deleted':False,'reconciled':True}

    # Old dispatched CI jobs have the workflow in their immutable arguments.
    # Rollouts need the persisted workflow name, not today's mutable policy.
    name=args.get('workflow') if item['operation']=='ci' else checkpoint.get('workflow')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.ya?ml',name):return None
    if item['status']!='dispatched' and checkpoint.get('stage')!='dispatch_intent':return None

    def matches(run):
        return (isinstance(run,dict) and type(run.get('id')) is int and run['id']>0
                and run.get('display_title')=='Live '+item['id']
                and run.get('head_sha')==args['headSha']
                and run.get('head_branch')==branch
                and run.get('event')=='workflow_dispatch'
                and run.get('path')=='.github/workflows/'+name
                and (run.get('head_repository') or {}).get('full_name','').casefold()==repository.casefold())

    run_id=(result or {}).get('runId') or checkpoint.get('runId')
    # Run lists do not expose rollout inputs (image/previousImage/CI IDs).
    # A matching title cannot prove those consequential inputs. Require a run
    # ID returned by this dispatch; a 204/lost receipt remains manual review.
    if item['operation']=='rollout' and not (type(run_id) is int and run_id>0):return None
    if type(run_id) is int and run_id>0:
        run,_=read('/actions/runs/'+str(run_id))
        candidates=[run] if matches(run) and run['id']==run_id else []
    else:
        candidates=[]
        for page in range(1,4):
            runs,more=read('/actions/workflows/'+name+'/runs',
                params={'event':'workflow_dispatch','head_sha':args['headSha'],
                        'branch':branch,'per_page':50,'page':page})
            candidates.extend(run for run in runs.get('workflow_runs',[]) if matches(run))
            if len(candidates)>1:return None
            if not more:break
        else:
            return None  # Bounded scan exhausted; uniqueness is unproven.
    if len(candidates)!=1:return None
    run=candidates[0]
    # Do not turn an absent or unknown conclusion into success/failure.
    complete=run.get('status')=='completed'
    if complete and run.get('conclusion') not in (
            'success','failure','cancelled','timed_out','action_required',
            'neutral','skipped','stale','startup_failure'):return None
    state=('success' if run['conclusion']=='success' else 'failed') if complete else 'dispatched'
    return state,{'headSha':args['headSha'],'workflow':name,'requestId':item['id'],
        'runId':run['id'],'runStatus':run.get('status'),'conclusion':run.get('conclusion'),
        'url':f'https://github.com/{repository}/actions/runs/{run["id"]}',
        'dispatched':True,'executionComplete':complete,'reconciled':True}
