"""Actual controller/API/queue + exact CLI, synthetic localhost provider only."""
import json,pathlib,subprocess
from tests.backend.test_live_task_dispatch import tasks,enabled,setup
from tests.backend.test_live_task_dispatch import test_real_http_ui_dispatch_queue_and_result_in_chat as _existing_e2e

BASE=pathlib.Path('/tmp/live-harness-1.17.18')
CMD=['unshare','-Urn','bwrap','--unshare-pid','--unshare-ipc','--unshare-uts','--die-with-parent','--cap-add','CAP_NET_ADMIN','--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--symlink','usr/bin','/bin','--symlink','usr/sbin','/sbin','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/etc','--bind',str(BASE),'/work','--chdir','/work','--clearenv','--setenv','PATH','/usr/bin:/usr/sbin:/bin','/usr/bin/python3','/work/isolation-runtime.py','--single']

def test_exact_harness_live_http_queue_idempotence(tasks,tmp_path,monkeypatch):
    app,c,login,mod,service,calls,worker=tasks
    import provider_fallback
    def invoke(prompt,**kwargs):
        assert kwargs['tool_policy']=='no_tools' and kwargs['routing_key']=='agent-a'
        assert 'SECRET B' not in prompt
        (BASE/'input-prompt.txt').write_text(prompt)
        p=subprocess.run(CMD,text=True,capture_output=True,timeout=60)
        assert p.returncode==0,p.stderr
        proof=json.loads(p.stdout.strip().splitlines()[-1])
        assert proof['version']=='1.17.18'
        assert proof['binary_sha256']=='0cbfb6de55aa4ce3c74da12d8516376033693a88abca6238c5be32bf98130636'
        assert proof['network_interfaces']==['lo'] and not proof['external_route']
        assert all(not r.get('tools') for r in proof['requests']) and len(proof['requests'])>0
        assert all(r['status']=='success' and not r['plugin_mcp_canary_exists'] and not r['tool_canary_exists'] for r in proof['runs'])
        text=proof['output']
        assert text=='Rascunho interno fixture'
        calls.append((prompt,kwargs))
        return {'status':'success','output':text,'provider_id':'localhost-fixture','model':'fixture-model','cli_command':'opencode','attempt_number':1}
    monkeypatch.setattr(provider_fallback,'invoke_with_fallback',invoke)
    original_run=subprocess.run
    def isolated_run(command,*args,**kwargs):
        if len(command)>1 and command[0]=='node' and str(command[1]).endswith('task-http-tests.cjs'):
            command=[command[0],str(BASE/'task-http-exact-tests.cjs'),*command[2:]]
            kwargs['timeout']=60
        return original_run(command,*args,**kwargs)
    monkeypatch.setattr(subprocess,'run',isolated_run)
    _existing_e2e(tasks,tmp_path)
    proof=json.loads((BASE/'isolation-queue-proof.json').read_text())
    proof['same_sdk_action_replayed']=True
    proof['cli_invocations_for_same_action']=len(calls)
    proof['actual_ui_api_queue_worker_result_test']='passed'
    (BASE/'isolated-idempotence-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
