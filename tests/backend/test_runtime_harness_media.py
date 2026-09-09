import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'dashboard/backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import provider_fallback as pf
import telegram_provider_bot as bot

def test_opencode_registers_selected_provider_without_persisting_secret(monkeypatch,tmp_path):
    monkeypatch.setattr(pf.shutil,'which',lambda _: '/usr/bin/opencode')
    calls=[]
    monkeypatch.setattr(pf,'_invoke_cli_run',lambda *a,**k: calls.append((a,k)) or {'status':'success'})
    pf._invoke_cli('opencode','hello',37,5,provider_id='omnirouter',model='Britto-Core',cwd=tmp_path,
                   env_overrides={'OPENAI_BASE_URL':'http://gateway/v1','OPENAI_API_KEY':'secret-test-value'})
    args,kwargs=calls[0]
    assert 'omnirouter/Britto-Core' in args[0]
    assert '--auto' in args[0]
    config=json.loads(args[1]['OPENCODE_CONFIG_CONTENT'])
    assert config['provider']['omnirouter']['options']['apiKey']=='{env:OPENAI_API_KEY}'
    assert 'secret-test-value' not in args[1]['OPENCODE_CONFIG_CONTENT']
    assert config['agent']['build']['steps']==37

def test_explicit_openclaude_full_access_does_not_get_overridden(monkeypatch,tmp_path):
    monkeypatch.setenv('OPENCLAUDE_PERMISSION_MODE','fullAccess')
    monkeypatch.setattr(pf.shutil,'which',lambda _: '/usr/bin/openclaude')
    calls=[]
    monkeypatch.setattr(pf,'_invoke_cli_run',lambda *a,**k: calls.append(a) or {'status':'success'})
    pf._invoke_cli('openclaude','hello',3,5,cwd=tmp_path)
    assert '--dangerously-skip-permissions' not in calls[0][0]
    assert 'fullAccess' in calls[0][0]

def test_dashboard_sync_ignores_stale_telegram_pin(monkeypatch):
    monkeypatch.setenv('TELEGRAM_PROVIDER','old')
    assert bot._telegram_provider_override({'telegram_follow_dashboard':True,'telegram_provider':'old'}) is None

def test_vision_sends_pixels_and_explicit_nonstream(monkeypatch,tmp_path):
    p=tmp_path/'test.png';p.write_bytes(b'fake-image-for-contract')
    monkeypatch.setattr(bot,'_omniroute_media_credentials',lambda:('http://gateway/v1','test-key'))
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return b'{"choices":[{"message":{"content":"Image described"}}]}'
    def open_(req,**kwargs):
        data=json.loads(req.data)
        assert data['stream'] is False
        assert data['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
        return Response()
    monkeypatch.setattr(bot.urllib.request,'urlopen',open_)
    assert bot.describe_telegram_image(p)=='Image described'
