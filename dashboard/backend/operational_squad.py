"""Versioned squad eligibility, separate from historical catalog and ACL.

Fail closed on missing/malformed configuration. No dispatch/readiness inference.
"""
import json
import re
from pathlib import Path

MANIFEST_PATH = Path(__file__).with_name('operational-squad.json')
_SLUG = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def load_operational_squad():
    data = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('invalid_operational_squad')
    if type(data.get('version')) is not int or data['version'] != 1 or not isinstance(data.get('agents'), list):
        raise ValueError('invalid_operational_squad')
    members = {}
    for item in data['agents']:
        if (not isinstance(item, dict) or not isinstance(item.get('slug'), str)
                or not _SLUG.fullmatch(item['slug']) or item['slug'] in members
                or item.get('group') not in ('principal', 'support') or type(item.get('active')) is not bool):
            raise ValueError('invalid_operational_squad')
        members[item['slug']] = {'active': item['active'], 'group': item['group'], 'version': data['version']}
    return members
