import importlib.util
from pathlib import Path
import sqlite3
import pytest
spec=importlib.util.spec_from_file_location('dryrun',Path(__file__).resolve().parents[1]/'scripts/queue_revalidation_dryrun.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@pytest.fixture
def case(tmp_path):
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
 c.executescript('''CREATE TABLE tickets(id TEXT,status TEXT,assignee_agent TEXT,blocked_reason TEXT,updated_at TEXT,requires_human_approval INTEGER,approval_id INTEGER,locked_at TEXT,goal_id INTEGER); CREATE TABLE heartbeats(id TEXT,agent TEXT,enabled INTEGER); CREATE TABLE ticket_comments(ticket_id TEXT,body TEXT,created_at TEXT); CREATE TABLE goals(id INTEGER,decomposition_state TEXT); INSERT INTO heartbeats VALUES('nex','nex-sales',1); INSERT INTO goals VALUES(9,'rejected');''')
 for prefix in m.NEX+m.BOLT+m.INTERNAL+(m.PROTECTED,):
  agent='nex-sales' if prefix in m.NEX else 'bolt-executor' if prefix in m.BOLT else 'mako-marketing'
  c.execute('INSERT INTO tickets VALUES(?,?,?,?,?,0,NULL,NULL,9)',(prefix+'-fixture','blocked',agent,None,'old'))
  c.execute('INSERT INTO ticket_comments VALUES(?,?,?)',(prefix+'-fixture','Agent offline (no heartbeat)','old'))
 p=tmp_path/'workspace/marketing/[C]oferta-setup-anual-whatsapp-preco-beneficios-2026-10-07.md';p.parent.mkdir(parents=True);p.write_text('Sprint 5 Felipe Lex')
 c.commit();c.execute('PRAGMA query_only=ON')
 yield c,tmp_path;c.close()


def test_plan_is_readonly_idempotent_and_never_reopens_or_reassigns(case):
 c,p=case;before=c.total_changes;a=m.plan(c,p);assert m.plan(c,p)==a;assert c.total_changes==before
 assert a['apply_supported'] is False
 assert len(a['proposals'])==10
 for r in a['proposals']:
  assert r['job_restart'] is False
  assert r['manual_review_required'] is True
  assert r['proposed'] is None or set(r['proposed'])=={'blocked_reason'}
 protected=a['proposals'][-1];assert protected['proposed'] is None
 assert all(r['decision']=='offline_premise_obsolete' for r in a['proposals'][:5])
 assert a['proposals'][-2]['proposed']=={'blocked_reason':'commercial_decision_required'}

@pytest.mark.parametrize('column,value',[('status','resolved'),('requires_human_approval',1),('approval_id',4),('locked_at','lock')])
def test_changed_state_or_gate_prevents_proposal(case,column,value):
 c,p=case;c.execute('PRAGMA query_only=OFF');c.execute(f'UPDATE tickets SET {column}=? WHERE id=?',(value,m.NEX[0]+'-fixture'));c.commit();c.execute('PRAGMA query_only=ON')
 assert m.plan(c,p)['proposals'][0]['proposed'] is None


def test_disabled_heartbeat_is_not_proposed_for_reenable(case):
 c,p=case;c.execute('PRAGMA query_only=OFF');c.execute('UPDATE heartbeats SET enabled=0');c.commit();c.execute('PRAGMA query_only=ON')
 assert all(r['proposed'] is None for r in m.plan(c,p)['proposals'][:5])


def test_cli_has_no_apply_mode(tmp_path):
 import subprocess,sys
 result=subprocess.run([sys.executable,str(Path(m.__file__)), '--db', str(tmp_path/'missing.db'), '--root', str(tmp_path), '--apply'],capture_output=True,text=True)
 assert result.returncode==2
 assert 'unrecognized arguments: --apply' in result.stderr
 assert not (tmp_path/'missing.db').exists()


def test_new_evidence_and_ambiguous_identity_produce_no_offline_proposal(case):
 c,p=case;c.execute('PRAGMA query_only=OFF');c.execute('UPDATE ticket_comments SET body=? WHERE ticket_id=?',('Delivered for review',m.NEX[0]+'-fixture'))
 c.execute('INSERT INTO tickets SELECT ?,status,assignee_agent,blocked_reason,updated_at,requires_human_approval,approval_id,locked_at,goal_id FROM tickets WHERE id=?',(m.NEX[1]+'-other',m.NEX[1]+'-fixture'));c.commit();c.execute('PRAGMA query_only=ON')
 rows=m.plan(c,p)['proposals']
 assert rows[0]['proposed'] is None
 assert rows[1]['decision']=='identity_missing_or_ambiguous'
