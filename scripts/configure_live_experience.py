"""Apply the reviewed client contract to the configured OmniNexus Live agent only.

Run inside the exact reviewed dashboard image after rollout. Existing process
credentials are used in memory; snapshots are restricted on the backup volume.
No synthesis/generation, voice, LLM, provider or workflow changes are requested.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import requests

BASE='https://api.elevenlabs.io/v1/convai'
EXPECTED_AGENT='agent_2801m4zs4r03e0qt3h3jcgj96tbv'


def apply(root,backup,confirm=False):
    # Inherit the running app's effective config without printing any values.
    env=dict(os.environ)
    for process in Path('/proc').glob('[0-9]*'):
        try:
            if b'/workspace/dashboard/backend/app.py' in (process/'cmdline').read_bytes().split(b'\0'):
                env.update({k.decode():v.decode() for k,v in (item.split(b'=',1) for item in (process/'environ').read_bytes().split(b'\0') if b'=' in item)});break
        except OSError:continue
    assert env.get('NEXUS_LIVE_AGENT_ID')==EXPECTED_AGENT,'Unexpected provider agent; stop'
    headers={'xi-api-key':env['ELEVENLABS_API_KEY']}
    def get(path):
        response=requests.get(BASE+path,headers=headers,timeout=(3,20),allow_redirects=False);response.raise_for_status();return response.json()
    before=get('/agents/'+EXPECTED_AGENT);inventory=get('/tools');assert not inventory.get('has_more'),'Paginate inventory before applying'
    desired=json.loads((root/'config/live-experience/client-tools.json').read_text())['tools']
    prompt=(root/'config/live-experience/agent-prompt.md').read_text()
    workflow=before.get('workflow') or {};assert all(node.get('type')=='start' for node in workflow.get('nodes',{}).values()),'Node-scoped workflow requires separate review'
    names={x['tool_config']['name']:x for x in inventory['tools']}
    assert len(names)==len(inventory['tools']),'Ambiguous tool names'
    changed=[]
    for config in desired:
        if config['name'] not in names:continue
        actual=names[config['name']]['tool_config']
        fields=('type','name','description','expects_response','execution_mode','response_timeout_secs')
        if (any(actual.get(k)!=config.get(k) for k in fields)
                or actual.get('parameters',{}).get('properties',{})!=config['parameters'].get('properties',{})
                or actual.get('parameters',{}).get('required',[])!=config['parameters'].get('required',[])):
            changed.append(config['name'])
    result={'agentId':EXPECTED_AGENT,'newTools':[x['name'] for x in desired if x['name'] not in names],
            'changedTools':changed,'promptSha256':hashlib.sha256(prompt.encode()).hexdigest(),'applied':False}
    if not confirm:return result
    assert not changed,'Existing schemas require a reviewed tool-version migration; no provider write performed: '+','.join(changed)
    backup.mkdir(mode=0o700,parents=True,exist_ok=False)
    def save(name,data):
        path=backup/name;path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    save('agent-before.json',before);save('tools-before.json',inventory)
    ids=list(before['conversation_config']['agent']['prompt'].get('tool_ids') or [])
    created=[]
    for config in desired:
        name=config['name']
        if name in names:
            tool=names[name];actual=tool['tool_config']
            for key in ('type','name','description','expects_response','execution_mode','response_timeout_secs'):
                assert actual.get(key)==config.get(key),'Existing tool differs: '+name+'; inspect before updating'
            params=actual.get('parameters',{});wanted=config['parameters']
            assert params.get('properties',{})==wanted.get('properties',{}) and params.get('required',[])==wanted.get('required',[]),'Existing tool schema differs: '+name
            identifier=tool['id']
        else:
            response=requests.post(BASE+'/tools',headers=headers,json={'tool_config':config},timeout=(3,20),allow_redirects=False)
            assert response.status_code in (200,201),'Tool creation rejected; inspect inventory before retry: '+str(response.status_code)
            identifier=response.json()['id'];created.append({'name':name,'id':identifier});save('created-tools.json',created)
        if identifier not in ids:ids.append(identifier)
    current=get('/agents/'+EXPECTED_AGENT)
    assert current['conversation_config']==before['conversation_config'] and current.get('workflow')==before.get('workflow'),'Agent changed concurrently; stop before patch'
    # One leaf per PATCH, re-read after each, preserving all non-target fields.
    for leaf,value in (('tool_ids',ids),('prompt',prompt)):
        response=requests.patch(BASE+'/agents/'+EXPECTED_AGENT,headers=headers,json={'conversation_config':{'agent':{'prompt':{leaf:value}}}},params={'version_description':'OmniNexus Live reviewed experience'},timeout=(3,20),allow_redirects=False)
        assert response.status_code==200,'Agent patch rejected: '+leaf+'; inspect current state'
        observed=get('/agents/'+EXPECTED_AGENT)
        assert observed['conversation_config']['agent']['prompt'][leaf]==value,'Provider did not persist '+leaf
        save('agent-after-'+leaf+'.json',observed)
    expected=copy.deepcopy(before['conversation_config']);actual=copy.deepcopy(observed['conversation_config'])
    for item in (expected,actual):
        for leaf in ('tool_ids','tools','prompt'):item['agent']['prompt'].pop(leaf,None)
    assert expected==actual and observed.get('workflow')==before.get('workflow') and observed.get('platform_settings')==before.get('platform_settings'),'Unexpected change outside prompt/tools'
    result.update(applied=True,toolCount=len(ids),createdTools=created,voiceModelAndPlatformPreserved=True,backup=str(backup),versionId=observed.get('version_id'))
    save('verification.json',result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path('/workspace'));parser.add_argument('--backup',type=Path,required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    print(json.dumps(apply(args.root,args.backup,args.apply),ensure_ascii=False))
