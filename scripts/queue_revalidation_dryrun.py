"""Read-only proposals for ten audited queue cases. No apply mode exists."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

NEX = ('de0fac29','8aa7bb62','c9ce0445','6651faa4','689037b5')
BOLT = ('c6851c4a','e16320ff','8717ebe0')
INTERNAL = ('e63b4871',)
PROTECTED = '5de37020'


def plan(conn, root):
    conn.row_factory = sqlite3.Row
    proposals = []
    for prefix in NEX + BOLT + INTERNAL + (PROTECTED,):
        rows = conn.execute('SELECT * FROM tickets WHERE id LIKE ? ORDER BY id', (prefix+'%',)).fetchall()
        if len(rows) != 1:
            proposals.append({'case': prefix, 'decision': 'identity_missing_or_ambiguous', 'proposed': None})
            continue
        t = dict(rows[0])
        expected = {k:t.get(k) for k in ('status','assignee_agent','blocked_reason','updated_at','requires_human_approval','approval_id','locked_by','locked_at')}
        item = {'ticket_id':t['id'], 'expected':expected, 'proposed':None,
                'job_restart':False, 'manual_review_required':True, 'evidence':{}}
        if prefix == PROTECTED:
            item['decision'] = 'protected_explicit_decision_only'
        elif (t['status'] != 'blocked' or t.get('locked_by') or t.get('locked_at') or t.get('approval_id') is not None
              or t.get('requires_human_approval')):
            item['decision'] = 'state_or_human_gate_changed_no_proposal'
        elif prefix in NEX:
            active = bool(conn.execute("SELECT 1 FROM heartbeats WHERE agent='nex-sales' AND enabled=1 LIMIT 1").fetchone())
            last = conn.execute('SELECT body FROM ticket_comments WHERE ticket_id=? ORDER BY created_at DESC LIMIT 1',(t['id'],)).fetchone()
            offline = bool(last and any(w in last[0].lower() for w in ('sem heartbeat','no heartbeat','não há heartbeat')))
            item['evidence'] = {'enabled_heartbeat':active, 'latest_comment_reports_offline':offline,
                                'delivery_proven':False}
            item['decision'] = 'offline_premise_obsolete' if active and offline else 'evidence_not_sufficient'
            if active and offline and t['assignee_agent']=='nex-sales':
                item['proposed'] = {'blocked_reason':'needs_current_funnel_evidence'}
        elif prefix in BOLT:
            goal = conn.execute('SELECT decomposition_state FROM goals WHERE id=?',(t.get('goal_id'),)).fetchone()
            rejected = bool(goal and goal[0]=='rejected')
            item['evidence'] = {'decomposition_rejected':rejected, 'deployment_or_acceptance_proven':False}
            item['decision'] = 'scope_decision_before_code_execution'
            if t['assignee_agent']=='bolt-executor':
                item['proposed'] = {'blocked_reason':'scope_review_required' if rejected else 'code_evidence_required'}
        else:
            path = Path(root)/'workspace/marketing/[C]oferta-setup-anual-whatsapp-preco-beneficios-2026-10-07.md'
            real = path.resolve()
            inside = real.is_relative_to((Path(root)/'workspace').resolve())
            exists = inside and real.is_file()
            text = real.read_text() if exists else ''
            decision = all(word in text for word in ('Sprint 5','Felipe','Lex'))
            item['evidence'] = {'internal_artifact_exists':exists,
                'sha256':hashlib.sha256(real.read_bytes()).hexdigest() if exists else None,
                'business_decisions_pending':decision}
            item['decision'] = 'commercial_decision_not_publication_retry'
            if decision and t['assignee_agent']=='mako-marketing':
                item['proposed'] = {'blocked_reason':'commercial_decision_required'}
        proposals.append(item)
    return {'mode':'read_only_dry_run','apply_supported':False,'proposals':proposals}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    args=p.parse_args()
    with sqlite3.connect(f'file:{args.db}?mode=ro',uri=True) as conn:
        conn.execute('PRAGMA query_only=ON')
        print(json.dumps(plan(conn,args.root),ensure_ascii=False,indent=2))
