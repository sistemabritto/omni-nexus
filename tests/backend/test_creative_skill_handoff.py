"""Test the bounded loader-to-task boundary, not model behavior or visual taste."""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'dashboard/backend'))


@pytest.mark.parametrize('agent,documents', [
    ('mako-marketing', ['mkt-creative-brief/SKILL.md', 'mkt-research-pipeline/SKILL.md']),
    ('pixel-social-media', ['video-editorial-pipeline/SKILL.md', 'design-quality/video-review.md']),
    ('canvas-designer', ['video-editorial-pipeline/SKILL.md', 'design-quality/video-review.md', 'stickman-video-director/SKILL.md']),
    ('oath-verifier', ['design-quality/video-review.md', 'design-quality/review.md', 'dev-team-methods/design-critique.md']),
    ('zen-simplifier', ['dev-ai-slop-cleaner/SKILL.md']),
])
def test_existing_role_recovers_required_documents_before_memory_cut(monkeypatch, agent, documents):
    import provider_fallback
    monkeypatch.setattr(provider_fallback, 'WORKSPACE', ROOT)
    task = 'Fixture de handoff interno; sem modelos, publicação ou produção.'
    assembled = provider_fallback._embed_agent_for_openclaude(task, agent)
    for relative in documents:
        pointer = '.claude/skills/' + relative
        assert pointer in provider_fallback._agent_prompt(agent)
        assert pointer in assembled
        assert (ROOT / pointer).is_file()
    assert task in assembled
    assert '# Persistent Agent Memory' not in assembled


def test_video_reviewer_has_real_methods_and_schema_binding():
    import json
    from media_creative_review import validate_creative_review, METHODS
    reference = (ROOT / '.claude/skills/design-quality/video-review.md').read_text()
    for source, version in METHODS.values():
        assert source in reference and (ROOT / source).is_file()
        origin = (ROOT / source).parent / 'ORIGIN.md'
        assert version in origin.read_text()
    fixture = json.loads((ROOT / 'docs/agents/evidence/creative-review-fixture.json').read_text())
    # Structure valid, deliberately synthetic: this is not an independent review.
    normalized = validate_creative_review(fixture, render_sha256=fixture['render_sha256'], version_id=fixture['version_id'])
    assert all('Fixture' in row['observation'] for row in normalized['criteria'].values())
