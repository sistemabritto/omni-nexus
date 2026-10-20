"""Bounded, credential-free discovery for the authenticated Live controller."""
import re
from pathlib import Path
from flask_login import current_user
from models import has_permission
from routes._helpers import parse_frontmatter
from skill_capability_dispatch import _SECRET


def skill_catalog(root, query='', limit=None):
    if not has_permission(current_user.role, 'skills', 'view'):
        return {'items': [], 'total': 0, 'status': 'denied'}
    base = Path(root) / '.claude/skills'
    if base.is_symlink():return {'items':[],'total':0,'status':'unavailable'}
    terms = query.casefold().split()
    rows = []
    for folder in sorted(base.iterdir()) if base.is_dir() else []:
        file = folder / 'SKILL.md'
        if folder.is_symlink() or file.is_symlink() or not file.is_file():
            continue
        try:
            with file.open(encoding='utf-8') as stream:
                meta = parse_frontmatter(stream.read(5000))
        except (OSError, UnicodeError):
            continue
        description = str(meta.get('description', '')).replace('\\n', ' ')[:180]
        if _SECRET.search(description):
            description = ''
        text = (folder.name + ' ' + description).casefold()
        if terms and not any(term in text for term in terms):
            continue
        # An unfiltered request is the complete compact index, not a sample.
        rows.append({'name': folder.name, **({'description': description} if query else {})})
    return {'items': rows if limit is None else rows[:limit], 'total': len(rows), 'truncated': limit is not None and len(rows)>limit,
            'status': 'available', 'execution': 'knowledge_only; use an authorized adapter for actions'}


def integration_catalog(row=None):
    if not has_permission(current_user.role, 'integrations', 'view'):
        return {'items': [], 'status': 'denied'}
    from routes.integrations import list_integrations
    data = list_integrations().get_json()
    rows = [{'name': str(item.get('name', ''))[:100], 'configured': item.get('configured') is True,
             'category': str(item.get('category', item.get('type', '')))[:70]}
            for item in data.get('integrations', []) if isinstance(item, dict)]
    from live_github import metadata
    rows=[x for x in rows if x['name']!='GitHub']
    rows.append(metadata(row))
    return {'items': rows[:30], 'total': len(rows), 'status': 'available',
            'meaning': 'configured means credentials are present; not a successful health check or execution permission'}


def catalog(root,row=None):
    from operational_squad import load_operational_squad
    from live_workspace_actions import AREAS
    from agent_catalog import NATIVE_CATALOG
    from models import has_agent_access
    from live_adapters import catalog as adapters
    squad=[{'agentName':slug,'name':NATIVE_CATALOG.get(slug,{}).get('display_name',slug),
            'function':NATIVE_CATALOG.get(slug,{}).get('function','')[:160]}
           for slug,item in load_operational_squad().items() if item['active'] and has_agent_access(current_user.role,slug)]
    return {'squad':squad,'skills': skill_catalog(root, limit=12), 'integrations': integration_catalog(row),
            'adapters':adapters(row) if row is not None else {'status':'scope_not_supplied'},
            'readTools': ['list_omni_capabilities', 'read_omni_skill', 'list_omni_assets','inspect_omni_area'],
            'writeTools': ['create_omni_artifact', 'create_omni_media','create_omni_image','update_omni_area','write_omni_document','operate_omni_adapter'],
            'workspaceAreas': list(AREAS),
            'approvalPolicy': __import__('live_approval_policy').policy(),
            'scope': 'current authenticated user and company; no credentials exposed'}


def read_skill(root, name, offset=0):
    if not has_permission(current_user.role, 'skills', 'view') or not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', name):
        raise PermissionError('skill_access_denied')
    base = Path(root) / '.claude/skills';folder=base/name;file=folder/'SKILL.md'
    if base.is_symlink() or folder.is_symlink() or file.is_symlink() or not file.is_file():
        raise ValueError('skill_unavailable')
    if type(offset) is not int or not 0 <= offset <= 128000:
        raise ValueError('invalid_skill_offset')
    with file.open(encoding='utf-8') as stream:
        text=stream.read(128001)
    # A skill is reference data. Its commands never become tool authority.
    if len(text)>128000 or _SECRET.search(text) or '\x00' in text:
        raise ValueError('skill_contains_sensitive_material')
    if offset>len(text):raise ValueError('invalid_skill_offset')
    end=min(offset+12000,len(text))
    return {'name':name,'text':text[offset:end], 'offset':offset,'totalCharacters':len(text),
            'nextOffset':end if end<len(text) else None,'truncated':end<len(text),
            'kind':'untrusted_reference_data','execution':'not_executed'}
