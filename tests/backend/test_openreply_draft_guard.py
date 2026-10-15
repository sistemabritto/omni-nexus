"""No network/DB: generated creative must not enable external messages."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
import reels_copilot as rc

class Connection:
    def __init__(self, fail=False): self.fail=fail; self.calls=[]; self.committed=False; self.rolled_back=False; self.closed=False
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params):
        if self.fail: raise RuntimeError('private-password-in-driver-error')
        self.calls.append((sql,params))
    def commit(self): self.committed=True
    def rollback(self): self.rolled_back=True
    def close(self): self.closed=True


def test_generated_campaign_cannot_send_even_if_row_claims_activation(monkeypatch):
    db=Connection();monkeypatch.setattr(rc,'_openreply_pg_connect',lambda:db)
    result=rc.create_openreply_campaign({'seq':15,'bait_text':'guide','isActive':True,'activation_authorized':True})
    assert result['status']=='draft' and result['activation_required'] and result['delivery_link_required']
    assert len(db.calls)==1 and db.committed and db.closed
    sql,params=db.calls[0]
    fields=re.findall(r'"([A-Za-z]+)"',sql.split('VALUES')[0])[1:]
    row=dict(zip(fields,params))
    assert not row['isActive'] and not row['dmTriggerEnabled'] and not row['publicReplyEnabled']
    assert not row['reportShareEnabled']
    assert row['pendingNextReel'] and row['keywords']==['15']
    assert '@{username}' in row['publicReplyMessages'][0]
    assert "AT TIME ZONE 'UTC'" in sql
    assert 'UPDATE' not in sql and 'TrackedLink' not in sql


def test_database_failure_rolls_back_without_disclosing_driver_error(monkeypatch):
    db=Connection(fail=True);monkeypatch.setattr(rc,'_openreply_pg_connect',lambda:db)
    result=rc.create_openreply_campaign({'seq':2})
    assert result=={'ok':False,'status':'failed','error':'openreply_draft_creation_failed'}
    assert db.rolled_back and db.closed and not db.committed
    assert 'private-password' not in str(result)


def test_unconfigured_access_does_not_claim_draft_created(monkeypatch):
    monkeypatch.setattr(rc,'_openreply_pg_connect',lambda:None)
    result=rc.create_openreply_campaign({'seq':3})
    assert not result['ok'] and result['status']=='failed'
