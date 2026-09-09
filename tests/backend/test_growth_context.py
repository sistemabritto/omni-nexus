import json,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'dashboard/backend'))
from growth_context import load_context

def test_missing_evidence_does_not_fabricate_metrics(tmp_path,monkeypatch):
    monkeypatch.setenv('GROWTH_EVIDENCE_PATH',str(tmp_path/'missing'))
    assert 'indisponível' in load_context()

def test_stale_evidence_is_explicit(tmp_path,monkeypatch):
    p=tmp_path/'report.json';p.write_text(json.dumps({'collected_at':(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()}))
    monkeypatch.setenv('GROWTH_EVIDENCE_PATH',str(p))
    assert 'desatualizado' in load_context()
