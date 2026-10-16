"""Explicit per-user/company file sources intersected with current Workspace ACL.

No directory crawling, ownership inference, file copying, network I/O or index.
Only reviewed file digests become searchable; a changed digest requires rebind.
"""
import hashlib
import os
import re
import stat
import uuid
from pathlib import PurePosixPath
from urllib.parse import quote

from flask_login import current_user
from models import has_permission
from werkzeug.exceptions import HTTPException

MAX_BYTES = 128 * 1024
MAX_BINDINGS = 32
_EXTENSIONS = frozenset(('.md', '.txt', '.html'))
_SECRET = re.compile(r'''-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{15,})|\bbearer\s+[A-Za-z0-9._-]{12,}|(?:api[_ -]?key|client[_ -]?secret|password|passwd|access[_ -]?token|authorization)\s*[:=]\s*["']?[^\s"']{8,}''', re.I)


class FileSourceDenied(Exception):
    pass


class FileSourceConflict(Exception):
    pass


def _permission():
    if not current_user.is_authenticated or not has_permission(current_user.role, 'workspace', 'view'):
        raise FileSourceDenied()


def _read(path):
    from routes import workspace
    _permission()
    if (not isinstance(path, str) or len(path) > 500 or '\\' in path or '\x00' in path
            or str(PurePosixPath(path)) != path):
        raise FileSourceDenied()
    parts = PurePosixPath(path).parts
    if (len(parts) < 3 or parts[0] != 'workspace' or PurePosixPath(path).suffix.lower() not in _EXTENSIONS
            or any(p in ('.', '..') or p.startswith('.') for p in parts)
            or any(re.search(r'(^|[-_.])(secrets?|credentials?|passwords?|tokens?|id_rsa)([-_.]|$)', p, re.I) for p in parts)):
        raise FileSourceDenied()
    try:
        # Canonical application gates, then no-follow descriptor traversal closes
        # the resolve/open symlink race and rejects every symlink component.
        workspace._resolve_safe(path, require_admin=False)
        workspace._check_folder_access(path)
        parent = os.open(workspace.WORKSPACE_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[1:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = child
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
                    raise FileSourceDenied()
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    raw = stream.read(MAX_BYTES + 1)
                after = os.fstat(fd)
                if len(raw) > MAX_BYTES or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                    raise FileSourceDenied()
            finally:
                os.close(fd)
        finally:
            os.close(parent)
        text = raw.decode('utf-8')
        if '\x00' in text or _SECRET.search(text):
            raise FileSourceDenied()
        return {'path': path, 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw),
                'mtimeNs': after.st_mtime_ns, 'text': text}
    except (OSError, UnicodeError, HTTPException) as exc:
        raise FileSourceDenied() from exc


def _table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS live_file_sources (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, company_id INTEGER NOT NULL,
        path TEXT NOT NULL, sha256 TEXT NOT NULL, revision INTEGER NOT NULL,
        active INTEGER NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id,company_id,path))''')


def _identity(row):
    _permission()
    if int(current_user.get_id()) != row['user_id']:
        raise FileSourceDenied()
    return (row['user_id'], row['company_id'])


def preview(conn, row, path):
    user, company = _identity(row)
    file = _read(path)
    _table(conn)
    binding = conn.execute('SELECT revision FROM live_file_sources WHERE user_id=? AND company_id=? AND path=?', (user, company, path)).fetchone()
    return {k: file[k] for k in ('path', 'sha256', 'size', 'mtimeNs')} | {'companyId': company, 'expectedRevision': binding['revision'] if binding else 0}


def bind(conn, row, *, path, sha256, expected_revision):
    user, company = _identity(row)
    if not has_permission(current_user.role, 'goals', 'manage'):
        raise FileSourceDenied()
    if (not isinstance(sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', sha256)
            or type(expected_revision) is not int or expected_revision < 0):
        raise ValueError('invalid_file_binding')
    file = _read(path)
    if file['sha256'] != sha256:
        raise FileSourceConflict()
    _table(conn)
    conn.execute('BEGIN IMMEDIATE')
    # A file cannot silently become shared across companies. Revocation and an
    # explicit new binding are needed to transfer its source association.
    if conn.execute('SELECT 1 FROM live_file_sources WHERE path=? AND company_id<>? AND active=1', (path, company)).fetchone():
        raise FileSourceConflict()
    old = conn.execute('SELECT * FROM live_file_sources WHERE user_id=? AND company_id=? AND path=?', (user, company, path)).fetchone()
    if (old['revision'] if old else 0) != expected_revision:
        raise FileSourceConflict()
    if (not old or not old['active']) and conn.execute('SELECT count(*) FROM live_file_sources WHERE user_id=? AND company_id=? AND active=1', (user, company)).fetchone()[0] >= MAX_BINDINGS:
        raise FileSourceConflict()
    if old:
        ident = old['id']
        conn.execute('UPDATE live_file_sources SET sha256=?, revision=revision+1, active=1, updated_at=CURRENT_TIMESTAMP WHERE id=?', (sha256, ident))
    else:
        ident = uuid.uuid4().hex
        conn.execute('INSERT INTO live_file_sources(id,user_id,company_id,path,sha256,revision,active) VALUES(?,?,?,?,?,1,1)', (ident, user, company, path, sha256))
    return {'id': ident, 'path': path, 'sha256': sha256, 'revision': expected_revision + 1, 'companyId': company, 'active': True}


def revoke(conn, row, ident, expected_revision):
    user, company = _identity(row)
    if not has_permission(current_user.role, 'goals', 'manage'):
        raise FileSourceDenied()
    if not isinstance(ident, str) or type(expected_revision) is not int or expected_revision < 1:
        raise ValueError('invalid_file_binding')
    _table(conn)
    changed = conn.execute('UPDATE live_file_sources SET active=0, revision=revision+1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND company_id=? AND revision=? AND active=1', (ident, user, company, expected_revision))
    if changed.rowcount != 1:
        raise FileSourceConflict()
    return {'id': ident, 'revision': expected_revision + 1, 'active': False}


def search(conn, row, terms):
    from live_query_excerpt import matching_excerpt
    try:
        user, company = _identity(row)
    except FileSourceDenied:
        return {'status': 'denied', 'source': 'explicit_workspace_files', 'results': []}
    _table(conn)
    bindings = conn.execute('SELECT * FROM live_file_sources WHERE user_id=? AND company_id=? AND active=1 ORDER BY updated_at DESC,id LIMIT ?', (user, company, MAX_BINDINGS)).fetchall()
    candidates = []
    available = 0
    for binding in bindings:
        try:
            file = _read(binding['path'])
        except FileSourceDenied:
            continue
        if file['sha256'] != binding['sha256']:
            continue
        available += 1
        score = sum(term.casefold() in (file['path']+' '+file['text']).casefold() for term in terms)
        if score:
            candidates.append((score, binding, file))
    results = []
    for _, binding, file in sorted(candidates, key=lambda x: -x[0])[:3]:
        # Recheck current ACL and digest immediately before serializing content.
        try:
            current = _read(file['path'])
        except FileSourceDenied:
            continue
        if current['sha256'] != binding['sha256']:
            continue
        live = conn.execute('SELECT 1 FROM live_file_sources WHERE id=? AND user_id=? AND company_id=? AND active=1 AND revision=? AND sha256=?', (binding['id'], user, company, binding['revision'], binding['sha256'])).fetchone()
        if live is None:
            continue
        results.append({'reference': '/api/workspace/file?path='+quote(file['path'], safe=''),
                        'bindingId': binding['id'], 'path': file['path'],
                        'revision': binding['revision'], 'sha256': file['sha256'],
                        'mtimeNs': file['mtimeNs'], 'source': 'explicit_workspace_file',
                        'text': matching_excerpt(file['text'], terms)})
    return {'status': 'available', 'source': 'explicit_workspace_files', 'results': results,
            'bindingCount': len(bindings), 'availableCount': available,
            'unavailableCount': len(bindings)-available, 'limit': 3,
            'policy': 'explicit_user_company_digest_and_current_workspace_acl'}


def list_bindings(conn, row):
    user, company = _identity(row)
    _table(conn)
    items = []
    for binding in conn.execute('SELECT * FROM live_file_sources WHERE user_id=? AND company_id=? AND active=1 ORDER BY updated_at DESC,id LIMIT ?', (user, company, MAX_BINDINGS)).fetchall():
        item = {'id': binding['id'], 'revision': binding['revision'], 'active': True, 'status': 'unavailable'}
        try:
            file = _read(binding['path'])
            item.update(path=binding['path'], sha256=binding['sha256'], status='current' if file['sha256']==binding['sha256'] else 'changed_rebind_required')
        except FileSourceDenied:
            pass
        items.append(item)
    return {'source': 'explicit_workspace_files', 'bindings': items, 'limit': MAX_BINDINGS}
