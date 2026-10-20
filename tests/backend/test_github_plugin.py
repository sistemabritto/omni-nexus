"""Actual plugin discovery/configuration/health routes; fixture token and HTTP."""
from pathlib import Path
import sqlite3
from unittest.mock import Mock
import yaml
import pytest
from tests.backend.test_managed_live_context import setup,ORIGIN

ROOT=Path(__file__).resolve().parents[2]


def test_plugin_manifest_has_protected_credential_and_authenticated_health():
    from plugin_schema import PluginManifest
    manifest=PluginManifest.model_validate(yaml.safe_load((ROOT/'plugins/github/plugin.yaml').read_text()))
    integration=manifest.integrations[0]
    assert integration.env_vars[0].secret and integration.env_vars[0].required
    assert integration.health_check.headers['Authorization']=='Bearer ${GITHUB_PLUGIN_TOKEN}'
    assert integration.health_check.url=='https://api.github.com/user'
    from provider_fallback import _build_agent_run_env
    assert 'GITHUB_PLUGIN_TOKEN' not in _build_agent_run_env({'GITHUB_PLUGIN_TOKEN':'never-forward'})


def test_panel_can_configure_token_and_test_without_returning_it(setup,tmp_path,monkeypatch):
    app,c,login,_,_,_=setup
    from routes import integrations as mod
    monkeypatch.setattr(mod,'WORKSPACE',tmp_path)
    monkeypatch.setattr(mod,'SKILLS_DIR',tmp_path/'.claude/skills')
    monkeypatch.setattr(mod,'PLUGINS_DIR',ROOT/'plugins')
    monkeypatch.setattr(mod,'DB_PATH',tmp_path/'dashboard.db')
    with sqlite3.connect(mod.DB_PATH) as conn:
        conn.execute('''CREATE TABLE integration_health_cache (
            plugin_slug TEXT NOT NULL, integration_slug TEXT NOT NULL,
            last_status TEXT, last_checked_at TEXT, last_error TEXT,
            PRIMARY KEY(plugin_slug,integration_slug))''')
    monkeypatch.setattr(mod,'audit',lambda *_a,**_kw:None)
    monkeypatch.delenv('GITHUB_PLUGIN_TOKEN',raising=False)
    # dotenv may set this variable; register its restoration with monkeypatch.
    monkeypatch.setenv('GITHUB_PLUGIN_TOKEN','')
    app.register_blueprint(mod.bp);login()
    headers={**ORIGIN,'X-Requested-With':'XMLHttpRequest'}
    url='/api/integrations/plugin/plugin-github-github'
    token='fixture-token-should-stay-on-server'
    saved=c.post(url,json={'env_vars':{'GITHUB_PLUGIN_TOKEN':token}},headers=headers)
    assert saved.status_code==200 and token not in saved.text
    assert 'GITHUB_PLUGIN_TOKEN' in (tmp_path/'.env').read_text()
    catalog=c.get('/api/integrations').json
    item=next(x for x in catalog['integrations'] if x.get('slug')=='plugin-github-github')
    assert item['kind']=='plugin' and item['configured'] and token not in str(catalog)
    assert item['status']=='pending'
    requests=[]
    def get(url,**kw):
        requests.append((url,kw));return Mock(status_code=200)
    monkeypatch.setattr(mod.http,'get',get)
    tested=c.post(url+'/test',json={},headers=headers)
    assert tested.status_code==200 and tested.json['ok'] is True
    assert token not in tested.text
    assert requests[0][0]=='https://api.github.com/user'
    assert requests[0][1]['headers']['Authorization']=='Bearer '+token
    assert requests[0][1]['allow_redirects'] is False
    item=next(x for x in c.get('/api/integrations').json['integrations'] if x.get('slug')=='plugin-github-github')
    assert item['configured'] is True and item['status']=='connected'
    assert item['last_health']['last_status']=='ok' and token not in str(item)
    from models import db,User
    with app.app_context():
        db.session.get(User,32).role='viewer';db.session.commit()
    login(32)
    assert c.post(url,json={'env_vars':{'GITHUB_PLUGIN_TOKEN':token}},headers=headers).status_code==403
    assert c.post(url+'/test',json={},headers=headers).status_code==403


def test_health_header_rejects_undeclared_credentials():
    from plugin_schema import PluginIntegration
    with pytest.raises(ValueError,match='not declared'):
        PluginIntegration.model_validate({'slug':'github','label':'GitHub','category':'productivity',
            'env_vars':[],'health_check':{'type':'http','url':'https://api.github.com/user',
                'headers':{'Authorization':'Bearer ${OTHER_SECRET}'}}})
