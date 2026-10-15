"""Runtime recovery and executable documentation boundary tests, no external tools."""
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / '.claude/skills'
QUALITY = SKILLS / 'design-quality'
STICK = SKILLS / 'stickman-video-director'


@pytest.fixture(scope='module')
def validator():
    # This exact local, pure reference block is the validator agents can read.
    code = re.search(r'```python\n(.*?)\n```', (QUALITY / 'contrast.md').read_text(), re.S).group(1)
    namespace = {}
    exec(compile(code, str(QUALITY / 'contrast.md'), 'exec'), namespace)
    return namespace


def test_runtime_recovery_before_memory_truncation():
    sys.path.insert(0, str(ROOT / 'dashboard/backend'))
    from provider_fallback import _agent_prompt
    for agent in ['canvas-designer', 'bolt-executor', 'oath-verifier', 'mako-marketing', 'pixel-social-media']:
        persona = _agent_prompt(agent)
        assert '.claude/skills/design-quality/SKILL.md' in persona, agent
        assert '.claude/skills/ui-ux-pro-max/SKILL.md' in persona
    for agent in ['canvas-designer', 'mako-marketing', 'pixel-social-media']:
        assert '.claude/skills/stickman-video-director/SKILL.md' in _agent_prompt(agent)
    for entry in ['AGENTS.md', '.claude/rules/design-quality.md', '.claude/skills/ui-ux-pro-max/SKILL.md']:
        assert '.claude/skills/design-quality/SKILL.md' in (ROOT / entry).read_text()


def test_existing_registry_and_text_only_resources():
    sys.path.insert(0, str(ROOT / 'dashboard/backend'))
    from flask import Flask
    from routes.skills import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    skills = {s['name']: s for s in client.get('/api/skills').json['skills']}
    for folder in [QUALITY, STICK]:
        assert not skills[folder.name]['has_scripts']
        assert client.get('/api/skills/' + folder.name).status_code == 200
        assert all(p.suffix in {'', '.md'} for p in folder.rglob('*') if p.is_file())
        for f in folder.glob('*.md'):
            for target in re.findall(r'\]\(([^)]+)\)', f.read_text()):
                if not target.startswith('https://'):
                    assert (folder / target).is_file(), target


@pytest.mark.parametrize('ratio,expected', [(4.499,False),(4.5,True),(4.501,True)])
def test_normal_threshold_without_rounding(validator, ratio, expected):
    assert validator['assess_ratio'](ratio, 18)['pass'] is expected


@pytest.mark.parametrize('ratio,expected', [(2.999,False),(3.0,True),(3.001,True)])
def test_large_threshold_without_rounding(validator, ratio, expected):
    assert validator['assess_ratio'](ratio, 24)['pass'] is expected


@pytest.mark.parametrize('size,bold,large', [
    (18,False,False),(23.999,False,False),(24,False,True),
    (18,True,False),(56/3-0.000001,True,False),(56/3,True,True),
])
def test_css_size_boundaries(validator, size, bold, large):
    result = validator['assess_ratio'](3.2, size, bold)
    assert result['large_text'] is large
    assert result['pass'] is large


def test_known_color_pairs_and_symmetry(validator):
    ratio = validator['contrast_ratio']
    assert ratio('#000', '#fff') == 21
    assert ratio('#fff', '#fff') == 1
    assert ratio('#123456', '#ABCDEF') == ratio('#ABCDEF', '#123456')
    assert 4.47 < ratio('#777777', '#FFFFFF') < 4.5
    assert not validator['assess_ratio'](ratio('#777777', '#fff'), 18)['pass']


@pytest.mark.parametrize('color', ['#1234', '#ffffff00', 'transparent', 'red', '#gggggg', '123456'])
def test_unsupported_colors_are_not_silently_certified(validator, color):
    with pytest.raises(ValueError):
        validator['contrast_ratio'](color, '#fff')


@pytest.mark.parametrize('ratio,size', [(float('nan'),18),(float('inf'),24),(0.9,18),(21.01,18),(4.5,0),(4.5,float('nan'))])
def test_invalid_evidence_rejected(validator, ratio, size):
    with pytest.raises(ValueError):
        validator['assess_ratio'](ratio, size)
