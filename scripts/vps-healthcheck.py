#!/usr/bin/env python3
"""Host checks and bounded recovery of a stranded central gateway task."""
import json,os,shutil,subprocess,time
from pathlib import Path

STATE=Path('/var/lib/vps-maintenance/health.json')
def output(*cmd):return subprocess.check_output(cmd,text=True,timeout=20)
def main():
    STATE.parent.mkdir(mode=0o750,exist_ok=True)
    previous=json.loads(STATE.read_text()) if STATE.exists() else {}
    disk=shutil.disk_usage('/')
    memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    now=time.time()
    report={'time':now,'disk_free_gib':round(disk.free/2**30,1),'disk_used_percent':round(disk.used/disk.total*100,1),
            'memory_available_gib':round(memory['MemAvailable']/2**20,1),'load':os.getloadavg(),'services':{},'warnings':[]}
    for name in ['evonexus_omniroute','evonexus_redis','hermes_hermes','evonexus_evonexus_telegram']:
        spec=json.loads(output('docker','service','inspect',name))[0]
        desired=spec.get('Spec',{}).get('Mode',{}).get('Replicated',{}).get('Replicas',0)
        tasks=output('docker','service','ps','--filter','desired-state=running','--format','{{.CurrentState}}',name).splitlines()
        report['services'][name]={'desired':desired,'tasks':tasks}
        if desired and not any(t.startswith('Running') for t in tasks):report['warnings'].append(name+' has no running task')
        if name=='evonexus_omniroute':
            # Do not interfere with a starting task, an upstream outage, or a deliberate scale-down.
            stranded=desired>0 and not tasks
            count=previous.get('stranded_checks',0)+1 if stranded else 0
            report['stranded_checks']=count
            report['last_recovery']=previous.get('last_recovery',0)
            if count>=3 and now-report['last_recovery']>1800:
                output('docker','service','update','--detach','--force',name)
                report['last_recovery']=now
                report['warnings'].append('Recovered stranded OmniRoute service')
    if report['disk_used_percent']>=85:report['warnings'].append('Disk usage >=85%')
    if memory['MemAvailable']<1048576:report['warnings'].append('Available RAM <1 GiB')
    tmp=STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(report,indent=2)+'\n')
    tmp.replace(STATE)
    print(json.dumps(report))
if __name__=='__main__':main()
