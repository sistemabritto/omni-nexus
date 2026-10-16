"""Bounded media retries. The dashboard owns eligibility across worker restarts."""

from datetime import datetime, timedelta, timezone
import random

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 60
BACKOFF_CAP_SECONDS = 3600


def permanent_error(error: str) -> bool:
    text = (error or "").casefold()
    return any(marker in text for marker in (
        "manifesto de entrada não encontrado", "manifesto de entrada inválido",
        "manifesto inválido", "manifesto não encontrado", "publication_manifest.json inválido",
        "binary not found", "não encontrado no path", "permission denied",
        "read-only file system", "unauthorized", "forbidden", "invalid api key",
        "skill de produção indisponível",
    ))


def failure_state(attempt_count: int, error: str, *, terminal: bool = False,
                  now: datetime | None = None) -> tuple[str, str | None]:
    if terminal or permanent_error(error) or attempt_count >= MAX_ATTEMPTS:
        return "failed", None
    delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** max(0, attempt_count - 1))
    # Positive jitter never retries earlier than the advertised base delay.
    delay = min(BACKOFF_CAP_SECONDS, delay * random.uniform(1, 1.25))
    retry_at = (now or datetime.now(timezone.utc)) + timedelta(seconds=delay)
    return "retryable_failure", retry_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def migrate_retry_state(conn) -> None:
    """Additive migration; quarantine exhausted legacy retries, preserving errors."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(media_jobs)")}
    if "next_retry_at" not in cols:
        conn.execute("ALTER TABLE media_jobs ADD COLUMN next_retry_at TEXT")
    conn.execute(
        "UPDATE media_jobs SET status='failed', next_retry_at=NULL, "
        "locked_at=NULL, locked_by=NULL "
        "WHERE status='retryable_failure' AND attempt_count >= ? AND locked_at IS NULL",
        (MAX_ATTEMPTS,),
    )
