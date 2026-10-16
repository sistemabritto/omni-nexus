"""Real Flask config endpoints -> disk -> Node loader/chat -> mocked transport."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest
from flask import Flask
from flask_login import LoginManager,UserMixin

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "dashboard/backend"))

@pytest.fixture
def configuration(tmp_path,monkeypatch):
    import routes.providers as routes
    data={'active_provider':'opencode','telegram_follow_dashboard':False,'providers':{
        'opencode':{'name':'OpenCode','cli_command':'opencode','default_model':'auto/coding','env_vars':{'OPENAI_BASE_URL':'https://gateway.invalid/v1','OPENAI_API_KEY':'fixture-private'}},
        'anthropic':{'cli_command':'claude','env_vars':{}},'other':{'cli_command':'openclaude','env_vars':{'OPENAI_MODEL':'unchanged'}}}}
    file=tmp_path/'providers.json';file.write_text(json.dumps(data))
    monkeypatch.setattr(routes,'PROVIDERS_CONFIG',file);monkeypatch.setattr(routes,'PROVIDERS_EXAMPLE_CONFIG',tmp_path/'absent.json')
    monkeypatch.setattr(routes,'_check_cli',lambda _: {'installed':True,'version':'fixture','path':'/fixture'})
    app=Flask(__name__);app.secret_key='test-only';app.register_blueprint(routes.bp)
    login=LoginManager(app)
    class User(UserMixin):id=1;role='admin';username='fixture'
    login.user_loader(lambda _:User())
    c=app.test_client()
    with c.session_transaction() as session:session['_user_id']='1';session['_fresh']=True
    return c,file,data,tmp_path


def runtime(config,model,cwd):
    result=subprocess.run(['node',str(ROOT/'qa/providers-model/config-chat-fixture.cjs')],input=json.dumps({'config':config,'model':model,'base':'https://gateway.invalid/v1','cwd':str(cwd)}),text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr
    proof=json.loads(result.stdout.splitlines()[-1]);assert proof['provider_calls']==0 and proof['transport_calls']==1
    return proof


def test_legacy_opencode_default_reaches_chat_without_rewriting_config(configuration):
    c,file,original,tmp=configuration
    before=file.read_bytes()
    view=c.get('/api/providers/opencode/config').get_json()
    assert view['env_vars']['OPENAI_MODEL']=='auto/coding'
    assert 'OPENAI_MODEL' in view['env_var_names']
    listed=c.get('/api/providers').get_json()['providers'];assert next(p for p in listed if p['id']=='opencode')['env_vars']['OPENAI_MODEL']=='auto/coding'
    assert file.read_bytes()==before
    assert runtime(original,'auto/coding',tmp)['active']=='opencode'


@pytest.mark.parametrize("mode",[None,"code"])
def test_explicit_saved_model_survives_api_roundtrip_and_reaches_transport(configuration,mode):
    c,file,original,tmp=configuration
    if mode:
        original['providers']['opencode']['mode']=mode;file.write_text(json.dumps(original))
    response=c.post('/api/providers/opencode/config',json={'env_vars':{'OPENAI_MODEL':'Britto-Core','OPENAI_API_KEY':'','BASH_ENV':'forbidden'}})
    assert response.status_code==200
    expected=copy.deepcopy(original);expected['providers']['opencode']['env_vars']['OPENAI_MODEL']='Britto-Core'
    assert json.loads(file.read_text())==expected
    assert c.get('/api/providers/opencode/config').get_json()['env_vars']['OPENAI_MODEL']=='Britto-Core'
    assert runtime(expected,'Britto-Core',tmp)['credential_preserved'] is True


def test_native_and_unrelated_provider_fields_remain_unchanged(configuration):
    c,file,original,tmp=configuration
    c.post('/api/providers/anthropic/config',json={'env_vars':{'OPENAI_MODEL':'should-not-add'}})
    c.post('/api/providers/opencode/config',json={'env_vars':{'OPENAI_MODEL':'bad;command'}})
    assert json.loads(file.read_text())==original
