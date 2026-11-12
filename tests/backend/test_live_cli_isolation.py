"""Per-call config/credential isolation; no network or real credential needed."""
import json
from pathlib import Path
import pytest
import provider_fallback as pf


def restricted(**kwargs):
    token=pf._CLI_TOOL_POLICY.set('no_tools')
    try:return pf._invoke_cli('opencode','synthetic',2,30,provider_id='selected',model='model',**kwargs)
    finally:pf._CLI_TOOL_POLICY.reset(token)


def test_restricted_call_drops_parent_credentials_integrations_and_workspace(monkeypatch,tmp_path):
    foreign=tmp_path/'foreign';foreign.mkdir();config=foreign/'opencode.json';config.write_text('{"plugin":["foreign"]}')
    monkeypatch.setenv('HOME',str(foreign));monkeypatch.setenv('XDG_CONFIG_HOME',str(foreign))
    monkeypatch.setenv('OPENCODE_CONFIG',str(config));monkeypatch.setenv('OPENCODE_CONFIG_CONTENT','{"mcp":{"foreign":{}}}')
    for key in ('ANTHROPIC_API_KEY','TELEGRAM_BOT_TOKEN','OUT_OF_SCOPE_SECRET','OPENAI_API_KEY','NODE_OPTIONS','HTTPS_PROXY'):
        monkeypatch.setenv(key,'SYNTHETIC_PARENT_ONLY')
    monkeypatch.setattr(pf.shutil,'which',lambda _: '/fixture/opencode')
    homes=[]
    def actual_boundary(cmd,env,timeout,cwd,**kw):
        homes.append(Path(env['HOME']).parent)
        assert '--pure' in cmd and '--auto' not in cmd
        assert cwd!=foreign and cwd.is_dir() and cwd.parent==homes[-1]
        assert env['OPENAI_API_KEY']=='SYNTHETIC_SELECTED'
        assert 'SYNTHETIC_PARENT_ONLY' not in json.dumps(env)
        assert Path(env['OPENCODE_CONFIG']).is_relative_to(homes[-1])
        assert Path(env['OPENCODE_CONFIG']).read_text()=='{}'
        assert not any(k in env for k in ('NODE_OPTIONS','HTTPS_PROXY','TELEGRAM_BOT_TOKEN','ANTHROPIC_API_KEY','OUT_OF_SCOPE_SECRET'))
        assert env['OPENCODE_DISABLE_PROJECT_CONFIG']=='true'
        assert env['OPENCODE_DISABLE_CLAUDE_CODE']=='true'
        assert env['OPENCODE_DISABLE_EXTERNAL_SKILLS']=='true'
        assert str(foreign) not in json.dumps(env)
        d=json.loads(env['OPENCODE_CONFIG_CONTENT'])
        assert list(d['provider'])==['selected'] and d['enabled_providers']==['selected']
        assert d['plugin']==[] and d['mcp']=={} and d['instructions']==[]
        assert d['model']==d['small_model']=='selected/model'
        assert d['permission']['*']=='deny' and d['tools']['bash'] is False
        return {'status':'success','output':json.dumps({'type':'text','part':{'text':'safe'}})}
    monkeypatch.setattr(pf,'_invoke_cli_run',actual_boundary)
    result=restricted(cwd=foreign,env_overrides={'OPENAI_API_KEY':'SYNTHETIC_SELECTED','OPENAI_BASE_URL':'http://127.0.0.1:1234/v1','OPENCODE_CONFIG_CONTENT':'{"plugin":["foreign"]}','TELEGRAM_BOT_TOKEN':'SYNTHETIC_PARENT_ONLY'})
    assert result['status']=='success' and config.read_text()=='{"plugin":["foreign"]}'
    assert homes and not homes[0].exists()


@pytest.mark.parametrize('selected',[{}, {'OPENAI_BASE_URL':'https://example.test/v1'}, {'OPENAI_API_KEY':'synthetic'}, {'OPENAI_API_KEY':'synthetic','OPENAI_BASE_URL':'https://user:pass@example.test/v1'}, {'OPENAI_API_KEY':'synthetic','OPENAI_BASE_URL':'file:///tmp/provider'}])
def test_restricted_call_requires_explicit_selected_attempt(monkeypatch,selected):
    monkeypatch.setenv('OPENAI_API_KEY','PARENT_NOT_FALLBACK')
    monkeypatch.setattr(pf,'_invoke_cli_configured',lambda **kw:pytest.fail('must fail before CLI'))
    assert restricted(env_overrides=selected)['error']=='restricted_explicit_provider_required'


@pytest.mark.parametrize('outcome',['timeout','exception'])
def test_restricted_temp_state_removed_on_failure(monkeypatch,outcome):
    seen=[]
    def boundary(**kw):
        seen.append(Path(kw['isolated_env']['HOME']).parent)
        if outcome=='exception':raise RuntimeError('fixture')
        return {'status':'timeout'}
    monkeypatch.setattr(pf,'_invoke_cli_configured',boundary)
    args={'env_overrides':{'OPENAI_API_KEY':'synthetic','OPENAI_BASE_URL':'http://127.0.0.1:1234/v1'}}
    if outcome=='exception':
        with pytest.raises(RuntimeError):restricted(**args)
    else:assert restricted(**args)['status']=='timeout'
    assert seen and not seen[0].exists()


def test_unrestricted_call_keeps_legacy_config_path(monkeypatch,tmp_path):
    captured=[]
    monkeypatch.setattr(pf,'_invoke_cli_configured',lambda **kw:captured.append(kw) or {'status':'success'})
    supplied={'OPENCODE_CONFIG_CONTENT':'{"plugin":["legacy"]}'}
    pf._invoke_cli('opencode','fixture',2,30,env_overrides=supplied,cwd=tmp_path)
    assert captured[0]['env_overrides'] is supplied and captured[0]['cwd']==tmp_path
    assert 'isolated_env' not in captured[0]


def test_ancestor_config_is_refused_before_cli(monkeypatch,tmp_path):
    root=tmp_path/'isolated';root.mkdir()
    (tmp_path/'opencode.json').write_text('{"plugin":["outside"]}')
    assert pf._restricted_ancestor_config_present(root)
    monkeypatch.setattr(pf,'_restricted_ancestor_config_present',lambda _:True)
    monkeypatch.setattr(pf,'_invoke_cli_configured',lambda **kw:pytest.fail('must not launch'))
    assert restricted(env_overrides={'OPENAI_API_KEY':'synthetic','OPENAI_BASE_URL':'http://127.0.0.1:1234/v1'})['error']=='restricted_ancestor_config_present'


def test_machine_managed_config_refused_without_override(monkeypatch):
    original=Path.exists
    monkeypatch.setattr(Path,'exists',lambda p:True if str(p)=='/etc/opencode' else original(p))
    monkeypatch.setattr(pf,'_invoke_cli_configured',lambda **kw:pytest.fail('must not launch'))
    assert restricted(env_overrides={'OPENAI_API_KEY':'synthetic','OPENAI_BASE_URL':'http://127.0.0.1:1234/v1'})['error']=='restricted_managed_config_present'


def test_restricted_result_contains_only_text(monkeypatch):
    monkeypatch.setattr(pf,'_invoke_cli_configured',lambda **kw:{'status':'success','output':json.dumps({'type':'text','part':{'text':'ready draft'}})+'\n'+json.dumps({'type':'step_finish','part':{'cost':0}})})
    assert restricted(env_overrides={'OPENAI_API_KEY':'synthetic','OPENAI_BASE_URL':'http://127.0.0.1:1234/v1'})['output']=='ready draft'
