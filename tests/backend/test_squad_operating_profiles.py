"""Actual prompt assembly/Live section, not model execution or external tools."""
import hashlib,json,re
from pathlib import Path
import pytest
from squad_operating_profiles import PROFILES, operating_profile, operating_capsule
from agent_catalog import catalog_entry
ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('slug', PROFILES)
def test_role_profile_reaches_real_loader_and_live_without_truncation(slug,monkeypatch):
    import provider_fallback
    from routes import managed_live_context as live
    monkeypatch.setattr(provider_fallback,'WORKSPACE',ROOT)
    monkeypatch.setattr(live,'AGENTS_DIR',ROOT/'.claude/agents')
    profile=operating_profile(slug)
    prompt=provider_fallback._agent_prompt(slug)
    embedded=provider_fallback._embed_agent_for_openclaude('Internal fixture, no invocation.',slug)
    capsule=operating_capsule(slug)
    assert capsule in prompt and capsule in embedded
    assert prompt.count(capsule)==1
    assert "Use somente o nome exibido ao se apresentar" in capsule
    assert '# Persistent Agent Memory' not in prompt
    assert 'OmniNexus Operating Contract' in prompt
    identity=live._agent_identity({'agent_name':slug})
    assert identity['status']=='available' and identity['truncated'] is False
    assert capsule in identity['persona'] and len(identity['persona'])<=2500
    assert 'no_tools' in identity['persona'] and 'ponteiro não abre cookbook' in identity['persona']
    assert profile['display_name'] in identity['persona']
    for path in profile['methods']:
        assert path in prompt and (ROOT/path).is_file()
    for role in profile['roles']:
        assert role['reviewer'] in prompt and role['responsible'] in prompt
    source=(ROOT/'.claude/agents'/f'{slug}.md').read_text()
    assert catalog_entry(slug,source,ROOT)['delivery_profile']==profile


def test_author_text_frontmatter_and_memory_preserved_byte_for_byte():
    for row in json.loads((ROOT/'qa/squad-operating/prompt-preservation.json').read_text()):
        source=(ROOT/'.claude/agents'/f"{row['slug']}.md").read_text()
        source=re.sub(r'\n\n## OmniNexus Operating Contract\n<!-- BEGIN OMNINEXUS DELIVERY -->.*?<!-- END OMNINEXUS DELIVERY -->\n','',source,flags=re.S)
        if row['original_live_heading']:
            source=re.sub(r'\n<!-- BEGIN OMNINEXUS LIVE CAPSULE -->.*?<!-- END OMNINEXUS LIVE CAPSULE -->\n','',source,flags=re.S)
        else:
            source=re.sub(r'\n\n## Live Identity\n<!-- BEGIN OMNINEXUS LIVE CAPSULE -->.*?<!-- END OMNINEXUS LIVE CAPSULE -->\n\n## Persona Author Instructions\n','',source,flags=re.S)
        assert hashlib.sha256(source.encode()).hexdigest()==row['original_sha256'],row['slug']


def test_custom_and_other_specialists_are_not_replaced(tmp_path):
    custom='---\nname: custom-author\ndisallowedTools: Write\n---\nOriginal author instructions\n# Persistent Agent Memory\nOriginal memories'
    assert operating_profile('custom-author') is None
    assert operating_profile('nex-sales') is None
    entry=catalog_entry('custom-author',custom,tmp_path)
    assert entry['display_name']=='custom-author' and entry['delivery_profile'] is None
    assert entry['delivery_roles']==[]
