"""VPS-side reviewed executor. Fixed service/repository; image-only update.

Run only from the protected Live rollout workflow after human approval. No shell
command, service, credential or environment override can be supplied by an agent.
"""
import copy
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

SERVICE='evonexus_evonexus_dashboard'
IMAGE=re.compile(r'^excarplex/evo-nexus-dashboard@sha256:[a-f0-9]{64}$')


def command(*args):
    result=subprocess.run(list(args),capture_output=True,text=True,timeout=240)
    if result.returncode:raise RuntimeError('executor_command_failed')
    return result.stdout


def inspect(*args):return json.loads(command('docker',*args))[0]


def rollout(image,revision,previous):
    if not IMAGE.fullmatch(image) or not IMAGE.fullmatch(previous) or not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('invalid_rollout_target')
    before=inspect('service','inspect',SERVICE)
    if before['Spec']['TaskTemplate']['ContainerSpec']['Image']!=previous:raise RuntimeError('production_image_changed')
    command('docker','pull',image)
    if inspect('image','inspect',image).get('Config',{}).get('Labels',{}).get('org.opencontainers.image.revision')!=revision:raise RuntimeError('image_revision_mismatch')
    containers=command('docker','ps','--filter','label=com.docker.swarm.service.name='+SERVICE,'--format','{{.ID}}').split()
    if len(containers)!=1:raise RuntimeError('production_container_count_changed')
    container=containers[0]
    # Refuse to terminate a real voice conversation or running implementation.
    check=r'''
import json,os,sqlite3
from pathlib import Path
import requests
from dotenv import load_dotenv
load_dotenv('/workspace/config/.env')
env=dict(os.environ)
for p in Path('/proc').glob('[0-9]*'):
    try:
        if b'/workspace/dashboard/backend/app.py' in (p/'cmdline').read_bytes().split(b'\0'):
            env.update(dict(x.decode().split('=',1) for x in (p/'environ').read_bytes().split(b'\0') if b'=' in x));break
    except OSError:pass
r=requests.get('https://api.elevenlabs.io/v1/convai/conversations',headers={'xi-api-key':env['ELEVENLABS_API_KEY']},params={'agent_id':env['NEXUS_LIVE_AGENT_ID'],'page_size':100},timeout=(3,15),allow_redirects=False)
assert r.status_code==200 and all(x.get('status') in ('done','failed') for x in r.json().get('conversations',[]))
c=sqlite3.connect('file:/workspace/dashboard/data/evonexus.db?mode=ro',uri=True)
assert c.execute("SELECT count(*) FROM orchestration_jobs WHERE status IN ('running','live_pending')").fetchone()[0]==0
print('PRODUCTION_IDLE')
'''
    if command('docker','exec',container,'/workspace/.venv/bin/python','-c',check).strip()!='PRODUCTION_IDLE':raise RuntimeError('production_not_idle')
    root=Path('/opt/evonexus-backups')/('live-approved-'+uuid.uuid4().hex)
    root.mkdir(mode=0o700,parents=True)
    snapshot=root/'service.json';snapshot.write_text(json.dumps(before));snapshot.chmod(0o600)
    command('docker','cp',container+':/workspace/config',str(root/'config'))
    for path in (root/'config').rglob('*'):
        if path.is_file():path.chmod(0o600)
        elif path.is_dir():path.chmod(0o700)
    backup_code=r'''
import os,sqlite3,uuid
from pathlib import Path
root=Path('/workspace/backups/live-approved')/uuid.uuid4().hex;root.mkdir(mode=0o700,parents=True)
for name in ('evonexus.db','nexus-live-context.sqlite3','live-continuity.sqlite3'):
    source=Path('/workspace/dashboard/data')/name
    if not source.exists():continue
    destination=root/name
    with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as src,sqlite3.connect(destination) as dst:src.backup(dst)
    destination.chmod(0o600)
print('DATABASE_BACKUP_READY')
'''
    if command('docker','exec',container,'/workspace/.venv/bin/python','-c',backup_code).strip()!='DATABASE_BACKUP_READY':raise RuntimeError('backup_failed')
    if inspect('service','inspect',SERVICE)['Spec']!=before['Spec']:raise RuntimeError('production_configuration_changed')
    command('docker','service','update','--detach=true','--image',image,SERVICE)
    after=inspect('service','inspect',SERVICE)
    expected=copy.deepcopy(before['Spec']);actual=copy.deepcopy(after['Spec'])
    expected['TaskTemplate']['ContainerSpec'].pop('Image');actual['TaskTemplate']['ContainerSpec'].pop('Image')
    if expected!=actual:raise RuntimeError('unexpected_service_change')
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        ids=command('docker','ps','--filter','label=com.docker.swarm.service.name='+SERVICE,'--format','{{.ID}}').split()
        if len(ids)==1:
            state=inspect('inspect',ids[0])
            if state.get('State',{}).get('Health',{}).get('Status')=='healthy':
                labels=state.get('Config',{}).get('Labels',{})
                if labels.get('org.opencontainers.image.revision')==revision:
                    record={'status':'healthy','revision':revision,'image':image,'onlyImageChanged':True}
                    (root/'result.json').write_text(json.dumps(record));return record
        time.sleep(3)
    # The human-approved proposal names this exact prior image for recovery.
    current=inspect('service','inspect',SERVICE)
    if current['Spec']['TaskTemplate']['ContainerSpec']['Image']==image:
        command('docker','service','update','--detach=true','--image',previous,SERVICE)
    raise RuntimeError('rollout_health_failed_previous_image_requested')


if __name__=='__main__':
    try:
        if len(sys.argv)!=4:raise ValueError('invalid_rollout_arguments')
        print(json.dumps(rollout(*sys.argv[1:])))
    except Exception:
        print('ROLLOUT_NOT_CONFIRMED; inspect the protected executor and reconcile before retrying.',file=sys.stderr)
        sys.exit(1)
