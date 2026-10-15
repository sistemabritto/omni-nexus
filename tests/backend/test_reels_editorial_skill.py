"""Editorial recovery tests: model failure stops before writes/integrations."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / '.claude/skills/social-reels-editorial'
sys.path.insert(0, str(ROOT / 'dashboard/backend'))


def test_discovery_and_local_links():
    from flask import Flask
    from routes.skills import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    item = next(s for s in client.get('/api/skills').json['skills'] if s['name'] == FOLDER.name)
    assert item['description'] and not item['has_scripts']
    assert client.get('/api/skills/' + FOLDER.name).status_code == 200
    assert all(p.suffix in {'', '.md'} for p in FOLDER.rglob('*') if p.is_file())
    for f in FOLDER.glob('*.md'):
        for link in re.findall(r'\]\(([^)]+)\)', f.read_text()):
            if not link.startswith('https://'):
                assert (FOLDER / link).is_file()


def test_personas_and_existing_script_entry_recover_guidance():
    from provider_fallback import _agent_prompt
    pointer = '.claude/skills/social-reels-editorial/SKILL.md'
    for agent in ['pixel-social-media', 'reels-copilot']:
        assert pointer in _agent_prompt(agent)
    assert pointer in (ROOT / '.claude/skills/social-reels-scripts/SKILL.md').read_text()


def test_real_inprocess_prompt_contains_guidance_and_original_schema(monkeypatch):
    import provider_fallback
    import reels_copilot
    calls = []
    def model_failure(**kwargs):
        calls.append(kwargs)
        return {'status': 'error', 'error': 'fixture model disabled'}
    monkeypatch.setattr(provider_fallback, 'resilient_invoke', model_failure)
    monkeypatch.setattr(reels_copilot.sqlite3, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('No DB allowed')))
    result = reels_copilot.generate_reel('fixture theme — não publicar')
    assert result['ok'] is False and len(calls) == 1
    prompt = calls[0]['prompt']
    assert calls[0]['agent'] == ''
    assert (FOLDER / 'SKILL.md').read_text() in prompt
    assert reels_copilot._REEL_SCHEMA_HINT in prompt
    assert prompt.endswith(reels_copilot._REEL_SCHEMA_HINT)
    assert 'fixture theme — não publicar' in prompt


def test_missing_guidance_preserves_schema_and_existing_flow(monkeypatch, tmp_path, caplog):
    import provider_fallback
    import reels_copilot
    calls = []
    def model_failure(**kwargs):
        calls.append(kwargs)
        return {'status': 'error', 'error': 'fixture only'}
    monkeypatch.setattr(provider_fallback, 'resilient_invoke', model_failure)
    monkeypatch.setattr(reels_copilot, 'WORKSPACE', tmp_path)
    result = reels_copilot.generate_reel()
    assert result['ok'] is False
    assert 'preserving existing protocol' in caplog.text
    assert calls[0]['prompt'].endswith(reels_copilot._REEL_SCHEMA_HINT)
    assert 'Orientação editorial local' not in calls[0]['prompt']


def test_origin_and_mit_notice():
    assert 'd03c56bb598be770c60b201f94237e5d1a4268a6' in (FOLDER / 'ORIGIN.md').read_text()
    assert 'Copyright (c) 2026 Jake Schincariol' in (FOLDER / 'LICENSE').read_text()
