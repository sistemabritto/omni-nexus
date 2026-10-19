"""Compatibility for persisted role identifiers after consolidating the squad."""
import json
import re
from pathlib import Path


def retirements(root):
    path=Path(root)/'scripts/squad-retirements.json'
    return json.loads(path.read_text()).get('agents',{}) if path.is_file() else {}


def agent_path(root, name):
    root=Path(root)
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',name):
        raise ValueError('invalid_agent_name')
    normal=root/'.claude/agents'/(name+'.md')
    target=retirements(root).get(name)
    if target:
        reference=root/'.claude/skills/squad-role-library/references'/(name+'.md')
        if reference.is_file() and not reference.is_symlink():
            return reference
        if not normal.is_file():
            return root/'.claude/agents'/(target+'.md')
    return normal
