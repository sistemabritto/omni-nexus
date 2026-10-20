"""Per-heartbeat alert preferences; the existing notification transport owns delivery."""
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

DEFAULT={'enabled':True,'categories':['timeout','provider_exhausted','auth','unknown'],
         'cooldownSeconds':300,'quietStart':None,'quietEnd':None,'timezone':'America/Bahia'}


def validate(args):
    import re
    if set(args)-set(DEFAULT):raise ValueError('invalid_alert_fields')
    data={**DEFAULT,**args}
    if type(data['enabled']) is not bool or type(data['cooldownSeconds']) is not int or not 60<=data['cooldownSeconds']<=86400:raise ValueError('invalid_alert_preferences')
    if not isinstance(data['categories'],list) or len(data['categories'])>4 or any(c not in DEFAULT['categories'] for c in data['categories']):raise ValueError('invalid_alert_categories')
    for key in ('quietStart','quietEnd'):
        value=data[key]
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',value)):raise ValueError('invalid_quiet_hours')
    if bool(data['quietStart'])!=bool(data['quietEnd']) or data['quietStart'] and data['quietStart']==data['quietEnd']:raise ValueError('invalid_quiet_hours')
    if not isinstance(data['timezone'],str) or len(data['timezone'])>80:raise ValueError('invalid_alert_timezone')
    try:ZoneInfo(data['timezone'])
    except (ValueError,ZoneInfoNotFoundError):raise ValueError('invalid_alert_timezone') from None
    return data


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS live_heartbeat_alerts(
      heartbeat_id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,
      preferences TEXT NOT NULL,last_alert_at REAL NOT NULL DEFAULT 0)''')


def read(ident):
    from routes import live_experience as api
    with api.live._store() as conn:
        ensure(conn);item=conn.execute('SELECT preferences FROM live_heartbeat_alerts WHERE heartbeat_id=?',(ident,)).fetchone()
    return {'identifier':ident,'configured':bool(item),'preferences':json.loads(item[0]) if item else DEFAULT,
            'scope':'workspace_administration_global','transport':'existing_heartbeat_notification_channel'}


def save(row,args):
    from routes import live_experience as api
    ident=args['identifier'];preferences=validate({**read(ident)['preferences'],**{k:v for k,v in args.items() if k!='identifier'}})
    with api.live._store() as conn:
        ensure(conn)
        conn.execute('INSERT INTO live_heartbeat_alerts(heartbeat_id,user_id,company_id,preferences) VALUES(?,?,?,?) ON CONFLICT(heartbeat_id) DO UPDATE SET preferences=excluded.preferences,user_id=excluded.user_id,company_id=excluded.company_id',
            (ident,row['user_id'],row['company_id'],json.dumps(preferences)))
    return read(ident)


def reserve(ident,category,*,path=None,now=None):
    """Reserve before send: an uncertain transport must not cause notification storms.

    Unconfigured legacy heartbeats retain their existing behavior. An explicitly
    configured preference fails closed on malformed data or unavailable storage.
    """
    path=Path(path or Path(__file__).resolve().parents[2]/'dashboard/data/nexus-live-context.sqlite3')
    if not path.is_file():return True
    now=time.time() if now is None else now
    try:
        with sqlite3.connect(path,timeout=5) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='live_heartbeat_alerts'").fetchone():return True
            conn.execute('BEGIN IMMEDIATE')
            item=conn.execute('SELECT preferences,last_alert_at FROM live_heartbeat_alerts WHERE heartbeat_id=?',(ident,)).fetchone()
            if not item:return True
            data=validate(json.loads(item[0]))
            if not data['enabled'] or category not in data['categories'] or now-item[1]<data['cooldownSeconds']:return False
            if data['quietStart']:
                clock=datetime.fromtimestamp(now,ZoneInfo(data['timezone'])).strftime('%H:%M')
                start,end=data['quietStart'],data['quietEnd']
                if (start<=clock<end if start<end else clock>=start or clock<end):return False
            conn.execute('UPDATE live_heartbeat_alerts SET last_alert_at=? WHERE heartbeat_id=?',(now,ident))
            return True
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError):return False
