"""Callback uses real Flask owned context and existing file ACL, no model."""
from pathlib import Path
import sqlite3
import os
import pytest
from tests.backend.test_live_file_sources import files, bind_file  # noqa:F401
from tests.backend.test_live_continuity_endpoints import enabled, bound, post  # noqa:F401
from tests.backend.test_managed_live_context import setup, ORIGIN  # noqa:F401
ROOT=Path(__file__).resolve().parents[2]

def call(c,ctx,**extra):
    return c.post('/api/live/omni-context/runtime-read',json={
        'runtimeSessionId':ctx['runtimeSessionId'],'agentName':'agent-a','query':'thumbnail',**extra},headers=ORIGIN)

def test_callback_derives_principal_from_cookie_and_owned_record(files,monkeypatch):
    fixture,_,save=files;app,c,login,mod,runtime,_=fixture
    monkeypatch.setattr(mod,'WORKSPACE',ROOT)
    path,_=save('brand.md','Marca identidade azul original')
    ctx=bound(c);runtime[ctx['runtimeSessionId']]['agentName']='agent-a';bind_file(c,ctx,path)
    r=call(c,ctx);assert r.status_code==200,r.json
    assert (r.json['userId'],r.json['companyId'])==(31,7)
    assert len(r.json['documents'])==5
    assert call(c,ctx).json==r.json
    payload={'runtimeSessionId':ctx['runtimeSessionId'],'agentName':'agent-a','query':'thumbnail'}
    assert c.post('/api/live/omni-context/runtime-read',json=payload).status_code==403
    assert c.post('/api/live/omni-context/runtime-read',json=payload,headers={'Origin':'https://foreign.test'}).status_code==403
    for injection in ({'companyId':8},{'files':['/etc/passwd']},{'workingDir':'/'},{'readContext':r.json}):
        assert call(c,ctx,**injection).status_code==400
    assert call(c,ctx,agentName='other').status_code==403
    assert call(c,ctx,runtimeSessionId='no-owned-context').status_code==403
    with sqlite3.connect(app.config['NEXUS_LIVE_CONTEXT_DB']) as conn:
        before_count=conn.execute('SELECT count(*) FROM contexts').fetchone()[0]
        conn.execute('UPDATE contexts SET conversation_id=NULL WHERE id=?',(ctx['contextId'],))
    assert call(c,ctx).status_code==403
    with sqlite3.connect(app.config['NEXUS_LIVE_CONTEXT_DB']) as conn:
        assert conn.execute('SELECT count(*) FROM contexts').fetchone()[0]==before_count
        conn.execute('UPDATE contexts SET conversation_id=? WHERE id=?',('provider-a',ctx['contextId']))
    payload={'runtimeSessionId':ctx['runtimeSessionId'],'agentName':'agent-a','query':'thumbnail'}
    assert c.post('/api/live/omni-context/runtime-read',json=payload,headers={**ORIGIN,'X-Fixture-Token':'yes'}).status_code==403
    other=bound(c,company=8,connection='other');runtime[other['runtimeSessionId']]['agentName']='agent-a'
    assert call(c,other).status_code==409 # company 7 binding not inherited
    login(32);assert call(c,ctx).status_code==403
    login(31)
    with sqlite3.connect(app.config['NEXUS_LIVE_CONTEXT_DB']) as conn:
        conn.execute('UPDATE contexts SET user_id=32 WHERE runtime_session_id=?',(ctx['runtimeSessionId'],))
    assert call(c,ctx).status_code==403

def test_callback_reloads_revocation_and_changed_source(files,monkeypatch):
    fixture,_,save=files;app,c,_,mod,runtime,_=fixture
    monkeypatch.setattr(mod,'WORKSPACE',ROOT)
    path,file=save('brand.md','Marca identidade original')
    ctx=bound(c);runtime[ctx['runtimeSessionId']]['agentName']='agent-a';binding=bind_file(c,ctx,path)
    before=call(c,ctx);assert before.status_code==200
    file.write_text('Marca identidade modificada')
    assert call(c,ctx).status_code==409
    file.write_text('Marca identidade original')
    post(c,ctx,'file-sources/revoke',id=binding['id'],expectedRevision=1)
    assert call(c,ctx).status_code==409


@pytest.mark.skipif(os.environ.get('OMNI_LOCAL_CHAT_BOOTSTRAP_PROOF') != '1',
                    reason='local CLI bootstrap proof requires explicit opt-in; pure callback/relay remains in CI')
@pytest.mark.parametrize('mode',['success','tenant','origin','path','revoke','snapshot','no_tools'])
def test_real_server_bootstrap_ws_callback_cli(files,monkeypatch,mode):
    """Actual WS server and HTTP Flask callback, never injected transport grant."""
    import os, subprocess, threading, json
    from werkzeug.serving import make_server
    fixture,_,save=files;app,c,login,mod,runtime,_=fixture
    monkeypatch.setattr(mod,'WORKSPACE',ROOT)
    path,file=save('brand.md','Marca identidade OWNED_BRAND_FIXTURE')
    ctx=bound(c);runtime[ctx['runtimeSessionId']]['agentName']='agent-a';bind_file(c,ctx,path)
    if mode=='tenant':login(32)
    cookie=c.get_cookie('session',domain='example.test').value
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    env={**os.environ,'FIXTURE_BACKEND':f'http://127.0.0.1:{server.server_port}/',
        'FIXTURE_SID':ctx['runtimeSessionId'],'FIXTURE_COOKIE':'session='+cookie,
        'FIXTURE_MODE':mode,'FIXTURE_SOURCE_PATH':str(file)}
    try:
        output=subprocess.run(['node',str(ROOT/'qa/capability-probe/server_owned_chat_e2e.cjs')],
            env=env,cwd=ROOT,capture_output=True,text=True,timeout=85)
        assert output.returncode==0,output.stdout+'\n'+output.stderr
        proof=json.loads(next(line.removeprefix('OWNED_SERVER_PROOF ') for line in output.stdout.splitlines() if line.startswith('OWNED_SERVER_PROOF ')))
        assert proof['mode']==mode
        if mode=='success':assert proof['nativeMarkerObserved'] is True
    finally:
        server.shutdown();thread.join(5)


def test_proxy_keeps_existing_cookie_and_real_origin_in_internal_handshake(enabled,monkeypatch):
    from routes.terminal_proxy import register_websocket_proxy
    from unittest.mock import Mock
    import types,sys
    app,c,_,_,_,_=enabled
    cookie='session='+c.get_cookie('session',domain='example.test').value
    calls=[]
    upstream=Mock();upstream.recv.return_value=b''
    monkeypatch.setitem(sys.modules,'websocket',types.SimpleNamespace(create_connection=lambda url,**kwargs:calls.append((url,kwargs)) or upstream))
    class Sock:
        def route(self,_path):
            def register(fn):self.handler=fn;return fn
            return register
    sock=Sock();register_websocket_proxy(sock)
    client=Mock();client.connected=False;client.receive.return_value=None
    with app.test_request_context('/terminal/ws',headers={'Cookie':cookie,**ORIGIN}):
        sock.handler(client)
    assert calls[0][1]['cookie']==cookie
    assert calls[0][1]['origin']==ORIGIN['Origin']
    upstream.settimeout.assert_called_once_with(None)


def test_proxy_idle_tick_preserves_binary_text_and_closes_after_disconnect(enabled,monkeypatch):
    """No sleeps: emulate receive timeout then bidirectional frames and close."""
    import queue, threading, types, sys
    from routes.terminal_proxy import register_websocket_proxy
    app,c,_,_,_,_=enabled
    forwarded=[];delivered=[];outgoing=queue.Queue();complete=threading.Event();timeouts=[]
    class Upstream:
        def settimeout(self,value):timeouts.append(value)
        def recv(self):return outgoing.get(timeout=5)
        def send(self,msg):forwarded.append(msg);outgoing.put(msg)
        def close(self):outgoing.put(b'')
    class Client:
        connected=True
        ticks=0
        def receive(self,timeout):
            self.ticks+=1
            if self.ticks==1:return None # idle but connected
            if self.ticks==2:return b'fixture-binary'
            if self.ticks==3:return 'fixture-text'
            assert complete.wait(5)
            self.connected=False;return None
        def send(self,msg):
            delivered.append(msg)
            if len(delivered)==2:complete.set()
        def close(self,**_):self.connected=False
    monkeypatch.setitem(sys.modules,'websocket',types.SimpleNamespace(create_connection=lambda *_args,**_kw:Upstream()))
    class Sock:
        def route(self,_):
            def register(fn):self.handler=fn;return fn
            return register
    sock=Sock();register_websocket_proxy(sock);client=Client()
    cookie='session='+c.get_cookie('session',domain='example.test').value
    with app.test_request_context('/terminal/ws',headers={'Cookie':cookie,**ORIGIN}):sock.handler(client)
    assert client.ticks==4 and client.connected is False
    assert forwarded==delivered==[b'fixture-binary','fixture-text']
    assert timeouts==[None]
