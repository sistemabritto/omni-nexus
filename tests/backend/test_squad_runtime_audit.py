"""Exercise real read boundaries offline; no model/provider/tool invocation."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'dashboard/backend'))
from agent_catalog import catalog_entry, reference_documents


def test_subdocument_does_not_claim_root_read(tmp_path):
    folder = tmp_path / '.claude/skills/dev-team-methods'
    folder.mkdir(parents=True)
    (folder / 'SKILL.md').write_text('root')
    (folder / 'design-critique.md').write_text('reference')
    entry = catalog_entry('canvas-designer', '.claude/skills/dev-team-methods/design-critique.md', tmp_path)
    root = next(x for x in entry['knowledge'] if x['name'] == 'dev-team-methods')
    assert root['document_present'] is True and root['persona_reference'] is False
    assert entry['reference_documents'] == [{
        'path': '.claude/skills/dev-team-methods/design-critique.md',
        'kind': 'reference_document', 'document_present': True,
        'read_instruction_in_persona': True, 'model_read_status': 'not_verified',
        'operational_status': 'not_verified'}]


def test_reference_boundaries_missing_duplicate_and_escaping_symlink(tmp_path):
    pointer = '.claude/skills/example/references/check.md'
    outside = tmp_path.parent / (tmp_path.name + '-outside.md')
    outside.write_text('not authorized as workspace evidence')
    target = tmp_path / pointer
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    try:
        source = 'Read `' + pointer + '` twice ' + pointer + '\n# Persistent Agent Memory\n.claude/skills/private/SKILL.md'
        refs = reference_documents(source, tmp_path)
        assert len(refs) == 1 and refs[0]['document_present'] is False
        target.unlink()
        target.write_text('local')
        assert reference_documents(source, tmp_path)[0]['document_present'] is True
        target.unlink()
        assert reference_documents(source, tmp_path)[0]['document_present'] is False
    finally:
        outside.unlink()


def test_real_cleaner_and_independent_visual_reviewer_pointers(monkeypatch):
    import provider_fallback
    monkeypatch.setattr(provider_fallback, 'WORKSPACE', ROOT)
    roles = {
        'zen-simplifier': ['.claude/skills/dev-ai-slop-cleaner/SKILL.md'],
        'oath-verifier': ['.claude/skills/design-quality/SKILL.md',
                          '.claude/skills/design-quality/review.md',
                          '.claude/skills/design-quality/contrast.md'],
        'canvas-designer': ['.claude/skills/dev-team-methods/design-critique.md'],
    }
    for slug, pointers in roles.items():
        persona = provider_fallback._agent_prompt(slug)
        assembled = provider_fallback._embed_agent_for_openclaude('offline audit task', slug)
        for pointer in pointers:
            assert pointer in persona and pointer in assembled
            assert (ROOT / pointer).is_file()
        # Only the pointer is injected by this loader, not the whole cookbook.
        if slug == 'oath-verifier':
            assert '4,499 falha em 4,5' not in assembled


def test_offline_audit_provenance_and_catalog_coverage():
    spec = importlib.util.spec_from_file_location('squad_audit', ROOT / 'scripts/audit_squad_runtime.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.build_audit(ROOT)
    assert len(result['agents']) == 42
    assert all(x['persona_present'] for x in result['agents'])
    assert len(result['adapted_modules']) == 6
    for item in result['adapted_modules']:
        assert item['document_present'] and item['origin_present']
        assert item['upstream_pins'] and item['license_notices']
        assert not item['local_links_missing']
        assert item['script_candidates'] == []
        assert item['operational_status'] == 'not_verified'


def test_looping_symlink_is_missing_evidence_not_endpoint_failure(tmp_path):
    target = tmp_path / '.claude/skills/example/SKILL.md'
    target.parent.mkdir(parents=True)
    target.symlink_to(target.name)
    refs = reference_documents('.claude/skills/example/SKILL.md', tmp_path)
    assert refs[0]['document_present'] is False
    assert refs[0]['operational_status'] == 'not_verified'


def test_frontmatter_and_memory_do_not_become_read_instructions(tmp_path):
    source = ('---\nexample: .claude/skills/front/SKILL.md\n---\n'
              'Read .claude/skills/visible/check.md\n'
              '## MEMORY.md\n.claude/skills/private/SKILL.md')
    refs = reference_documents(source, tmp_path)
    assert [item['path'] for item in refs] == ['.claude/skills/visible/check.md']
    assert refs[0]['document_present'] is False
