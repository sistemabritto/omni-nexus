import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('gambito_builder',ROOT/'scripts/build_gambito_editorial_v4.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

def test_complete_drafts_and_reward_links(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'OUT',tmp_path)
    builder.build('https://nexus.sistemabritto.com.br/share/test-token')
    records=json.loads((tmp_path/'gambito-v4-inventory.json').read_text())
    assert len(records)==35
    assert len({r['id'] for r in records})==35
    for row in records:
        assert len(row['hooks'])==2 and all(row['hooks'])
        assert row['status']=='draft_review'
        assert row['campaign_id'] is None and row['media_id'] is None
        assert 'NÃO VALIDADO' in row['openreply_prompt']
        assert 'media_id=PENDENTE' in row['openreply_prompt']
        if row['reward']!='LASER':
            assert '/api/shares/test-token/view?' in row['url']
            assert row['url'].endswith('#'+row['reward'])
            assert f'id="{row["reward"]}"' in (tmp_path/'caderno-gambito-v4.html').read_text()
    for artifact in tmp_path.glob('*.html'):
        text=artifact.read_text()
        assert '<script' not in text
        assert 'prefers-color-scheme:dark' in text
    assert '/api/shares/test-token/click?' in (tmp_path/'caderno-gambito-v4.html').read_text()

def test_monitor_uses_real_approval_schema(tmp_path,monkeypatch):
    import sqlite3
    import sys
    from datetime import datetime,timezone
    sys.path.insert(0,str(ROOT/'dashboard/backend'))
    import reels_producer
    db=tmp_path/'runtime.db'
    with sqlite3.connect(db) as conn:
        conn.executescript('CREATE TABLE heartbeats(id TEXT, interval_seconds INTEGER, enabled INTEGER); CREATE TABLE heartbeat_runs(run_id TEXT, heartbeat_id TEXT, status TEXT, started_at TEXT); CREATE TABLE pending_approvals(status TEXT); INSERT INTO pending_approvals VALUES ("pending"),("approved");')
    monkeypatch.setattr(reels_producer,'DB',db)
    monkeypatch.setattr(reels_producer,'REPORTS',tmp_path)
    monkeypatch.setattr(reels_producer,'GROWTH',tmp_path/'absent.json')
    report=reels_producer.inspect(datetime(2026,9,10,tzinfo=timezone.utc))
    assert report['pending_approvals_all_workflows']==1
    assert 'Banco operacional indisponível' not in report['issues']
