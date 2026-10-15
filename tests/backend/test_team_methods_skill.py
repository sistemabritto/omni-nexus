"""Verify existing-runtime retrieval, not an operational controller."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / '.claude/skills/dev-team-methods'
AGENTS = ['clawdia-assistant', 'helm-conductor', 'compass-planner', 'bolt-executor',
          'hawk-debugger', 'mako-marketing', 'pixel-social-media', 'nex-sales',
          'dex-data', 'lens-reviewer', 'oath-verifier']


@pytest.mark.parametrize('agent', AGENTS)
def test_runtime_recovers_role_and_references(agent):
    sys.path.insert(0, str(ROOT / 'dashboard/backend'))
    from provider_fallback import _agent_prompt, _embed_agent_for_openclaude
    pointer = '.claude/skills/dev-team-methods/SKILL.md'
    assert pointer in _agent_prompt(agent)
    assert pointer in _embed_agent_for_openclaude('Inspect fixture only', agent)
    text = (FOLDER / 'SKILL.md').read_text()
    row = next(line for line in text.splitlines() if line.startswith('| ' + agent + ' |'))
    targets = row.split('|')[3].strip().split(', ')
    for target in targets:
        assert (FOLDER / target).is_file(), (agent, target)


def test_registry_text_only_package_and_local_links():
    sys.path.insert(0, str(ROOT / 'dashboard/backend'))
    from flask import Flask
    from routes.skills import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    item = next(s for s in client.get('/api/skills').json['skills'] if s['name'] == FOLDER.name)
    assert item['description'] and not item['has_scripts']
    assert client.get('/api/skills/' + FOLDER.name).status_code == 200
    for f in FOLDER.iterdir():
        assert f.is_file() and (f.suffix == '.md' or f.name.startswith('LICENSE-'))
        if f.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', f.read_text()):
                if not target.startswith('https://'):
                    assert (FOLDER / target).is_file()


def test_attribution_pins_and_notices_preserved():
    text = (FOLDER / 'ORIGIN.md').read_text()
    assert '652b2692f8d8ec2b1f1a38e559073e287dfdc469' in text
    assert 'bb92a77741419a4ab5f06e711a283343f1ada0c3' in text
    for name in ['LICENSE-agency-agents', 'LICENSE-superpowers']:
        notice = (FOLDER / name).read_text()
        assert 'MIT License' in notice and 'Copyright' in notice and 'Permission is hereby granted' in notice
