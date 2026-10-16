"""Heartbeat Dispatcher — schedules and dispatches heartbeat wake triggers.

Manages:
- interval: APScheduler jobs per heartbeat
- manual: triggered by POST /api/heartbeats/{id}/run
- mention / new_task: transactional, versioned ticket outbox (opt-in)
- approval_decision: existing approval event integration

Debounce: same heartbeat cannot trigger twice within 30s.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

import schedule

WORKSPACE = Path(__file__).resolve().parent.parent.parent

# Thread pool for async heartbeat runs (size 4)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hb-worker")
_schedule_lock = threading.Lock()

# Execution lock — prevents same heartbeat_id from running concurrently.
# Slot is reserved in dispatch() (main thread) before _executor.submit(),
# released in _run()'s finally block (worker thread).
_running: set[str] = set()
_running_lock = threading.Lock()

# Debounce window (seconds)
DEBOUNCE_SECONDS = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _get_db():
    import sqlite3
    from pathlib import Path as _Path
    db_path = WORKSPACE / "dashboard" / "data" / "evonexus.db"
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _is_debounced(heartbeat_id: str) -> tuple[bool, str | None]:
    """Check if a heartbeat was triggered within the debounce window.

    Returns (is_debounced, existing_trigger_id).
    """
    conn = _get_db()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=DEBOUNCE_SECONDS)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        row = conn.execute(
            """SELECT id FROM heartbeat_triggers
               WHERE heartbeat_id = ? AND created_at > ? AND consumed_at IS NULL
               AND coalesced_into IS NULL
               ORDER BY created_at DESC LIMIT 1""",
            (heartbeat_id, cutoff),
        ).fetchone()
        if row:
            return True, row["id"]
        return False, None
    finally:
        conn.close()


def _record_trigger(heartbeat_id: str, trigger_type: str, payload: dict | None = None, coalesced_into: str | None = None) -> str:
    """Insert a trigger event and return its id."""
    trigger_id = str(uuid.uuid4())
    now = _now_iso()
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO heartbeat_triggers
               (id, heartbeat_id, trigger_type, payload, created_at, coalesced_into)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (trigger_id, heartbeat_id, trigger_type, json.dumps(payload or {}), now, coalesced_into),
        )
        conn.commit()
        return trigger_id
    finally:
        conn.close()


def _mark_trigger_consumed(trigger_id: str):
    """Mark trigger as consumed (run dispatched)."""
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE heartbeat_triggers SET consumed_at = ? WHERE id = ?",
            (_now_iso(), trigger_id),
        )
        conn.commit()
    finally:
        conn.close()


def dispatch(heartbeat_id: str, trigger_type: str, payload: dict | None = None) -> tuple[bool, str | None]:
    """Dispatch a heartbeat run with debounce protection.

    Returns (dispatched, run_id).
    Returns (False, None) if debounced or disabled.
    """
    if trigger_type in ("mention", "new_task"):
        # Ticket events need an authenticated, committed source event, not a
        # caller-provided payload passed straight to the executor.
        return False, None

    # Check if heartbeat is enabled in DB
    conn = _get_db()
    try:
        row = conn.execute("SELECT enabled FROM heartbeats WHERE id = ?", (heartbeat_id,)).fetchone()
        if not row or not row["enabled"]:
            print(f"[dispatcher] heartbeat {heartbeat_id} is disabled, skipping", flush=True)
            return False, None
    finally:
        conn.close()

    # Debounce check
    debounced, existing_id = _is_debounced(heartbeat_id)
    if debounced:
        # Record coalesced trigger
        _record_trigger(heartbeat_id, trigger_type, payload, coalesced_into=existing_id)
        print(f"[dispatcher] {heartbeat_id} debounced (coalesced into {existing_id})", flush=True)
        return False, None

    # Record the trigger
    trigger_id = _record_trigger(heartbeat_id, trigger_type, payload)

    # Generate run_id
    run_id = str(uuid.uuid4())

    # Reserve execution slot — atomic check+add under lock.
    # Done in main thread (not in _run) to avoid TOCTOU race between workers.
    with _running_lock:
        if heartbeat_id in _running:
            _record_trigger(heartbeat_id, trigger_type, payload, coalesced_into=None)
            print(f"[dispatcher] {heartbeat_id} already running, coalesced run_id={run_id}", flush=True)
            return False, None
        _running.add(heartbeat_id)

    def _run():
        from heartbeat_runner import run_heartbeat
        try:
            _mark_trigger_consumed(trigger_id)
            run_heartbeat(
                heartbeat_id=heartbeat_id,
                triggered_by=trigger_type,
                trigger_id=trigger_id,
                run_id=run_id,
            )
        except Exception as exc:
            print(f"[dispatcher] ERROR running {heartbeat_id} run_id={run_id}: {exc}", flush=True)
        finally:
            with _running_lock:
                _running.discard(heartbeat_id)

    print(f"[dispatcher] dispatching {heartbeat_id} trigger_type={trigger_type} run_id={run_id}", flush=True)
    _executor.submit(_run)
    return True, run_id


# ── Interval scheduler ────────────────────────────────────────────────────────

def _load_enabled_heartbeats() -> list[dict]:
    """Load all heartbeats from DB (synced from YAML at startup)."""
    conn = _get_db()
    try:
        rows = conn.execute("SELECT * FROM heartbeats").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_heartbeats_to_db():
    """Mirror config/heartbeats.yaml into heartbeats table."""
    import sys
    import importlib

    # Ensure backend dir is in path
    backend_dir = Path(__file__).resolve().parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    try:
        from heartbeat_schema import load_heartbeats_yaml
        cfg = load_heartbeats_yaml()
    except Exception as exc:
        print(f"[dispatcher] WARNING could not load heartbeats.yaml: {exc}", flush=True)
        return

    now = _now_iso()
    conn = _get_db()
    try:
        for hb in cfg.heartbeats:
            existing = conn.execute(
                "SELECT id FROM heartbeats WHERE id = ?", (hb.id,)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO heartbeats
                       (id, agent, interval_seconds, max_turns, timeout_seconds,
                        lock_timeout_seconds, wake_triggers, enabled, goal_id,
                        required_secrets, decision_prompt, handler, source_plugin,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        hb.id, hb.agent, hb.interval_seconds, hb.max_turns,
                        hb.timeout_seconds, hb.lock_timeout_seconds,
                        json.dumps(hb.wake_triggers), int(hb.enabled), hb.goal_id,
                        json.dumps(hb.required_secrets), hb.decision_prompt,
                        hb.handler, hb.source_plugin,
                        now, now,
                    ),
                )
            else:
                # Update mutable fields but preserve enabled state set via UI
                conn.execute(
                    """UPDATE heartbeats SET
                       agent=?, interval_seconds=?, max_turns=?, timeout_seconds=?,
                       lock_timeout_seconds=?, wake_triggers=?, goal_id=?,
                       required_secrets=?, decision_prompt=?, handler=?, source_plugin=?,
                       updated_at=?
                       WHERE id=?""",
                    (
                        hb.agent, hb.interval_seconds, hb.max_turns, hb.timeout_seconds,
                        hb.lock_timeout_seconds, json.dumps(hb.wake_triggers), hb.goal_id,
                        json.dumps(hb.required_secrets), hb.decision_prompt,
                        hb.handler, hb.source_plugin, now,
                        hb.id,
                    ),
                )
        conn.commit()
        print(f"[dispatcher] synced {len(cfg.heartbeats)} heartbeats from YAML to DB", flush=True)
    finally:
        conn.close()


def _seconds_since_last_run(heartbeat_id: str) -> float | None:
    """Seconds since this heartbeat's most recent run started, or None if it
    has never run. Used by register_interval_jobs to catch up on heartbeats
    that are overdue relative to their OWN history — see that function's
    docstring for why this matters.
    """
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT started_at FROM heartbeat_runs WHERE heartbeat_id = ? "
            "ORDER BY started_at DESC LIMIT 1",
            (heartbeat_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["started_at"]:
        return None
    try:
        last = datetime.strptime(row["started_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - last).total_seconds()


def register_interval_jobs():
    """Register schedule jobs for all heartbeats with 'interval' wake trigger.

    `schedule.every(N).do(job)` always counts the first firing from THIS
    call, not from any persisted history — so a heartbeat that's mid-
    interval when the process restarts (a redeploy, a crash, `reload_config`
    after a plugin install) has its countdown reset to the full N, and
    starts looking "overdue" relative to its configured cadence even though
    nothing is actually broken. Confirmed live 2026-07-14: several redeploys
    in a short window left atlas-4h/zara-2h/flux-6h looking hours behind
    schedule purely because of restart timing, not a stuck dispatcher.
    Fires an immediate catch-up dispatch for anything already overdue by its
    own last-run history before/alongside registering the periodic job, so
    a redeploy costs at most one wasted-looking cycle, never a multi-hour
    stall. dispatch()'s existing 30s debounce makes this safe to call
    repeatedly (e.g. on every plugin-triggered reload_config).
    """
    _sync_heartbeats_to_db()
    heartbeats = _load_enabled_heartbeats()

    registered = 0
    for hb in heartbeats:
        try:
            triggers = json.loads(hb.get("wake_triggers", "[]"))
        except Exception:
            triggers = []

        if "interval" not in triggers:
            continue

        if not hb.get("enabled"):
            continue

        interval_secs = hb["interval_seconds"]
        hb_id = hb["id"]

        # Catch-up: if this heartbeat is already overdue by its own history
        # (last real run further back than its interval), fire it now
        # instead of waiting a full fresh interval from this process start.
        elapsed = _seconds_since_last_run(hb_id)
        if elapsed is not None and elapsed >= interval_secs:
            print(f"[dispatcher] {hb_id} overdue ({elapsed:.0f}s since last run, "
                  f"interval {interval_secs}s) — catch-up dispatch", flush=True)
            dispatch(hb_id, "interval")

        # Use schedule library (same as scheduler.py)
        # Tag the job so we can cancel it if needed
        tag = f"hb-interval-{hb_id}"

        def _make_job(heartbeat_id: str):
            def _job():
                dispatch(heartbeat_id, "interval")
            return _job

        with _schedule_lock:
            # Remove any existing job for this heartbeat
            schedule.clear(tag)

            if interval_secs < 60:
                interval_secs = 60  # safety floor

            if interval_secs % 3600 == 0:
                hours = interval_secs // 3600
                schedule.every(hours).hours.do(_make_job(hb_id)).tag(tag)
                print(f"[dispatcher] registered interval job for {hb_id} every {hours}h", flush=True)
            elif interval_secs % 60 == 0:
                minutes = interval_secs // 60
                schedule.every(minutes).minutes.do(_make_job(hb_id)).tag(tag)
                print(f"[dispatcher] registered interval job for {hb_id} every {minutes}m", flush=True)
            else:
                schedule.every(interval_secs).seconds.do(_make_job(hb_id)).tag(tag)
                print(f"[dispatcher] registered interval job for {hb_id} every {interval_secs}s", flush=True)

            registered += 1

    print(f"[dispatcher] {registered} interval jobs registered", flush=True)
    return registered


def start_dispatcher_thread():
    """Start a background thread that runs the heartbeat schedule loop."""
    def _loop():
        import time
        # A1: YAML é fonte de verdade — alinhar DB→YAML ANTES de registrar os
        # jobs, senão um heartbeat com enabled=true no YAML mas false no banco
        # (drift do "preserva UI") ficaria mudo até alguém reconciliar na mão.
        try:
            from hb_reconcile import run_reconcile_on_boot
            run_reconcile_on_boot()
        except Exception as exc:  # noqa: BLE001 — reconcile no boot nunca derruba o dispatcher
            print(f"[dispatcher] hb_reconcile on boot failed (non-fatal): {exc}", flush=True)
        register_interval_jobs()
        _last_drain = 0.0
        _DRAIN_EVERY_SECONDS = 15
        while True:
            schedule.run_pending()
            import time as _time
            if _time.monotonic() - _last_drain >= _DRAIN_EVERY_SECONDS:
                _last_drain = _time.monotonic()
                try:
                    drain_event_triggers()
                except Exception as exc:
                    print(f"[dispatcher] drain_event_triggers ERROR: {exc}", flush=True)
            time.sleep(5)

    t = threading.Thread(target=_loop, name="heartbeat-dispatcher", daemon=True)
    t.start()
    print("[dispatcher] dispatcher thread started", flush=True)


# ── Config reload (called by plugin_loader after install/uninstall) ──────────

def reload_config() -> dict:
    """Re-sync heartbeats from config + plugins and re-register interval jobs.

    Called by plugin_loader.PluginInstaller after copying heartbeats to
    plugins/{slug}/heartbeats.yaml (install) or after removing it (uninstall).
    Safe to call while the dispatcher is running — uses _schedule_lock.

    Returns:
        Dict with keys: heartbeats_loaded (int), jobs_registered (int).
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info("[reload_config] Re-syncing heartbeats (core + plugins)")
    _sync_heartbeats_to_db()

    with _schedule_lock:
        schedule.clear()

    count = register_interval_jobs()
    logger.info("[reload_config] Done: %d heartbeats, %d interval jobs", count, count)
    return {"heartbeats_loaded": count, "jobs_registered": count}


# ── Stub hooks for future triggers ───────────────────────────────────────────

def on_new_task(heartbeat_id: str, task_id: str):
    """Hook called when a new task is assigned. F1.3 will implement fully."""
    dispatch(heartbeat_id, "new_task", payload={"task_id": task_id})


def on_mention(heartbeat_id: str, mention_data: dict):
    """Hook called on agent mention. F1.3 will implement fully."""
    dispatch(heartbeat_id, "mention", payload=mention_data)


def on_approval_decision(heartbeat_id: str, approval_id: str, decision: str):
    """Hook called on approval resolution. F1.2 will implement fully."""
    dispatch(heartbeat_id, "approval_decision", payload={"approval_id": approval_id, "decision": decision})


# ── Event-trigger consumer (F1.3) ─────────────────────────────────────────────
#
# API handlers (e.g. _fire_mention_triggers on a ticket comment) INSERT a row
# into heartbeat_triggers, but nothing ever WOKES the agent — that was the gap
# ("mention morre na fila"). This poller claims each pending event trigger and
# runs its heartbeat, passing the ORIGINAL trigger_id so the runner loads the
# exact payload (ticket_id / comment_id / mentioner).

_EVENT_TRIGGER_TYPES = ("mention", "new_task", "approval_decision")


def _pending_event_triggers(limit: int = 200):
    """Bounded scan; disabled events do not monopolize the first twenty slots."""
    from ticket_wake_contract import enabled
    conn = _get_db()
    try:
        rows = conn.execute("""SELECT t.* FROM heartbeat_triggers t
            JOIN heartbeats h ON h.id=t.heartbeat_id
            WHERE t.consumed_at IS NULL AND t.coalesced_into IS NULL AND h.enabled=1
              AND t.trigger_type IN ('mention','new_task','approval_decision')
              AND (t.trigger_type='approval_decision' OR ?=1)
            ORDER BY t.created_at,t.id LIMIT ?""", (int(enabled()), limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _claim_event(row):
    """Reserve durable run + event atomically, across dispatcher processes."""
    from ticket_wake_contract import MAX_ATTEMPTS, MAX_IN_FLIGHT, validate
    conn = _get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        trigger = conn.execute("SELECT * FROM heartbeat_triggers WHERE id=? AND consumed_at IS NULL AND coalesced_into IS NULL", (row['id'],)).fetchone()
        hb = conn.execute("SELECT * FROM heartbeats WHERE id=?", (row['heartbeat_id'],)).fetchone()
        if not trigger or not hb or not hb['enabled'] or row['trigger_type'] not in json.loads(hb['wake_triggers'] or '[]'):
            return None
        try:
            payload = json.loads(trigger['payload'] or '{}')
            if not isinstance(payload, dict):
                raise ValueError()
            retry = payload.get('_dispatcher_retry', {})
            if not isinstance(retry, dict) or type(retry.get('attempts', 0)) is not int or not 0 <= retry.get('attempts', 0) <= MAX_ATTEMPTS or not isinstance(retry.get('next_at', ''), str):
                raise ValueError()
        except (ValueError, TypeError):
            conn.execute('UPDATE heartbeat_triggers SET consumed_at=?,payload=? WHERE id=?',
                         (_now_iso(), json.dumps({'_dispatcher_rejection':'invalid_event_payload'}), row['id']))
            conn.commit()
            return None
        if retry.get('next_at', '') > _now_iso():
            return None
        if row['trigger_type'] in ('mention', 'new_task'):
            if 'handler' in hb.keys() and hb['handler']:
                return None
            try:
                validate(conn, payload, hb['agent'], row['trigger_type'])
                if payload['event_id'] != row['id']:
                    raise ValueError('event_identity_mismatch')
            except ValueError as exc:
                # Retain an explicit terminal diagnostic, never silently infer legacy authority.
                payload['_dispatcher_rejection'] = str(exc)
                conn.execute('UPDATE heartbeat_triggers SET consumed_at=?,payload=? WHERE id=?', (_now_iso(), json.dumps(payload), row['id']))
                conn.commit()
                return None
        if retry.get('attempts', 0) >= MAX_ATTEMPTS:
            return None
        busy = conn.execute("""SELECT count(*) FROM heartbeat_runs r
            JOIN heartbeats h ON h.id=r.heartbeat_id
            WHERE r.status='running' AND h.agent=?""", (hb['agent'],)).fetchone()[0]
        total = conn.execute("SELECT count(*) FROM heartbeat_runs WHERE status='running'").fetchone()[0]
        if busy or total >= MAX_IN_FLIGHT:
            return None
        run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'heartbeat-event:' + row['id']))
        existing = conn.execute('SELECT status FROM heartbeat_runs WHERE run_id=?', (run_id,)).fetchone()
        if existing:
            # An uncertain/final prior execution must never be inferred again.
            conn.execute('UPDATE heartbeat_triggers SET consumed_at=? WHERE id=?', (_now_iso(), row['id']))
            conn.commit()
            return None
        conn.execute("""INSERT INTO heartbeat_runs(run_id,heartbeat_id,trigger_id,started_at,status,triggered_by,prompt_preview)
            VALUES(?,?,?,?,'running',?,'[event reserved]')""", (run_id, hb['id'], row['id'], _now_iso(), row['trigger_type']))
        conn.execute('UPDATE heartbeat_triggers SET consumed_at=? WHERE id=?', (_now_iso(), row['id']))
        conn.commit()
        return run_id
    finally:
        conn.rollback()
        conn.close()


def _return_unstarted_event(row, run_id):
    """Only before invocation: release reservation with durable bounded backoff."""
    from ticket_wake_contract import MAX_ATTEMPTS
    conn = _get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        deleted = conn.execute("DELETE FROM heartbeat_runs WHERE run_id=? AND status='running' AND prompt_preview='[event reserved]'", (run_id,)).rowcount
        if not deleted:
            return
        payload = json.loads(conn.execute('SELECT payload FROM heartbeat_triggers WHERE id=?', (row['id'],)).fetchone()[0])
        attempts = payload.get('_dispatcher_retry', {}).get('attempts', 0) + 1
        delay = 30 * (2 ** (attempts - 1))
        payload['_dispatcher_retry'] = {'attempts': attempts, 'reason': 'executor_unavailable',
            'next_at': (datetime.now(timezone.utc) + timedelta(seconds=delay)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}
        conn.execute('UPDATE heartbeat_triggers SET consumed_at=?,payload=? WHERE id=?',
                     (_now_iso() if attempts >= MAX_ATTEMPTS else None, json.dumps(payload), row['id']))
        conn.commit()
    finally:
        conn.rollback()
        conn.close()


def reconcile_event_reservations():
    """Recover only expired pre-invocation reservations. Never replay uncertain work."""
    conn = _get_db()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        rows = [dict(r) for r in conn.execute("""SELECT t.*,r.run_id FROM heartbeat_runs r
            JOIN heartbeat_triggers t ON t.id=r.trigger_id
            WHERE r.status='running' AND r.prompt_preview='[event reserved]' AND r.started_at<?""", (cutoff,))]
    finally:
        conn.close()
    for row in rows:
        _return_unstarted_event(row, row['run_id'])
    return len(rows)


def _start_event(row, run_id):
    """CAS marks invocation boundary; a stale queued callback cannot start work."""
    conn = _get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        hb = conn.execute('SELECT * FROM heartbeats WHERE id=?', (row['heartbeat_id'],)).fetchone()
        current = conn.execute('SELECT payload FROM heartbeat_triggers WHERE id=?', (row['id'],)).fetchone()
        reason = None
        if not hb or not hb['enabled'] or row['trigger_type'] not in json.loads(hb['wake_triggers'] or '[]'):
            reason = 'heartbeat_disabled_before_start'
        elif row['trigger_type'] in ('mention', 'new_task'):
            if 'handler' in hb.keys() and hb['handler']:
                reason = 'ticket_event_handler_not_supported'
            from ticket_wake_contract import validate
            try:
                validate(conn, json.loads(current['payload']), hb['agent'], row['trigger_type'])
            except ValueError as exc:
                reason = str(exc)
        if reason:
            conn.execute("UPDATE heartbeat_runs SET status='fail',ended_at=?,error=? WHERE run_id=? AND prompt_preview='[event reserved]'", (_now_iso(), reason, run_id))
            conn.commit()
            return False
        changed = conn.execute("UPDATE heartbeat_runs SET prompt_preview='[event executing]' WHERE run_id=? AND status='running' AND prompt_preview='[event reserved]'", (run_id,)).rowcount
        conn.commit()
        return changed == 1
    finally:
        conn.rollback()
        conn.close()


def drain_event_triggers() -> int:
    """Admit bounded, authorized events; reconcile reservations, not entire inboxes."""
    reconcile_event_reservations()
    dispatched = 0
    for row in _pending_event_triggers():
        hb_id = row['heartbeat_id']
        with _running_lock:
            if hb_id in _running or len(_running) >= 4:
                continue
            _running.add(hb_id)
        try:
            run_id = _claim_event(row)
            if run_id is None:
                with _running_lock:
                    _running.discard(hb_id)
                continue
        except Exception:
            with _running_lock:
                _running.discard(hb_id)
            raise

        def _run(row=row, hb_id=hb_id, run_id=run_id):
            try:
                from heartbeat_runner import run_heartbeat
                if _start_event(row, run_id):
                    run_heartbeat(heartbeat_id=hb_id, triggered_by=row['trigger_type'],
                                  trigger_id=row['id'], run_id=run_id)
            except Exception as exc:
                # Outcome unknown after invocation: retain durable running reservation;
                # reconciliation must not silently repeat a tool-enabled execution.
                print(f"[dispatcher] event run requires reconciliation hb={hb_id}: {type(exc).__name__}", flush=True)
            finally:
                with _running_lock:
                    _running.discard(hb_id)
        try:
            _executor.submit(_run)
        except Exception:
            try:
                _return_unstarted_event(row, run_id)
            finally:
                with _running_lock:
                    _running.discard(hb_id)
            continue
        dispatched += 1
    return dispatched
