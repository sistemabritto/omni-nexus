"""Discovery and routing contracts only; never claims a CRM replay."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / '.claude/skills/mkt-research-pipeline'
METHODS = {
    'competitor-profiling': ('mako-marketing',),
    'product-marketing': ('mako-marketing', 'oath-verifier'),
    'social': ('pixel-social-media',),
    'copywriting': ('mako-marketing', 'pixel-social-media'),
    'cro': ('mako-marketing', 'oath-verifier'),
    'revops': ('nex-sales',),
    'analytics': ('dex-data',),
    'attribution': ('dex-data',),
}


def test_existing_discovery_and_text_only_package():
    sys.path.insert(0, str(ROOT / 'dashboard/backend'))
    from flask import Flask
    from routes.skills import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    items = client.get('/api/skills').json['skills']
    item = next(s for s in items if s['name'] == FOLDER.name)
    assert item['description'] and not item['has_scripts']
    assert client.get('/api/skills/' + FOLDER.name).status_code == 200
    assert all(f.suffix in {'', '.md'} for f in FOLDER.rglob('*') if f.is_file())
    for f in FOLDER.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)', f.read_text()):
            if not target.startswith('https://'):
                assert (f.parent / target).is_file(), (f, target)


@pytest.mark.parametrize('method,agents', METHODS.items())
def test_method_routes_survive_runtime_loader(method, agents):
    sys.path.insert(0, str(ROOT / 'dashboard/backend'))
    from provider_fallback import _agent_prompt, _embed_agent_for_openclaude
    skill = (FOLDER / 'SKILL.md').read_text()
    row = next(line for line in skill.splitlines() if line.startswith('| ' + method + ' |'))
    for agent in agents:
        assert agent in row
        assert '.claude/skills/mkt-research-pipeline/SKILL.md' in _agent_prompt(agent)
        assert '.claude/skills/mkt-research-pipeline/SKILL.md' in _embed_agent_for_openclaude('Review fixture only', agent)
    target = re.search(r'\]\(([^)]+)\)', row).group(1)
    assert (FOLDER / target).is_file()


def test_source_pin_license_and_existing_competitive_entry():
    assert '55ff469422c3592dac45bcad08dfb40221981c02' in (FOLDER / 'ORIGIN.md').read_text()
    assert 'Copyright (c) 2025 Corey Haines' in (FOLDER / 'LICENSE').read_text()
    assert '.claude/skills/mkt-research-pipeline/SKILL.md' in (ROOT / '.claude/skills/mkt-competitive-brief/SKILL.md').read_text()
    # Fixture matrix is a review artifact, not a routing implementation/test result.
    fixtures = (FOLDER / 'references/routing-fixtures.md').read_text()
    for case in ['Duplicação', 'Timeout', 'Resultado tardio', 'Owner indisponível', 'Empresa desconhecida']:
        assert '| ' + case + ' |' in fixtures
    assert 'replays operacionais são NÃO TESTADOS' in fixtures
