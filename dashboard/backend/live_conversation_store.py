"""Unwired, provider-independent continuity. Use only a dedicated database.

Callers supply authenticated identity and a current server ACL, never model IDs.
No provider calls, legacy ingestion, policy editing, or generated summarization.
"""
import json
import hashlib
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class ContinuityDenied(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: str
    company_id: int


KINDS = frozenset({'transcript', 'fact', 'inference', 'decision', 'pending', 'preference', 'progress', 'result'})


class ConversationStore:
    def __init__(self, path, allowed):
        self.path = str(path)
        # allowed(principal, conversation_id_or_None): live authorization callback.
        self.allowed = allowed

    def _guard(self, p, conversation=None):
        if (not isinstance(p, Principal) or not isinstance(p.user_id, str)
                or not p.user_id or type(p.company_id) is not int
                or p.company_id <= 0 or not self.allowed(p, conversation)):
            raise ContinuityDenied()

    @contextmanager
    def _db(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError('unsupported_continuity_schema')
            db.execute('''CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, company_id INTEGER NOT NULL,
                activity INTEGER NOT NULL DEFAULT 0)''')
            db.execute('''CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
                event_id TEXT NOT NULL, revision INTEGER NOT NULL, kind TEXT NOT NULL,
                text TEXT NOT NULL, source TEXT NOT NULL, verified INTEGER NOT NULL,
                retracted INTEGER NOT NULL, UNIQUE(conversation_id,event_id,revision))''')
            db.execute('''CREATE TABLE IF NOT EXISTS summaries (
                conversation_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                payload TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS receipts (
                conversation_id TEXT NOT NULL, request_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
                event_id TEXT NOT NULL, revision INTEGER NOT NULL,
                PRIMARY KEY(conversation_id,request_key))''')
            db.execute('PRAGMA user_version=1')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _owned(self, db, p, cid):
        self._guard(p, cid)
        row = db.execute('SELECT id FROM conversations WHERE id=? AND user_id=? AND company_id=?',
                         (cid, p.user_id, p.company_id)).fetchone()
        if row is None:
            raise ContinuityDenied()

    def create_explicit(self, p):
        """Only a human New conversation action should invoke this method."""
        self._guard(p)
        cid = uuid.uuid4().hex
        with self._db() as db:
            self._guard(p)
            db.execute('INSERT INTO conversations(id,user_id,company_id) VALUES(?,?,?)',
                       (cid, p.user_id, p.company_id))
            self._refresh(db, cid)
        return cid

    def latest(self, p, *, create_if_missing=False):
        """Resume default; no implicit creation. No content leaks for revoked IDs."""
        self._guard(p)
        with self._db() as db:
            rows = db.execute('SELECT id FROM conversations WHERE user_id=? AND company_id=? ORDER BY activity DESC,rowid DESC',
                              (p.user_id, p.company_id)).fetchall()
            cid = next((r['id'] for r in rows if self.allowed(p, r['id'])), None)
            if cid is None and create_if_missing:
                cid = uuid.uuid4().hex
                self._guard(p)
                db.execute('INSERT INTO conversations(id,user_id,company_id) VALUES(?,?,?)', (cid,p.user_id,p.company_id))
                self._refresh(db,cid)
            self._guard(p, cid)
            return cid

    @staticmethod
    def _current(db, cid):
        return db.execute('''SELECT e.* FROM events e WHERE conversation_id=?
            AND NOT EXISTS (SELECT 1 FROM events n WHERE n.conversation_id=e.conversation_id
            AND n.event_id=e.event_id AND n.revision>e.revision) ORDER BY seq''', (cid,)).fetchall()

    def _refresh(self, db, cid):
        current = self._current(db, cid)
        revision = db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE conversation_id=?', (cid,)).fetchone()[0]
        payload = {'facts': [], 'inferences': [], 'decisions': [], 'pending': [], 'preferences': []}
        mapping = {'fact': 'facts', 'inference': 'inferences', 'decision': 'decisions',
                   'pending': 'pending', 'preference': 'preferences'}
        for r in current:
            if r['retracted'] or r['kind'] in ('transcript', 'progress', 'result'):
                continue
            # Unverified claims never become facts/decisions/preferences.
            bucket = mapping[r['kind']] if r['verified'] else 'inferences'
            payload[bucket].append({'event_id': r['event_id'], 'revision': r['revision'],
                                    'text': r['text'], 'source': r['source'],
                                    'verified': bool(r['verified'])})
        db.execute('INSERT OR REPLACE INTO summaries VALUES(?,?,?)', (cid, revision, json.dumps(payload)))
        db.execute('UPDATE conversations SET activity=? WHERE id=?', (time.time_ns(), cid))

    def record(self, p, cid, *, kind, text, source, verified=False,
               event_id=None, expected_revision=None, retract=False, request_key=None):
        """Source/verified come from a trusted adapter or explicit user confirmation.

        A model suggestion MUST be stored unverified. Corrections require CAS;
        old revisions remain available in history, never in current context.
        """
        self._guard(p, cid)
        if (kind not in KINDS or not isinstance(text, str) or not text.strip()
                or len(text) > 4000 or not isinstance(source, str) or not source.strip()
                or len(source) > 200 or type(verified) is not bool or type(retract) is not bool):
            raise ValueError('invalid_event')
        if kind == 'inference' and verified:
            raise ValueError('inference_cannot_be_verified_fact')
        if request_key is not None and (not isinstance(request_key, str) or not 1 <= len(request_key) <= 128):
            raise ValueError('invalid_request_key')
        fingerprint = hashlib.sha256(json.dumps([kind,text,source,verified,event_id,expected_revision,retract]).encode()).hexdigest()
        eid = event_id or uuid.uuid4().hex
        with self._db() as db:
            self._owned(db, p, cid)
            if request_key is not None:
                receipt = db.execute('SELECT * FROM receipts WHERE conversation_id=? AND request_key=?', (cid,request_key)).fetchone()
                if receipt is not None:
                    if receipt['fingerprint'] != fingerprint:
                        raise ValueError('idempotency_conflict')
                    self._guard(p, cid)
                    return {'event_id':receipt['event_id'],'revision':receipt['revision']}
            previous = db.execute('SELECT MAX(revision) FROM events WHERE conversation_id=? AND event_id=?', (cid, eid)).fetchone()[0]
            if previous is None:
                if event_id is not None or expected_revision is not None or retract:
                    raise ValueError('unknown_event')
                revision = 1
            else:
                if type(expected_revision) is not int or expected_revision != previous:
                    raise ValueError('revision_conflict')
                revision = previous + 1
            db.execute('INSERT INTO events(conversation_id,event_id,revision,kind,text,source,verified,retracted) VALUES(?,?,?,?,?,?,?,?)',
                       (cid, eid, revision, kind, text, source, verified, retract))
            self._refresh(db, cid)
            if request_key is not None:
                db.execute('INSERT INTO receipts VALUES(?,?,?,?,?)', (cid,request_key,fingerprint,eid,revision))
            self._guard(p, cid)
        return {'event_id': eid, 'revision': revision}

    def snapshot(self, p, cid, *, history_limit=50):
        self._guard(p, cid)
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValueError('invalid_limit')
        with self._db() as db:
            self._owned(db, p, cid)
            summary = db.execute('SELECT revision,payload FROM summaries WHERE conversation_id=?', (cid,)).fetchone()
            history = db.execute('SELECT event_id,revision,kind,text,source,verified,retracted FROM events WHERE conversation_id=? ORDER BY seq DESC LIMIT ?', (cid, history_limit)).fetchall()
            self._guard(p, cid)
            return {'conversation_id': cid, 'summary_revision': summary['revision'],
                    'summary': json.loads(summary['payload']),
                    'history': [dict(r) for r in reversed(history)],
                    'history_limit': history_limit,
                    'current_context': [{'event_id': r['event_id'], 'revision': r['revision'],
                                         'kind': r['kind'], 'text': r['text'],
                                         'source': r['source'], 'verified': bool(r['verified'])}
                                        for r in self._current(db, cid) if not r['retracted']][-history_limit:],
                    'context_kind': 'untrusted_reference_data'}

    def events_since(self, p, cid, *, after=0, limit=100):
        """Revision stream for UI upsert by event_id; tombstones remove old content."""
        self._guard(p, cid)
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid_cursor')
        with self._db() as db:
            self._owned(db, p, cid)
            rows = db.execute('SELECT seq,event_id,revision,kind,text,source,verified,retracted FROM events WHERE conversation_id=? AND seq>? ORDER BY seq LIMIT ?', (cid, after, limit)).fetchall()
            self._guard(p, cid)
            return [dict(r) for r in rows]

    def search(self, p, terms, *, limit=5, exclude_event=None):
        """Query current revisions in this user's/company's persisted Live history.

        No vector index, imported transcript, schema change or new memory store.
        SQL restricts ownership BEFORE candidate selection. Authorization remains
        live per logical conversation and is checked again before returning.
        """
        self._guard(p)
        if (not isinstance(terms, list) or not 1 <= len(terms) <= 4
                or any(not isinstance(t, str) or not 1 <= len(t) <= 200 for t in terms)
                or type(limit) is not int or not 1 <= limit <= 5):
            raise ValueError('invalid_query')
        if exclude_event is not None and (not isinstance(exclude_event, tuple)
                or len(exclude_event) != 2
                or any(not isinstance(x, str) or not 1 <= len(x) <= 128 for x in exclude_event)):
            raise ValueError('invalid_excluded_event')
        excluded = exclude_event or ('', '')
        with self._db() as db:
            match = ' OR '.join('instr(lower(e.text),lower(?))>0' for _ in terms)
            score = ' + '.join('(instr(lower(e.text),lower(?))>0)' for _ in terms)
            rows = db.execute('''SELECT e.*, c.id AS logical_id, (''' + score + ''') AS relevance
                FROM events e JOIN conversations c ON c.id=e.conversation_id
                WHERE c.user_id=? AND c.company_id=? AND e.retracted=0
                AND NOT (e.conversation_id=? AND e.event_id=?)
                AND NOT EXISTS (SELECT 1 FROM events n WHERE n.conversation_id=e.conversation_id
                    AND n.event_id=e.event_id AND n.revision>e.revision)
                AND (''' + match + ''') ORDER BY relevance DESC, e.verified DESC,
                    CASE WHEN e.source LIKE 'browser:user:%' THEN 0 ELSE 1 END,
                    e.seq DESC LIMIT 100''',
                (*terms,p.user_id,p.company_id,*excluded,*terms)).fetchall()
            selected = []
            for row in rows:
                if self.allowed(p, row['logical_id']):
                    selected.append(dict(row))
                    if len(selected) == limit:
                        break
            self._guard(p)
            return [r for r in selected if self.allowed(p, r['logical_id'])]
