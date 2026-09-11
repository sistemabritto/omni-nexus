"""Scoped runtime check and restore of previously authorized editorial monitor."""
import json
import sys
sys.path.insert(0,'/tmp/gambito-v4')
from publish_gambito_v4 import api
sys.path.insert(0,'/workspace/dashboard/backend')
sys.path.insert(0,'/workspace')
import reels_producer

if __name__=='__main__':
    for hid in ['reels-producer','pixel-growth-6h','goal-planner']:
        try:
            hb=api('/heartbeats/'+hid)
            summary={k:hb.get(k) for k in ['id','enabled','handler']}
            last=hb.get('last_run') or {}
            summary['last_run']={k:last.get(k) for k in ['run_id','status','started_at','duration_seconds']} if isinstance(last,dict) else last
            print(json.dumps(summary,default=str))
        except Exception as error: print(hid,type(error).__name__)
    print('monitor_test',json.dumps(reels_producer.tick(),ensure_ascii=False))
    print('monitor_dedup',json.dumps(reels_producer.tick(),ensure_ascii=False))
    import urllib.request,os
    request=urllib.request.Request('http://127.0.0.1:8080/api/heartbeats/reels-producer',method='PATCH',data=b'{"enabled":true}',headers={'Authorization':'Bearer '+os.environ['DASHBOARD_API_TOKEN'],'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=30) as response:
        print('monitor_enabled',json.load(response).get('enabled'))
