"""Contract tests for textual logo knowledge and existing skill discovery."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_logo_skill_discovered_by_existing_registry():
    sys.path.insert(0, str(ROOT / 'dashboard/backend'))
    from flask import Flask
    from routes.skills import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    response = client.get('/api/skills')
    assert response.status_code == 200
    skill = next(x for x in response.json['skills'] if x['name'] == 'logo-design')
    assert skill['description'] and skill['has_scripts'] is False
    assert client.get('/api/skills/logo-design').status_code == 200


def test_logo_knowledge_is_text_only_with_resolvable_references():
    import re
    folder = ROOT / '.claude/skills/logo-design'
    skill = (folder / 'SKILL.md').read_text()
    for target in re.findall(r'\]\(([^)]+)\)', skill):
        assert (folder / target).is_file(), target
    assert all(p.suffix in {'.md', ''} for p in folder.rglob('*') if p.is_file())
    assert not (folder / 'scripts').exists()
    agent = (ROOT / '.claude/agents/canvas-designer.md').read_text()
    assert '.claude/skills/logo-design/SKILL.md' in agent
    # Guardrails are instructions, not claims of executing a visual evaluation.
    for phrase in ['Checkpoint de aprovação', 'aguarde escolha explícita', 'não realizada', 'Não ativar por mera menção', 'preservar', 'indisponíveis/desabilitados']:
        assert phrase.lower() in skill.lower()
    origin = (folder / 'ORIGIN.md').read_text()
    assert '0ecf52e9a4b3ac92b714f7cc6e3148ab8c774134' in origin
    assert '1.432' in origin and 'EXCLUÍDOS' in origin
