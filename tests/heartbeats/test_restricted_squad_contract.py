"""Actual restricted controller consumes squad roles before any mocked inference."""
import json
from pathlib import Path
import pytest
import restricted_squad_contract as contract
from tests.heartbeats.test_internal_ticket_draft import db, run, success


def test_preflight_resolves_real_roles_and_local_methods_without_provider():
    proof=contract.preflight_contract('pixel-social-media')
    assert (proof['responsible'],proof['assistant'],proof['reviewer']) == contract.ACTORS
    assert proof['tool_policy']=='no_tools' and proof['providerAvailability']=='not_probed'
    assert proof['reviewStatus']=='required_not_started' and proof['methodHashes']


def test_runtime_contract_precedes_inference_and_binds_real_artifact(db,tmp_path):
    def invoke(**kw):
        audit=json.loads(db.execute("SELECT payload FROM ticket_activity WHERE action='internal_draft_contract_validated'").fetchone()[0])
        assert audit['squad']['version']==contract.VERSION
        assert audit['squad']['reviewer']=='oath-verifier'
        return success(**kw)
    result=run(db,tmp_path,invoke)
    handoff=result['delivery_handoff']
    assert handoff['artifactSha256']==result['sha256']
    assert handoff['reviewStatus']=='pending_independent_review'
    assert handoff['semanticAcceptance']=='not_verified' and handoff['acknowledgement']=='not_recorded'
    assert handoff['dispatchAllowed'] is False and handoff['publicationApproved'] is False
    assert handoff['ownershipChanged'] is False
    assert db.execute('SELECT assignee_agent,status FROM tickets').fetchone()[:]==('pixel-social-media','review')


@pytest.mark.parametrize('failure', ['missing_method','reviewer_is_author','role_drift'])
def test_preflight_failure_parks_only_pilot_before_any_model(db,tmp_path,monkeypatch,failure):
    if failure=='missing_method': monkeypatch.setattr(contract,'ROOT',tmp_path)
    else:
        roles=list(contract.FRONTS['editorial'])
        roles[3 if failure=='reviewer_is_author' else 2]='pixel-social-media'
        monkeypatch.setitem(contract.FRONTS,'editorial',tuple(roles))
    calls=[]
    result=run(db,tmp_path,lambda **kw:calls.append(kw))
    assert not calls and result['status']=='fail'
    assert result['error'].startswith('restricted_squad_')
    assert result['diagnostics']['failure_stage']=='squad_preflight'
    assert db.execute('SELECT status,locked_by FROM tickets').fetchone()[:]==('blocked',None)
    assert not list(tmp_path.iterdir())


def test_method_change_during_inference_cannot_commit_artifact(db,tmp_path,monkeypatch):
    original=contract.preflight_contract('pixel-social-media')
    methods=tmp_path/'methods';methods.mkdir()
    for ref in original['methodHashes']:
        path=methods/ref;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('# Trusted fixture method')
    monkeypatch.setattr(contract,'ROOT',methods)
    def invoke(**kw):
        (methods/'.claude/skills/dev-team-methods/handoff.md').write_text('# Changed fixture method')
        return success(**kw)
    result=run(db,tmp_path,invoke)
    assert result['error']=='restricted_squad_changed'
    assert result['diagnostics']['failure_stage']=='squad_revalidation'
    assert not (tmp_path/'internal-drafts').exists()
    assert db.execute('SELECT status,locked_by FROM tickets').fetchone()[:]==('blocked',None)
