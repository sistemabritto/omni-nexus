"""Discovery and instruction contracts; no LLM/visual execution claimed."""
import re
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / '.claude/skills/mkt-creative-brief'


def test_discovery_and_real_agent_links():
    sys.path.insert(0, str(ROOT / 'dashboard/backend'))
    from flask import Flask
    from routes.skills import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    result = client.get('/api/skills').json
    item = next(s for s in result['skills'] if s['name'] == 'mkt-creative-brief')
    assert item['description'] and not item['has_scripts']
    assert client.get('/api/skills/mkt-creative-brief').status_code == 200
    for agent in ['mako-marketing', 'pixel-social-media', 'canvas-designer']:
        assert '.claude/skills/mkt-creative-brief/SKILL.md' in (ROOT / '.claude/agents' / (agent + '.md')).read_text()
    for f in FOLDER.glob('*.md'):
        for link in re.findall(r'\]\(([^)]+)\)', f.read_text()):
            if not link.startswith('https://'):
                assert (FOLDER / link).is_file(), link
    assert all(f.suffix in {'', '.md'} for f in FOLDER.rglob('*') if f.is_file())


@pytest.mark.parametrize('contract', [
    'usuário / marca (caminho/versão) / hipótese',
    'hipóteses explícitas',
    'Preservar a marca Sistema Britto existente',
    'não são proibições estéticas universais',
    'números sem fonte não viram claims',
    'Sem renderizador disponível: entregar somente plano/storyboard',
    'Ler esta skill não autoriza executar pacotes',
    'acessar credenciais',
    'publicar',
    'não são competências instaladas',
])
def test_instruction_contracts(contract):
    assert contract in (FOLDER / 'SKILL.md').read_text()


def test_examples_and_provenance():
    examples = (FOLDER / 'examples.md').read_text()
    for topic in ['Hipóteses explícitas', 'Diagnóstico', 'Aplicação', 'Acompanhamento', 'CTA', 'Prova necessária', 'Landing mobile', 'Kit social', 'Storyboard sem renderizador']:
        assert topic in examples
    qa = (FOLDER / 'qa.md').read_text()
    assert all(level in qa for level in ['P0', 'P1', 'P2', 'nenhuma fonte'])
    origin = (FOLDER / 'ORIGIN.md').read_text()
    assert '7abd6fc2b11987c3940eb4ffc461478ff37c0b33' in origin
    assert 'referodesign/refero_skill' in origin
    assert 'Apache License' in (FOLDER / 'LICENSE').read_text()
