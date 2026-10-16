"""Controller-owned, text-only pilot. No model-provided paths, actions or outcomes.

The exact ID allowlist is code reviewed; ticket prose cannot grant capabilities.
This module never enables a heartbeat or changes provider configuration.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

PILOT_ID = 'dcf84bb2-062d-5484-b940-786eebcd1e5d'
PILOT_AGENT = 'pixel-social-media'
MARKER = '[reports-20261016-v1:EDIT-07]'
MAX_DRAFT_BYTES = 64_000


def is_restricted(ticket_id):
    return ticket_id == PILOT_ID


def _now():
    return datetime.now(timezone.utc).isoformat()


def _activity(conn, ticket_id, action, payload):
    conn.execute('INSERT INTO ticket_activity (id,ticket_id,actor,action,payload,created_at) VALUES (?,?,?,?,?,?)',
                 (str(uuid.uuid4()), ticket_id, 'controller:internal-draft', action,
                  json.dumps(payload, ensure_ascii=False), _now()))


def restricted_candidate(conn, agent):
    """Read independently of inbox limits, so protected prose never goes generic."""
    if agent != PILOT_AGENT:
        return None
    row = conn.execute('SELECT * FROM tickets WHERE id=? AND assignee_agent=? AND status=\'open\' AND locked_at IS NULL',
                       (PILOT_ID, agent)).fetchone()
    return dict(row) if row else None


def _save_draft(root, ticket_id, run_id, content):
    """Use directory FDs and O_NOFOLLOW, never a path returned by the model."""
    # root is supplied only by the controller, never by ticket text.
    root = Path(root)
    base = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in ('internal-drafts', str(uuid.UUID(ticket_id))):
            try:
                os.mkdir(name, mode=0o700, dir_fd=base)
            except FileExistsError:
                pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
            os.close(base)
            base = child
        name = str(uuid.UUID(run_id)) + '.md'
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=base)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return f'internal-drafts/{ticket_id}/{name}'
    finally:
        os.close(base)


def run_draft(conn, ticket, agent, run_id, root, *, invoke=None):
    """One bounded invocation; failure parks only this ticket with specific cause.

    The model gets a fixed hypothetical brief, no inbox/persona/credentials or
    user-controlled description. Its output is inert Markdown, never parsed as
    a heartbeat outcome. State and artifact metadata are controller generated.
    """
    if (ticket['id'] != PILOT_ID or agent != PILOT_AGENT
            or ticket.get('company_id') != 1 or MARKER not in (ticket.get('description') or '')
            or ticket.get('approval_id') is not None or ticket.get('requires_human_approval')):
        raise ValueError('restricted_ticket_contract_mismatch')
    uuid.UUID(run_id)
    checkout_at = _now()
    cur = conn.execute('''UPDATE tickets SET locked_at=?,locked_by=?,lock_timeout_seconds=900
        WHERE id=? AND assignee_agent=? AND company_id=1 AND status='open'
        AND updated_at=? AND description=? AND locked_at IS NULL
        AND approval_id IS NULL AND requires_human_approval=0''',
        (checkout_at, agent, PILOT_ID, agent, ticket['updated_at'], ticket['description']))
    if cur.rowcount != 1:
        conn.rollback()
        return {'status': 'fail', 'error': 'restricted_checkout_conflict', 'output': '', 'agent': agent}
    _activity(conn, PILOT_ID, 'checkout', {'run_id': run_id, 'tool_policy': 'no_tools'})
    conn.commit()
    prompt = '''Escreva em português um RASCUNHO INTERNO HIPOTÉTICO para um artigo
sobre medir resultado de chatbot. Comece com "RASCUNHO — EXEMPLO HIPOTÉTICO".
Use dados inteiramente fictícios e identifique-os como hipótese, nunca como caso
real. Inclua período, população/denominadores, definição de resolução, retrabalho,
custo e um exemplo de cálculo consistente, com limitações. Não alegue que 3
pageviews tornam um tema vencedor. Não use ferramentas, internet, CRM, Ghost,
publicação, mensagens, geração de mídia ou arquivos. Não peça permissões ou
credenciais. Retorne somente o texto Markdown do rascunho, sem ações ou JSON.'''
    result = {}
    artifact = None
    try:
        if invoke is None:
            from provider_fallback import invoke_with_fallback
            invoke = invoke_with_fallback
        # Do not use step7_invoke_claude: its legacy native fallback has tools.
        # ContextVar policy covers every configured provider/model fallback.
        result = invoke(prompt=prompt, max_turns=1, timeout_seconds=120,
                        per_attempt_timeout_cap=45, agent='', routing_key=agent,
                        tool_policy='no_tools')
        if result.get('status') != 'success':
            # Expose actionable adapter gates, never raw provider output/secrets.
            code = result.get('error')
            safe_codes = {'restricted_adapter_unsupported', 'restricted_managed_config_present',
                          'restricted_ancestor_config_present', 'restricted_explicit_provider_required',
                          'restricted_text_result_required'}
            raise RuntimeError(code if code in safe_codes else 'restricted_provider_failed')
        text = result.get('output')
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > MAX_DRAFT_BYTES:
            raise ValueError('restricted_invalid_draft')
        # Explicit hypothesis is mandatory, even when the provider claims success.
        if not text.lstrip().startswith('RASCUNHO — EXEMPLO HIPOTÉTICO'):
            raise ValueError('restricted_hypothesis_label_missing')
        # Recheck while holding SQLite's writer transaction before creating file.
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM tickets WHERE id=?', (PILOT_ID,)).fetchone()
        if (not row or row['status'] != 'open' or row['locked_by'] != agent
                or row['locked_at'] != checkout_at or row['company_id'] != 1
                or row['approval_id'] is not None or row['requires_human_approval']
                or row['assignee_agent'] != agent or row['updated_at'] != ticket['updated_at']
                or row['description'] != ticket['description']):
            raise RuntimeError('restricted_completion_conflict')
        artifact = _save_draft(root, PILOT_ID, run_id, text)
        sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
        conn.execute("UPDATE tickets SET status='review',blocked_reason=NULL,locked_at=NULL,locked_by=NULL,updated_at=? WHERE id=?", (_now(), PILOT_ID))
        _activity(conn, PILOT_ID, 'internal_draft_ready', {'run_id': run_id, 'artifact': artifact,
            'sha256': sha, 'bytes': len(text.encode('utf-8')), 'tool_policy': 'no_tools',
            'human_publication_approval': False})
        conn.commit()
        return {**result, 'output': '', 'agent': agent, 'internal_draft': artifact, 'sha256': sha}
    except Exception as exc:
        conn.rollback()
        # Never overwrite a human edit or another checkout on error.
        cur = conn.execute("""UPDATE tickets SET status='blocked',blocked_reason='internal_draft_failed',
            locked_at=NULL,locked_by=NULL,updated_at=? WHERE id=? AND status='open'
            AND locked_by=? AND locked_at=? AND assignee_agent=? AND updated_at=? AND description=?
            AND company_id=1 AND approval_id IS NULL AND requires_human_approval=0""",
            (_now(), PILOT_ID, agent, checkout_at, agent, ticket['updated_at'], ticket['description']))
        if cur.rowcount:
            _activity(conn, PILOT_ID, 'internal_draft_failed', {'run_id': run_id, 'reason': str(exc),
                'tool_policy': 'no_tools', 'orphan_artifact': artifact})
        conn.commit()
        return {'status': 'fail', 'error': str(exc), 'output': '', 'agent': agent}
