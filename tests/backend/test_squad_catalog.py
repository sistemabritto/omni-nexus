"""Read-only presentation metadata must not confer capabilities or permissions."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'dashboard/backend'))
from agent_catalog import NATIVE_CATALOG, catalog_entry, _runtime_body


def test_native_catalog_covers_current_personas_without_renaming():
    personas = {p.stem for p in (ROOT / '.claude/agents').glob('*.md') if not p.stem.startswith(('custom-', 'plugin-'))}
    from operational_squad import load_operational_squad
    from agent_roster import retirements
    assert personas == set(load_operational_squad())
    assert personas | (set(retirements(ROOT)) & set(NATIVE_CATALOG)) == set(NATIVE_CATALOG)
    assert all(v['display_name'] and v['function'] and v['sector_id'] for v in NATIVE_CATALOG.values())


@pytest.mark.parametrize('agent', sorted(NATIVE_CATALOG))
def test_evidence_uses_actual_runtime_body(agent):
    from provider_fallback import _agent_prompt
    from agent_roster import agent_path
    source = agent_path(ROOT, agent).read_text()
    assert _runtime_body(source) == _agent_prompt(agent)
    entry = catalog_entry(agent, source, ROOT)
    assert entry['evidence_scope'] == 'files_and_explicit_persona_paths_only'
    assert all(k['operational_status'] == 'not_verified' for k in entry['knowledge'])


def test_document_presence_and_memory_only_reference_are_distinct(tmp_path):
    skill = tmp_path / '.claude/skills/design-quality/SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('textual knowledge only')
    source = '---\nname: canvas-designer\n---\nPersona\n# Persistent Agent Memory\n.claude/skills/design-quality/SKILL.md'
    entry = catalog_entry('canvas-designer', source, tmp_path)
    quality = next(k for k in entry['knowledge'] if k['name'] == 'design-quality')
    assert quality['document_present'] is True
    assert quality['persona_reference'] is False
    assert quality['operational_status'] == 'not_verified'
    entry = catalog_entry('canvas-designer', '.claude/skills/design-quality/SKILL.md', tmp_path)
    assert next(k for k in entry['knowledge'] if k['name'] == 'design-quality')['persona_reference'] is True
    assert next(k for k in entry['knowledge'] if k['name'] == 'logo-design')['document_present'] is False


def test_unknown_custom_is_preserved_not_assigned_a_native_role(tmp_path):
    entry = catalog_entry('custom-existing', 'A custom persona', tmp_path)
    assert entry['display_name'] == 'custom-existing'
    assert entry['sector_id'] == 'custom'
    assert entry['knowledge'] == []


def test_existing_endpoint_adds_catalog_without_changing_acl_or_description(monkeypatch, tmp_path):
    from flask import Flask
    from routes import agents
    persona_dir = tmp_path / '.claude/agents'
    persona_dir.mkdir(parents=True)
    source = '---\nname: mako-marketing\ndescription: Original description\nmodel: sonnet\n---\nOriginal persona'
    (persona_dir / 'mako-marketing.md').write_text(source)
    (persona_dir / 'custom-existing.md').write_text('---\ndescription: Custom unchanged\n---\nCustom')
    monkeypatch.setattr(agents, 'AGENTS_DIR', persona_dir)
    monkeypatch.setattr(agents, 'WORKSPACE', tmp_path)
    monkeypatch.setattr(agents, 'AGENT_MEMORY_DIR', tmp_path / 'memories')
    monkeypatch.setattr(agents, 'has_agent_access', lambda role, name: name == 'custom-existing')
    app = Flask(__name__)
    app.config['LOGIN_DISABLED'] = True
    app.register_blueprint(agents.bp)
    from flask_login import LoginManager
    LoginManager(app).user_loader(lambda user: None)
    items = {x['name']: x for x in app.test_client().get('/api/agents').json}
    assert items['mako-marketing']['locked'] is True
    assert items['mako-marketing']['description'] == 'Original description'
    assert items['mako-marketing']['model'] == 'sonnet'
    assert items['mako-marketing']['catalog']['display_name'] == 'Orion'
    assert items['custom-existing']['locked'] is False
    assert items['custom-existing']['description'] == 'Custom unchanged'
    assert (persona_dir / 'mako-marketing.md').read_text() == source
