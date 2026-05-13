"""Knowledge API key CRUD — creation, verification, and revocation.

Token format: ``evo_k_<8char_prefix>.<base64url_secret>``

The prefix is stored as plain-text for O(1) lookup; only the full token is
bcrypt-hashed (rounds=12).  The plain token is returned exactly once, at
creation time.

Backend-portable: uses SQLAlchemy with named placeholders so the same code
path works on the dashboard's SQLite backend and on the Postgres backend
selected via ``SQLALCHEMY_DATABASE_URI`` / ``DATABASE_URL``.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from typing import Any

import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# Engine resolution — prefer Flask's shared engine, fall back to env URI.
# ---------------------------------------------------------------------------

_fallback_engine: Engine | None = None
_fallback_uri: str | None = None
_engine_lock = threading.Lock()


def _get_engine() -> Engine:
    """Return a SQLAlchemy Engine for the host DB.

    Order of resolution:
    1. Flask app's ``models.db.engine`` when inside an app context.
    2. A process-wide engine built from ``SQLALCHEMY_DATABASE_URI`` env var
       (used by CLI/worker/test contexts).
    """
    try:
        from flask import current_app  # noqa: F401 — only used to check ctx
        from models import db
        return db.engine
    except Exception:
        pass

    uri = os.environ.get("SQLALCHEMY_DATABASE_URI", "").strip()
    if not uri:
        raise RuntimeError(
            "No SQLAlchemy engine available: outside Flask app context and "
            "SQLALCHEMY_DATABASE_URI is unset."
        )

    global _fallback_engine, _fallback_uri
    with _engine_lock:
        if _fallback_engine is None or _fallback_uri != uri:
            _fallback_engine = create_engine(uri, future=True)
            _fallback_uri = uri
        return _fallback_engine


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

_PREFIX_LEN = 8
_SECRET_BYTES = 33  # ceil(44 * 6/8) — produces exactly 44 base64url chars


def _generate_token() -> tuple[str, str, str]:
    """Return (full_token, prefix, token_hash).

    full_token  — shown to the user exactly once
    prefix      — first 8 chars after ``evo_k_``, stored plain for lookup
    token_hash  — bcrypt digest of full_token, stored in DB
    """
    prefix = secrets.token_urlsafe(_PREFIX_LEN)[:_PREFIX_LEN]
    secret = urlsafe_b64encode(os.urandom(_SECRET_BYTES)).rstrip(b"=").decode()[:44]
    full_token = f"evo_k_{prefix}.{secret}"
    hashed = bcrypt.hashpw(full_token.encode(), bcrypt.gensalt(rounds=12)).decode()
    return full_token, prefix, hashed


# ---------------------------------------------------------------------------
# Ensure table exists (idempotent, portable across SQLite + Postgres).
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_api_keys (
    id TEXT PRIMARY KEY,
    name TEXT,
    prefix TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    space_ids TEXT NOT NULL DEFAULT '[]',
    scopes TEXT NOT NULL DEFAULT '["read"]',
    rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
    rate_limit_per_day INTEGER NOT NULL DEFAULT 10000,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    expires_at TEXT
)
"""

_CREATE_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_kak_prefix ON knowledge_api_keys(prefix)"


def ensure_table() -> None:
    """Idempotent — safe to call multiple times. Creates table on first use
    when the Alembic/host-DB migration hasn't been applied yet."""
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(text(_CREATE_TABLE_SQL))
        conn.execute(text(_CREATE_INDEX_SQL))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _row_to_dict(row) -> dict[str, Any]:
    """Convert a SQLAlchemy Row to a plain dict and decode JSON fields."""
    d = dict(row._mapping)
    d["space_ids"] = json.loads(d["space_ids"]) if d.get("space_ids") else []
    d["scopes"] = json.loads(d["scopes"]) if d.get("scopes") else []
    return d


def create_api_key(
    *,
    name: str | None,
    connection_id: str,
    space_ids: list[str] | None = None,
    scopes: list[str] | None = None,
    rate_limit_per_min: int = 60,
    rate_limit_per_day: int = 10000,
    expires_at: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Create a new API key.

    Returns ``(row_dict, plain_token)``.  ``plain_token`` is shown once only.
    """
    ensure_table()
    full_token, prefix, token_hash = _generate_token()
    key_id = str(uuid.uuid4())
    now = _now()
    space_ids = space_ids or []
    scopes = scopes or ["read"]

    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO knowledge_api_keys
                    (id, name, prefix, token_hash, connection_id, space_ids, scopes,
                     rate_limit_per_min, rate_limit_per_day, created_at, expires_at)
                VALUES (:id, :name, :prefix, :token_hash, :connection_id, :space_ids, :scopes,
                        :rate_limit_per_min, :rate_limit_per_day, :created_at, :expires_at)
                """
            ),
            {
                "id": key_id,
                "name": name,
                "prefix": prefix,
                "token_hash": token_hash,
                "connection_id": connection_id,
                "space_ids": json.dumps(space_ids),
                "scopes": json.dumps(scopes),
                "rate_limit_per_min": rate_limit_per_min,
                "rate_limit_per_day": rate_limit_per_day,
                "created_at": now,
                "expires_at": expires_at,
            },
        )

    row = get_api_key(key_id)
    return row, full_token  # type: ignore[return-value]


def get_api_key(key_id: str) -> dict[str, Any] | None:
    ensure_table()
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM knowledge_api_keys WHERE id = :id"),
            {"id": key_id},
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_api_keys(connection_id: str | None = None) -> list[dict[str, Any]]:
    ensure_table()
    engine = _get_engine()
    with engine.connect() as conn:
        if connection_id:
            rows = conn.execute(
                text(
                    "SELECT * FROM knowledge_api_keys "
                    "WHERE connection_id = :cid ORDER BY created_at DESC"
                ),
                {"cid": connection_id},
            ).fetchall()
        else:
            rows = conn.execute(
                text("SELECT * FROM knowledge_api_keys ORDER BY created_at DESC")
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def revoke_api_key(key_id: str) -> bool:
    """Hard-delete the API key row. Returns True if a row was deleted."""
    ensure_table()
    engine = _get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM knowledge_api_keys WHERE id = :id"),
            {"id": key_id},
        )
        return result.rowcount > 0


def verify_token(bearer: str) -> dict[str, Any] | None:
    """Verify a bearer token.

    Returns the api_key row if valid and not expired, else None.
    Uses prefix-first lookup (O(1)) then a single bcrypt.checkpw call.
    """
    if not bearer.startswith("evo_k_"):
        return None
    rest = bearer[len("evo_k_"):]
    parts = rest.split(".", 1)
    if len(parts) != 2:
        return None
    prefix = parts[0]

    ensure_table()
    # Compute "now" in Python so the WHERE clause is portable across SQLite + PG.
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")

    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT * FROM knowledge_api_keys "
                "WHERE prefix = :prefix "
                "  AND (expires_at IS NULL OR expires_at > :now)"
            ),
            {"prefix": prefix, "now": now_str},
        ).fetchall()

    for row in rows:
        d = _row_to_dict(row)
        try:
            if bcrypt.checkpw(bearer.encode(), d["token_hash"].encode()):
                try:
                    with engine.begin() as wconn:
                        wconn.execute(
                            text(
                                "UPDATE knowledge_api_keys SET last_used_at = :now "
                                "WHERE id = :id"
                            ),
                            {"now": _now(), "id": d["id"]},
                        )
                except Exception:
                    pass
                return d
        except Exception:
            continue

    return None
