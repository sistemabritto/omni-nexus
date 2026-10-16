"""Opt-in offline proof: public binary/proxy deps copied read-only from image.

Run in user+net namespace with only lo up. No host install or real model.
"""
import os
from pathlib import Path
import pytest
from tests.backend.test_live_file_sources import files,bind_file  # noqa:F401
from tests.backend.test_live_continuity_endpoints import enabled,bound  # noqa:F401
from tests.backend.test_managed_live_context import setup  # noqa:F401
ROOT=Path(__file__).resolve().parents[2]
PIN='0cbfb6de55aa4ce3c74da12d8516376033693a88abca6238c5be32bf98130636'

@pytest.mark.skipif(not os.environ.get('OMNI_PINNED_PROXY_PROOF'),reason='requires read-only copied image runtime and isolated network namespace')
@pytest.mark.parametrize('mode',['success','tenant','origin','path','revoke','snapshot','no_tools'])
def test_pinned_binary_through_actual_flask_ws_proxy(files,monkeypatch,mode):
    import hashlib,json,subprocess,threading,urllib.request,socket
    assert [name for _,name in socket.if_nameindex()]==['lo'], 'proof requires dedicated loopback-only net namespace'
    assert len(Path('/proc/net/route').read_text().strip().splitlines())==1, 'proof requires no egress route'
    from types import SimpleNamespace
    from flask_sock import Sock
    from werkzeug.serving import make_server
    from routes import terminal_proxy
    import websocket
    binary=Path(os.environ['PROOF_BINARY'])
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==PIN
    assert websocket.__version__=='1.9.2'
    assert Path(websocket.__file__).resolve().is_relative_to(Path(os.environ['PROOF_PROXY_RUNTIME']).resolve())
    fixture,_,save=files;app,c,login,mod,_,_=fixture
    monkeypatch.setattr(mod,'WORKSPACE',ROOT)
    terminal_proxy.register_websocket_proxy(Sock(app))
    path,file=save('brand.md','Marca identidade OWNED_BRAND_FIXTURE')
    ctx=bound(c);bind_file(c,ctx,path)
    if mode=='tenant':login(32)
    cookie=c.get_cookie('session',domain='example.test').value
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    env={**os.environ,'FIXTURE_BACKEND':f'http://127.0.0.1:{server.server_port}/',
        'FIXTURE_SID':ctx['runtimeSessionId'],'FIXTURE_COOKIE':'session='+cookie,
        'FIXTURE_MODE':mode,'FIXTURE_SOURCE_PATH':str(file),
        'FIXTURE_PROXY':f'ws://127.0.0.1:{server.server_port}/terminal/ws','PROOF_BINARY_SHA256':PIN}
    process=subprocess.Popen(['node',str(ROOT/'qa/capability-probe/server_owned_chat_e2e.cjs')],env=env,cwd=ROOT,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        ready=process.stdout.readline()
        assert ready.startswith('OWNED_NODE_PORT '),ready+process.stderr.read()
        node_port=int(ready.split()[-1]);monkeypatch.setattr(terminal_proxy,'TERMINAL_WS_BASE',f'ws://127.0.0.1:{node_port}')
        # Actual Node GET handler verifies runtime id+agent, no fake HTTP adapter.
        def runtime_get(url,**kwargs):
            assert url.rsplit('/',1)[-1]==ctx['runtimeSessionId']
            with urllib.request.urlopen(f'http://127.0.0.1:{node_port}/api/sessions/'+ctx['runtimeSessionId'],timeout=5) as response:
                payload=json.load(response)
            return SimpleNamespace(json=lambda:payload,raise_for_status=lambda:None)
        monkeypatch.setattr(mod.requests,'get',runtime_get)
        out,err=process.communicate('ready\n',timeout=90)
        assert process.returncode==0,out+'\n'+err
        proof=json.loads(next(x.removeprefix('OWNED_SERVER_PROOF ') for x in out.splitlines() if x.startswith('OWNED_SERVER_PROOF ')))
        assert proof['realFlaskProxy'] is True and proof['binarySha256']==PIN
    finally:
        if process.poll() is None:process.kill();process.communicate()
        server.shutdown();thread.join(5)
