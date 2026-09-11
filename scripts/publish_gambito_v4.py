"""Run inside dashboard after copying approved-scope artifacts to /tmp/gambito-v4."""
import json
import os
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode

def api(path, data=None):
    req=urllib.request.Request('http://127.0.0.1:8080/api'+path,
        headers={'Authorization':'Bearer '+os.environ['DASHBOARD_API_TOKEN'],'Content-Type':'application/json'},
        data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req,timeout=30) as response: return json.load(response)

def publish(source, target):
    dest=Path('/workspace')/target
    backup=Path('/workspace/config/audits')/datetime.now(timezone.utc).strftime('gambito-v4-%Y%m%dT%H%M%S')
    if dest.exists():
        backup.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copy2(dest,backup/dest.name)
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix('.v4.tmp');shutil.copy2(source,temp);temp.replace(dest)
    try: share=api('/shares/by-path?'+urlencode({'path':target}))
    except urllib.error.HTTPError as error:
        if error.code!=404: raise
        share=api('/shares',{'path':target,'expires_in':None})
    print(json.dumps({'path':target,'share':share},ensure_ascii=False))

if __name__=='__main__':
    import sys
    mapping={'caderno-gambito-v4.html':'workspace/social/[C]caderno-gambito-v4.html',
      'linha-editorial-gambito-v4.html':'workspace/social/[C]linha-editorial-sistema-britto.html',
      'roteiros-gambito-v4.html':'workspace/social/[C]roteiros-reels-10-16-09.html',
      'auditoria47-gambito-v4.html':'workspace/reports/[C]instagram-growth-audit-individual-2026-09-03.html'}
    for name in sys.argv[1:]: publish(Path('/tmp/gambito-v4')/name,mapping[name])
