#!/usr/bin/env python3
"""Fixed read-only aggregate queries on the VPS; no raw contacts/messages."""
import json,subprocess

def output(*args):return subprocess.check_output(args,text=True,timeout=60)
def container(service):
    ids=output('docker','ps','--filter','label=com.docker.swarm.service.name='+service,'--format','{{.ID}}').splitlines()
    if len(ids)!=1:raise RuntimeError('Expected one running '+service)
    return ids[0]

def collect(start,end):
    result={}
    try:
        cid=container('plausible_plausible_events_db')
        a=int(start.timestamp());b=int(end.timestamp())
        query=f"SELECT hostname, name, pathname, referrer_source, count() AS events, uniqExact(session_id) AS sessions FROM plausible_events_db.events_v2 WHERE timestamp >= toDateTime({a}) AND timestamp < toDateTime({b}) GROUP BY hostname,name,pathname,referrer_source ORDER BY events DESC LIMIT 200 FORMAT JSON"
        data=json.loads(output('docker','exec',cid,'clickhouse-client','--readonly','1','--max_execution_time','20','--query',query))
        result['clickhouse']={'status':'ok','data':data['data']}
    except Exception as exc:result['clickhouse']={'status':'unavailable','error':type(exc).__name__}
    try:
        cid=container('pgvector_pgvector')
        a=start.isoformat();b=end.isoformat()
        queries={
          'pipelines':f"select p.name pipeline,s.name stage,s.stage_type,count(*) items,count(*) filter(where i.created_at >= '{a}' and i.created_at < '{b}') new_in_window,count(*) filter(where i.updated_at < now()-interval '7 days') stale_7d from public.pipeline_items i join public.pipelines p on p.id=i.pipeline_id left join public.pipeline_stages s on s.id=i.pipeline_stage_id group by 1,2,3 order by 1,2",
          'contacts':f"select count(*) new_contacts,count(*) filter(where nullif(phone_number,'') is not null) with_phone from public.contacts where created_at >= '{a}' and created_at < '{b}'",
          'conversations':f"select status,count(*) conversations,count(*) filter(where first_reply_created_at is not null) with_first_reply from public.conversations where created_at >= '{a}' and created_at < '{b}' group by 1",
          'messages':f"select message_type,sender_type,status,count(*) messages from public.messages where created_at >= '{a}' and created_at < '{b}' group by 1,2,3",
          'tasks':"select status,count(*) tasks,count(*) filter(where due_date<now() and completed_at is null) overdue from public.pipeline_tasks group by 1",
        }
        data={}
        for name,query in queries.items():
            sql="BEGIN READ ONLY; SET LOCAL statement_timeout='20s'; SELECT coalesce(json_agg(q),'[]'::json) FROM ("+query+") q; COMMIT;"
            raw=output('docker','exec',cid,'psql','-U','postgres','-d','evocrm','-Atq','-v','ON_ERROR_STOP=1','-c',sql)
            data[name]=json.loads(raw)
        result['crm']={'status':'ok','data':data}
    except Exception as exc:result['crm']={'status':'unavailable','error':type(exc).__name__}
    return result
