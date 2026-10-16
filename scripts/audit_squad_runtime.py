#!/usr/bin/env python3
"""Offline, read-only evidence of persona pointers. Never runs a skill or provider.

JSON goes to stdout; redirect explicitly to retain an audit. No config/env/DB,
agent memory, global skill roots, network or model access is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dashboard/backend'))
from agent_catalog import NATIVE_CATALOG, _runtime_body, catalog_entry

ADAPTED_MODULES = ('logo-design', 'mkt-creative-brief', 'design-quality',
                   'dev-team-methods', 'mkt-research-pipeline', 'social-reels-editorial')


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build_audit(root: Path) -> dict:
    root = root.resolve()
    skills = []
    for layer in ('skills', 'skills-media'):
        for folder in sorted((root / '.claude' / layer).glob('*')):
            if not folder.is_dir() or not folder.resolve().is_relative_to(root):
                continue
            document = next((folder / name for name in ('SKILL.md', 'skill.md')
                             if (folder / name).is_file()), None)
            if document is not None and not document.resolve().is_relative_to(root):
                document = None
            text = document.read_text(encoding='utf-8') if document else ''
            scripts = sorted(str(p.relative_to(root)) for p in folder.rglob('*')
                             if p.is_file() and p.suffix in {'.py', '.js', '.ts', '.sh'}
                             and p.resolve().is_relative_to(root))
            skills.append({'name': folder.name, 'layer': layer,
                           'document_present': document is not None,
                           'document_sha256': sha256(text) if document else None,
                           'listed_by_existing_skills_endpoint': layer == 'skills',
                           'script_candidates': scripts,
                           'executable_status': 'not_verified',
                           'operational_status': 'not_verified'})
    agents = []
    for slug in sorted(NATIVE_CATALOG):
        path = root / '.claude/agents' / (slug + '.md')
        source = path.read_text(encoding='utf-8') if path.is_file() else ''
        body = _runtime_body(source)
        catalog = catalog_entry(slug, source, root)
        # Exact backtick names identify additional discovery hints, not paths
        # loaded by the provider. Do not infer them from agent names/descriptions.
        named = set(re.findall(r'`([a-z0-9][a-z0-9-]*)`', body))
        named_skills = sorted({s['name'] for s in skills if s['name'] in named})
        agents.append({'slug': slug, 'persona_present': path.is_file(),
                       'bounded_persona_sha256': sha256(body),
                       'bounded_persona_chars': len(body),
                       'named_skill_hints': named_skills, 'catalog': catalog})
    modules = []
    for name in ADAPTED_MODULES:
        folder = root / '.claude/skills' / name
        entry = folder / 'SKILL.md'
        origin = folder / 'ORIGIN.md'
        text = entry.read_text(encoding='utf-8') if entry.is_file() else ''
        provenance = origin.read_text(encoding='utf-8') if origin.is_file() else ''
        notices = sorted(p for p in folder.glob('LICENSE*') if p.is_file())
        # Inventory only: executable-looking files are never executed here.
        scripts = sorted(str(p.relative_to(root)) for p in folder.rglob('*')
                         if p.is_file() and p.suffix in {'.py', '.js', '.ts', '.sh'}
                         and p.resolve().is_relative_to(root))
        missing_links = []
        for doc in folder.rglob('*.md'):
            if not doc.resolve().is_relative_to(root):
                continue
            for target in re.findall(r'\]\(([^)]+)\)', doc.read_text(encoding='utf-8')):
                if '://' in target or target.startswith('#'):
                    continue
                local = (doc.parent / target.split('#', 1)[0]).resolve()
                if not local.is_relative_to(root) or not local.is_file():
                    missing_links.append({'document': str(doc.relative_to(root)), 'target': target})
        modules.append({'name': name, 'document_present': entry.is_file(),
                        'document_sha256': sha256(text), 'origin_present': origin.is_file(),
                        'upstream_pins': sorted(set(re.findall(r'\b[0-9a-f]{40}\b', provenance))),
                        'license_notices': [{'path': str(p.relative_to(root)),
                                             'sha256': sha256(p.read_text(encoding='utf-8'))} for p in notices],
                        'local_links_missing': missing_links, 'script_candidates': scripts,
                        'operational_status': 'not_verified'})
    return {'schema_version': 1, 'scope': 'offline_native_persona_pointers_and_six_adapted_modules',
            'limits': ['Pointer presence is not skill-content injection or model reading.',
                       'Script presence is not executable availability or operational success.',
                       'Python provider persona slicing is not every runtime path.',
                       'No credentials, DB, memory, tools, providers or network were accessed.'],
            'agents': agents, 'skills': skills, 'adapted_modules': modules}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build_audit(args.workspace), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
