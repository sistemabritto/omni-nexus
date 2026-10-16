"""Versioned, fail-closed ticket wake context; no dispatch or ticket mutations.

The shared dashboard bearer token authenticates a service user, not an agent.
Only browser-authenticated admins can originate v1 automatic wakes. Agent-origin
chaining remains unsupported until an authenticated runtime identity exists.
"""
import hashlib
import json
import os
import uuid

SCHEMA = 'ticket-wake-v1'
MAX_ATTEMPTS = 3
MAX_IN_FLIGHT = 4


def enabled():
    return os.environ.get('TICKET_EVENT_WAKES_ENABLED') == '1'


def context(conn, ticket_id):
    """Read identifiers from the source of truth and reject mixed companies."""
    row = conn.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
    if row is None:
        raise ValueError('ticket_missing')
    t = dict(row)
    company = conn.execute('SELECT status FROM companies WHERE id=?', (t['company_id'],)).fetchone()
    if not company or company['status'] != 'active':
        raise ValueError('company_inactive')
    project_id = t.get('project_id')
    goal_id = t.get('goal_id')
    if goal_id is not None:
        goal = conn.execute('SELECT project_id FROM goals WHERE id=?', (goal_id,)).fetchone()
        if not goal or (project_id is not None and project_id != goal['project_id']):
            raise ValueError('goal_project_mismatch')
        project_id = goal['project_id']
    mission_id = None
    if project_id is not None:
        project = conn.execute('SELECT company_id,mission_id FROM projects WHERE id=?', (project_id,)).fetchone()
        if not project or project['company_id'] != t['company_id']:
            raise ValueError('project_company_mismatch')
        mission_id = project['mission_id']
        if mission_id is not None:
            # Missions have no company_id in the real schema; scope comes from project.
            mission = conn.execute('SELECT id FROM missions WHERE id=?', (mission_id,)).fetchone()
            if not mission:
                raise ValueError('mission_missing')
    return {'company_id': t['company_id'], 'ticket_id': t['id'],
            'ticket_version': t['updated_at'], 'owner': t['assignee_agent'],
            'goal_id': goal_id, 'project_id': project_id, 'mission_id': mission_id,
            'task_id': t.get('task_id'), 'status': t['status']}


def envelope(ctx, *, actor_user_id, recipient, kind, source_id):
    if kind not in ('mention', 'new_task'):
        raise ValueError('unsupported_event')
    material = [SCHEMA, ctx, actor_user_id, recipient, kind, source_id]
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, SCHEMA + ':' + digest))
    return dict(ctx, schema=SCHEMA, event_id=event_id, actor_user_id=actor_user_id,
                recipient=recipient, kind=kind, source_id=source_id, depth=0,
                max_depth=0, requires_ack=True, ownership_changed=False,
                evidence=[], publication_approved=False)


def validate(conn, payload, agent, kind):
    """Revalidate at dispatch and immediately before inference; return context."""
    if not enabled():
        raise ValueError('ticket_event_wakes_disabled')
    if not isinstance(payload, dict) or payload.get('schema') != SCHEMA:
        raise ValueError('unauthenticated_legacy_event')
    if payload.get('recipient') != agent or payload.get('kind') != kind:
        raise ValueError('recipient_mismatch')
    if payload.get('depth') != 0 or payload.get('max_depth') != 0:
        raise ValueError('agent_chaining_unsupported')
    user = conn.execute('SELECT role,is_active FROM users WHERE id=?', (payload.get('actor_user_id'),)).fetchone()
    if not user or not user['is_active'] or user['role'] != 'admin':
        raise ValueError('actor_not_authorized')
    ctx = context(conn, payload.get('ticket_id'))
    for key, value in ctx.items():
        if payload.get(key) != value:
            raise ValueError('stale_ticket_context')
    expected = envelope(ctx, actor_user_id=payload['actor_user_id'], recipient=agent,
                        kind=kind, source_id=payload.get('source_id'))
    if payload.get('event_id') != expected['event_id']:
        raise ValueError('event_identity_mismatch')
    import re
    from pathlib import Path
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,99}', agent) or not (Path(__file__).resolve().parents[2] / '.claude/agents' / (agent + '.md')).is_file():
        raise ValueError('persona_unavailable')
    from internal_ticket_draft import is_restricted
    if is_restricted(ctx['ticket_id']):
        raise ValueError('restricted_ticket_event_unsupported')
    t = dict(conn.execute('SELECT * FROM tickets WHERE id=?', (ctx['ticket_id'],)).fetchone())
    if t.get('requires_human_approval') or t.get('approval_id'):
        raise ValueError('approval_gate')
    if ctx['status'] in ('blocked', 'resolved', 'closed'):
        raise ValueError('ticket_not_runnable')
    if kind == 'new_task':
        if ctx['owner'] != agent or ctx['status'] not in ('open', 'in_progress'):
            raise ValueError('work_owner_mismatch')
        if t.get('locked_at') or t.get('locked_by'):
            raise ValueError('ticket_locked')
    else:
        comment = conn.execute('SELECT ticket_id FROM ticket_comments WHERE id=?', (payload.get('source_id'),)).fetchone()
        if not comment or comment['ticket_id'] != ctx['ticket_id']:
            raise ValueError('comment_mismatch')
    return ctx


def acquire_work_lease(conn, payload, agent, run_id, timeout_seconds):
    """CAS before inference; caller retains token, ownership is never transferred."""
    import secrets
    from datetime import datetime, timezone
    token = secrets.token_urlsafe(32)
    conn.execute('BEGIN IMMEDIATE')
    try:
        ctx = validate(conn, payload, agent, 'new_task')
        now = datetime.now(timezone.utc).isoformat()
        changed = conn.execute("""UPDATE tickets SET locked_at=?,locked_by=?,lock_token=?,lock_timeout_seconds=?
            WHERE id=? AND company_id=? AND assignee_agent=? AND updated_at=?
              AND locked_at IS NULL AND locked_by IS NULL AND status IN ('open','in_progress')
              AND requires_human_approval=0 AND approval_id IS NULL""",
            (now, agent, token, max(1800, int(timeout_seconds)+120), ctx['ticket_id'], ctx['company_id'], agent, ctx['ticket_version'])).rowcount
        if changed != 1:
            raise ValueError('work_lease_conflict')
        conn.execute('INSERT INTO ticket_activity(id,ticket_id,actor,action,payload,created_at) VALUES(?,?,?,?,?,?)',
                     (str(uuid.uuid4()), ctx['ticket_id'], agent, 'checkout', json.dumps({'run_id':run_id,'event_id':payload['event_id'],'lease':'controller_owned'}), now))
        conn.commit()
        return token
    except BaseException:
        conn.rollback()
        raise


def release_work_lease(conn, ticket_id, agent, token):
    changed = conn.execute('UPDATE tickets SET locked_at=NULL,locked_by=NULL,lock_token=NULL WHERE id=? AND locked_by=? AND lock_token=?',
                          (ticket_id, agent, token)).rowcount
    conn.commit()
    return changed == 1


def apply_result(conn, payload, result, agent, run_id, lease_token, workspace):
    """Record observed evidence; review stays pending, never invoke an auto-reviewer."""
    from datetime import datetime, timezone
    from pathlib import Path
    from heartbeat_outcome import parse_agent_outcome
    if result.get('status') != 'success':
        return None
    spec = parse_agent_outcome(result.get('output'))
    if not spec or spec.get('action') not in ('work', 'skip', 'blocked'):
        raise ValueError('event_outcome_invalid')
    receipt = {'schema': SCHEMA, 'event_id': payload['event_id'], 'run_id': run_id,
               'ticket_id': payload['ticket_id'], 'ticket_version': payload['ticket_version'],
               'owner': payload['owner'], 'ownership_changed': False,
               'acknowledgement': 'not_recorded', 'review_status': 'pending_independent_review',
               'publication_approved': False, 'evidence': []}
    if payload['kind'] == 'mention':
        # The service principal may differ from the browser user who requested
        # the wake. Correlate by server-recorded idempotency key + actual actor.
        row = None
        cid = None
        for activity in conn.execute("SELECT payload FROM ticket_activity WHERE ticket_id=? AND action='commented' ORDER BY created_at DESC LIMIT 100", (payload['ticket_id'],)):
            detail = json.loads(activity['payload'] or '{}')
            if detail.get('wake_event_id') != payload['event_id']:
                continue
            expected = str(uuid.uuid5(uuid.NAMESPACE_URL,
                f"ticket-comment:{payload['ticket_id']}:{detail.get('actor_user_id')}:wake:{payload['event_id']}"))
            if detail.get('comment_id') != expected:
                continue
            cid = expected
            row = conn.execute('SELECT body,ticket_id FROM ticket_comments WHERE id=?', (cid,)).fetchone()
            if row and row['ticket_id'] == payload['ticket_id']:
                break
        if not row or row['ticket_id'] != payload['ticket_id']:
            raise ValueError('mention_comment_not_observed')
        receipt['evidence'] = [{'type':'ticket_comment', 'id':cid,
                                'sha256':hashlib.sha256(row['body'].encode()).hexdigest()}]
        return receipt
    if spec['action'] == 'skip':
        receipt['status'] = 'skip'
        return receipt
    evidence = spec.get('evidence')
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 10:
        raise ValueError('work_evidence_required')
    root = Path(workspace).resolve()
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {'ref', 'sha256'}:
            raise ValueError('invalid_work_evidence')
        path = (root / item['ref']).resolve(strict=True)
        path.relative_to(root)
        if not path.is_file() or not 0 < path.stat().st_size <= 262144:
            raise ValueError('invalid_work_evidence')
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha != item['sha256']:
            raise ValueError('work_evidence_hash_mismatch')
        receipt['evidence'].append({'ref':str(path.relative_to(root)), 'sha256':sha})
    target = 'blocked' if spec['action'] == 'blocked' else spec.get('new_status') or 'in_progress'
    if target not in ('in_progress', 'review', 'blocked') or spec.get('ticket_id') != payload['ticket_id']:
        raise ValueError('event_outcome_scope')
    now = datetime.now(timezone.utc).isoformat()
    conn.execute('BEGIN IMMEDIATE')
    try:
        actor = conn.execute('SELECT role,is_active FROM users WHERE id=?', (payload['actor_user_id'],)).fetchone()
        if not actor or not actor['is_active'] or actor['role'] != 'admin':
            raise ValueError('actor_revoked_before_result')
        current = context(conn, payload['ticket_id'])
        if any(current[key] != payload.get(key) for key in current):
            raise ValueError('event_context_changed_before_result')
        changed = conn.execute("""UPDATE tickets SET status=?,updated_at=?,blocked_reason=?
            WHERE id=? AND company_id=? AND assignee_agent=? AND lock_token=?
              AND locked_by=? AND updated_at=? AND status IN ('open','in_progress')
              AND requires_human_approval=0 AND approval_id IS NULL""",
            (target,now,'agent_blocked' if target=='blocked' else None,payload['ticket_id'],
             payload['company_id'],agent,lease_token,agent,payload['ticket_version'])).rowcount
        if changed != 1:
            raise ValueError('event_outcome_lease_or_gate_changed')
        comment_id = str(uuid.uuid5(uuid.NAMESPACE_URL,'ticket-event-outcome:'+run_id))
        summary = str(spec.get('result') or '')[:4000]
        conn.execute('INSERT INTO ticket_comments(id,ticket_id,author,body,mentions,created_at) VALUES(?,?,?,?,?,?)',
                     (comment_id,payload['ticket_id'],'controller:'+agent,summary,'[]',now))
        receipt.update(status=target,result_version=now,comment_id=comment_id)
        conn.execute('INSERT INTO ticket_activity(id,ticket_id,actor,action,payload,created_at) VALUES(?,?,?,?,?,?)',
                     (str(uuid.uuid5(uuid.NAMESPACE_URL,'ticket-event-receipt:'+run_id)),payload['ticket_id'],
                      'controller:'+agent,'ticket_event_result',json.dumps(receipt),now))
        conn.commit()
        return receipt
    except BaseException:
        conn.rollback()
        raise
