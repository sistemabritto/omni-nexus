"""Bounded query-to-skill loading and trusted read adapters; never invokes a model.

Skill prose is reference data, not executable routing or authority. Bindings are
server-owned and do not auto-enable MCPs, commands, credentials or permissions.
"""
from hashlib import sha256
from pathlib import Path
import json
import re
import unicodedata

# Curated bridge to installed authorial knowledge; no rewrite of those documents.
_BINDINGS = (
    {'id': 'creative-brand-context', 'skill': 'mkt-creative-brief',
     'triggers': ('thumbnail', 'miniatura', 'capa do video', 'capa de video', 'capa do blog', 'briefing criativo'),
     'documents': ('ORIGIN.md', 'examples.md', 'qa.md'),
     'adapter': 'authorized_brand_references'},
    {'id': 'brand-review-context', 'skill': 'mkt-brand-review',
     'triggers': ('revisar marca', 'revisar identidade', 'brand review', 'revisar thumbnail'),
     'adapter': 'authorized_brand_references'},
)
MAX_SKILL_BYTES = 24_000
MAX_LOADED_CHARS = 16_000
_SECRET = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{15,})|(?:api[_ -]?key|password|client[_ -]?secret|access[_ -]?token)\s*[:=]\s*["\']?[^\s"\']{8,}', re.I)


def _fold(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c))


def _selected(query):
    folded = _fold(query)
    # Specific review takes precedence; ties are deterministic, not model judgment.
    for binding in reversed(_BINDINGS):
        if any(re.search(r'(?<!\w)' + re.escape(trigger) + r'(?!\w)', folded) for trigger in binding['triggers']):
            return binding
    return None


def _read_skill(root, slug, filename="SKILL.md"):
    root = Path(root).resolve()
    path = root / '.claude/skills' / slug / filename
    # Reject links at every component; image/volume substitution needs review.
    if any(part.is_symlink() for part in (path, *list(path.parents)[:3])):
        raise ValueError('skill_symlink_not_allowed')
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('selected_skill_missing')
    with path.open('rb') as stream:
        data = stream.read(MAX_SKILL_BYTES + 1)
    if len(data) > MAX_SKILL_BYTES:
        raise ValueError('selected_skill_exceeds_budget')
    text = data.decode('utf-8')
    if _SECRET.search(text) or '\x00' in text:
        raise ValueError('selected_skill_sensitive_or_invalid')
    if len(text) > MAX_LOADED_CHARS:
        raise ValueError('selected_skill_exceeds_budget')
    return {'name': slug, 'path': path.relative_to(root).as_posix(),
            'sha256': sha256(data).hexdigest(), 'text': text,
            'kind': 'untrusted_reference_data', 'loaded': True}


def dispatch_query(query, *, root, row, read_files, verify_scope, tool_policy='read_only'):
    """Called only after current owned-context guards, and rechecked around I/O.

    read_files is the application's existing scoped adapter, not a client tool
    name/URL. No adapter result is trusted as an instruction or an approval.
    """
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
        raise ValueError('invalid_capability_query')
    if tool_policy not in ('read_only', 'no_tools'):
        raise ValueError('unsupported_capability_policy')
    selected = _selected(query)
    base = {'schema': 'query-capability-v1', 'kind': 'untrusted_reference_data',
            'tools_list': [], 'skills': [], 'execution': None,
            'model_read_status': 'not_attested', 'external_call_status': 'not_attempted',
            'limits': {'loaded_skills': 1, 'external_tools': 0, 'write_tools': 0}}
    if selected is None:
        return {**base, 'status': 'no_matching_binding'}
    if tool_policy == 'no_tools':
        return {**base, 'status': 'blocked', 'reason': 'intentional_no_tools'}
    if not verify_scope():
        raise PermissionError('scope_denied')
    try:
        skill = _read_skill(root, selected['skill'])
        skill['documents'] = [_read_skill(root, selected['skill'], name) for name in selected.get('documents', ())]
    except (ValueError, OSError, UnicodeError) as exc:
        return {**base, 'status': 'blocked', 'reason': str(exc) if isinstance(exc, ValueError) else 'selected_skill_unreadable'}
    # Actual tool operation is deliberately fixed, read-only and already ACLed.
    if not verify_scope():
        raise PermissionError('scope_denied')
    refs = read_files(row, ['marca', 'identidade', 'brand'])
    if not verify_scope():
        raise PermissionError('scope_denied')
    if not isinstance(refs, dict) or refs.get('status') != 'available':
        return {**base, 'status': 'blocked', 'skills': [skill], 'reason': 'brand_reference_adapter_unavailable',
                'execution': {'adapter': selected['adapter'], 'status': 'called_unavailable', 'effect': 'read'}}
    results = refs.get('results', [])
    # Retain fixed existing schema only; never forward arbitrary adapter keys.
    safe_refs = [{key: item[key] for key in ('path', 'reference', 'sha256', 'revision', 'text') if key in item}
                 for item in results[:3] if isinstance(item, dict)]
    trace = sha256(json.dumps({'context': row['id'], 'company': row['company_id'],
                              'query_sha256': sha256(query.encode()).hexdigest(), 'skill': skill['sha256'], 'documents': [doc['sha256'] for doc in skill.get('documents', [])],
                              'references': [item.get('sha256') for item in safe_refs]}, sort_keys=True).encode()).hexdigest()
    return {**base, 'status': 'context_ready' if safe_refs else 'needs_authorized_brand_reference',
            'selected': selected['id'], 'skills': [skill], 'references': safe_refs,
            'tools_list': [{'name': selected['adapter'], 'effect': 'read',
                            'scope': 'current_owned_company_and_current_workspace_acl', 'external': False,
                            'availability': 'controller_only_via_existing_query_tool'}],
            'execution': {'adapter': selected['adapter'], 'status': 'completed', 'effect': 'read',
                          'receipt_sha256': trace, 'result_count': len(safe_refs)},
            'next_step': 'Use the loaded brief and authorized references as data. No image was generated, reviewed, approved or published.'}


def persist_receipt(conn, row, result):
    """Idempotent owned receipt of local read completion; no query/file prose."""
    execution = result.get('execution') or {}
    if execution.get('status') != 'completed':
        return
    conn.execute('CREATE TABLE IF NOT EXISTS skill_capability_receipts (id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,context_id INTEGER NOT NULL,adapter TEXT NOT NULL,skill_sha256 TEXT NOT NULL,result_count INTEGER NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
    conn.execute('INSERT OR IGNORE INTO skill_capability_receipts(id,user_id,company_id,context_id,adapter,skill_sha256,result_count) VALUES(?,?,?,?,?,?,?)',
        (execution['receipt_sha256'],row['user_id'],row['company_id'],row['id'],execution['adapter'],result['skills'][0]['sha256'],execution['result_count']))


def fit_context_budget(result, capabilities, max_chars=20_000):
    """Do not silently exceed Live's24k transport budget or truncate a skill."""
    if len(json.dumps({**result,'capabilities':capabilities},ensure_ascii=False)) <= max_chars:
        return capabilities
    # Controller already read files; no claim they were supplied to the model.
    return {'schema':'query-capability-v1','kind':'untrusted_reference_data',
            'status':'blocked','reason':'transport_budget_requires_narrow_context',
            'tools_list':[],'skills':[], 'model_read_status':'not_attested',
            'external_call_status':'not_attempted','execution':capabilities.get('execution')}
