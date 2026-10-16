"""Private result receipts: stable IDs, current source ACL/digest, no text cache."""
import hashlib
import json
import uuid
from pathlib import PurePosixPath
from urllib.parse import quote

from flask_login import current_user
from werkzeug.exceptions import HTTPException
from live_file_sources import FileSourceDenied, resolve_binding, source_text_allowed
from live_query_excerpt import matching_excerpt


def _table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS live_file_receipts (
        id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,company_id INTEGER NOT NULL,
        logical_id TEXT NOT NULL,source_kind TEXT NOT NULL,source_id TEXT NOT NULL,
        source_revision INTEGER NOT NULL,sha256 TEXT NOT NULL,terms_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id,company_id,logical_id,source_kind,source_id,source_revision,sha256))''')


def _recording(row, ident, sha256, revision):
    from recordings_access import require_company
    from models import Recording, RecordingScript
    try:
        require_company(row['company_id'])
        record = Recording.query.filter_by(id=ident, company_id=row['company_id']).first()
        if record is None or record.script_revision != revision:
            raise FileSourceDenied()
        script = RecordingScript.query.filter_by(recording_id=ident, number=revision).first()
        if script is None or not source_text_allowed(script.text) or script.sha256 != sha256 or hashlib.sha256(script.text.encode()).hexdigest() != sha256:
            raise FileSourceDenied()
        require_company(row['company_id'])
        return {'text': script.text, 'title': record.title, 'reference': '/api/recordings/'+ident}
    except HTTPException as exc:
        if exc.code not in (401, 403, 404):
            raise
        raise FileSourceDenied() from exc


def resolve(conn, row, ident):
    if int(current_user.get_id()) != row['user_id']:
        raise FileSourceDenied()
    _table(conn)
    receipt = conn.execute('SELECT * FROM live_file_receipts WHERE id=? AND user_id=? AND company_id=?',
                           (ident, row['user_id'], row['company_id'])).fetchone()
    if receipt is None:
        raise FileSourceDenied()
    if receipt['source_kind'] == 'workspace':
        file = resolve_binding(conn, row, receipt['source_id'], receipt['sha256'], receipt['source_revision'])
        title = PurePosixPath(file['path']).name
        original = '/api/workspace/file?path='+quote(file['path'], safe='')
    elif receipt['source_kind'] == 'recording_script':
        file = _recording(row, receipt['source_id'], receipt['sha256'], receipt['source_revision'])
        title = file['title']; original = file['reference']
    else:
        raise FileSourceDenied()
    terms = json.loads(receipt['terms_json'])
    reference = '/api/live/file-results/'+receipt['id']
    excerpt = matching_excerpt(file['text'], terms)
    return {'id': receipt['id'], 'title': title[:200], 'reference': reference,
            'sha256': receipt['sha256'], 'sourceRevision': receipt['source_revision'],
            'source': receipt['source_kind'], 'originalReference': original,
            'text': title[:200]+'\n'+excerpt, 'excerpt': excerpt,
            'createdAt': receipt['created_at'], 'content': file['text']}


def create(conn, row, logical_id, terms, *, files, documents):
    _table(conn)
    candidates = [('workspace', f['bindingId'], f['revision'], f['sha256']) for f in files]
    candidates += [('recording_script', f['recordingId'], f['revision'], f['sha256']) for f in documents]
    results = []
    for kind, ident, revision, digest in candidates[:3]:
        conn.execute('INSERT OR IGNORE INTO live_file_receipts(id,user_id,company_id,logical_id,source_kind,source_id,source_revision,sha256,terms_json) VALUES(?,?,?,?,?,?,?,?,?)',
                     (uuid.uuid4().hex, row['user_id'], row['company_id'], logical_id, kind, ident, revision, digest, json.dumps(terms)))
        receipt = conn.execute('SELECT id FROM live_file_receipts WHERE user_id=? AND company_id=? AND logical_id=? AND source_kind=? AND source_id=? AND source_revision=? AND sha256=?',
                               (row['user_id'], row['company_id'], logical_id, kind, ident, revision, digest)).fetchone()
        try:
            current = resolve(conn, row, receipt['id'])
        except FileSourceDenied:
            continue
        results.append({k: current[k] for k in ('id', 'title', 'reference', 'sha256', 'sourceRevision', 'source', 'createdAt')})
    return results
