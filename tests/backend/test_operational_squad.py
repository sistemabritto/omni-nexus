"""Manifest eligibility does not replace catalog/ACL or assert runtime readiness."""
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
import operational_squad


def test_approved_twelve_reconcile_aliases_and_existing_portraits():
    from agent_catalog import NATIVE_CATALOG
    roster = operational_squad.load_operational_squad()
    assert len(roster) == 12
    assert all(entry['active'] is True for entry in roster.values())
    assert sum(entry['group'] == 'principal' for entry in roster.values()) == 6
    assert sum(entry['group'] == 'support' for entry in roster.values()) == 6
    assert set(roster) == {'clawdia-assistant', 'mako-marketing', 'pixel-social-media', 'canvas-designer', 'bolt-executor', 'oath-verifier', 'atlas-project', 'sage-strategy', 'raven-critic', 'hawk-debugger', 'lens-reviewer', 'probe-qa'}
    root = Path(__file__).resolve().parents[2]
    for slug in roster:
        assert (root / '.claude/agents' / (slug + '.md')).is_file()
        assert slug in NATIVE_CATALOG
    assert [NATIVE_CATALOG[slug]['display_name'] for slug in list(roster)[:6]] == ['Hera', 'Orion', 'Dante', 'Íris', 'Vulcano', 'Argos']
    portrait_slugs = set()
    for group in ('squad-v2', 'squad-support-v2'):
        data = json.loads((root / 'dashboard/frontend/public/avatar' / group / 'manifest.json').read_text())
        portrait_slugs.update(item['slug'] for item in data['portraits'])
    assert set(roster) <= portrait_slugs
    assert [NATIVE_CATALOG[slug]['display_name'] for slug in list(roster)[6:]] == ['Atlas', 'Sage', 'Raven', 'Hawk', 'Lens', 'Probe']


@pytest.mark.parametrize('data', [[], {}, {'version': True, 'agents': []}, {'version': 1, 'agents': [{'slug': '../x', 'group': 'support', 'active': True}]}, {'version': 1, 'agents': [{'slug': 'a', 'group': 'support', 'active': 'true'}]}, {'version': 1, 'agents': [{'slug': 'a', 'group': 'support', 'active': True}]*2}])
def test_invalid_manifest_fails_closed(tmp_path, monkeypatch, data):
    path = tmp_path / 'squad.json'
    path.write_text(json.dumps(data))
    monkeypatch.setattr(operational_squad, 'MANIFEST_PATH', path)
    with pytest.raises(ValueError):
        operational_squad.load_operational_squad()


def test_general_catalog_keeps_custom_historical_and_locked_agents(tmp_path, monkeypatch):
    from flask import Flask
    from flask_login import LoginManager
    from routes import agents
    personas = tmp_path / 'agents'
    personas.mkdir()
    for slug in ('mako-marketing', 'nex-sales', 'dex-data', 'custom-existing'):
        (personas / (slug + '.md')).write_text('---\ndescription: Existing\n---\nPersona')
    monkeypatch.setattr(agents, 'AGENTS_DIR', personas)
    monkeypatch.setattr(agents, 'AGENT_MEMORY_DIR', tmp_path / 'memory')
    monkeypatch.setattr(agents, 'has_agent_access', lambda role, name: name != 'mako-marketing')
    app = Flask(__name__)
    app.config['LOGIN_DISABLED'] = True
    LoginManager(app).user_loader(lambda uid: None)
    app.register_blueprint(agents.bp)
    client = app.test_client()
    rows = {row['name']: row for row in client.get('/api/agents').json}
    assert set(rows) == {'mako-marketing', 'nex-sales', 'dex-data', 'custom-existing'}
    assert rows['mako-marketing']['locked'] is True
    assert rows['mako-marketing']['operational_squad']['active'] is True
    assert all(rows[slug]['operational_squad']['active'] is False for slug in ('nex-sales', 'dex-data', 'custom-existing'))
    assert rows['custom-existing']['custom'] is True
    assert client.get('/api/agents/custom-existing').status_code == 200
    assert client.get('/api/agents/nex-sales').status_code == 200
    monkeypatch.setattr(agents, 'load_operational_squad', lambda: (_ for _ in ()).throw(ValueError()))
    assert len(client.get('/api/agents').json) == 4
    assert not any(row['operational_squad']['active'] for row in client.get('/api/agents').json)
