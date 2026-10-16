"""Work-specific review routing, without provider/queue calls."""
import pytest
from squad_work_policy import ENTRY_POINTS, work_policy, reviewer_candidates


def test_six_entry_points_and_central_quality_not_fixed_eighteen():
    assert len(ENTRY_POINTS)==6 and len(set(ENTRY_POINTS.values()))==6
    for front in ENTRY_POINTS:
        p=work_policy(front)
        assert p['quality_coordinator']=='oath-verifier'
        assert p['assignment']=='per_work_not_fixed_trio'
        assert not p['dispatch_enforced_here']
        assert p['producer_wip_limit']==1 and p['correction_cycle_limit']==2
        assert p['legacy_goal_tasks']=='frozen_not_new_work'
    assert 'nex-sales' in work_policy('strategy')['specialists']
    assert 'dex-data' in work_policy('strategy')['specialists']
    assert 'helm-conductor' in work_policy('engineering')['specialists']


def test_no_self_review_or_unknown_access_or_unknown_capacity():
    assert reviewer_candidates('engineering',contributors={'lens-reviewer'},
        authorized_available={'lens-reviewer','vault-security','oath-verifier'},
        active_work={'lens-reviewer':0,'vault-security':1})==[]
    assert reviewer_candidates('engineering',contributors={'bolt-executor'},
        authorized_available={'lens-reviewer'}, active_work={'lens-reviewer':0})==['lens-reviewer']
    assert reviewer_candidates('quality',contributors={'raven-critic'},
        authorized_available={'raven-critic','probe-qa'},active_work={'raven-critic':0,'probe-qa':0})==['probe-qa']
    assert reviewer_candidates('visual',contributors=set(),
        authorized_available={'oath-verifier'},active_work={'oath-verifier':False})==[]


def test_no_mutable_policy_shared_or_unknown_front():
    p=work_policy('strategy');p['specialists'].clear()
    assert work_policy('strategy')['specialists']
    with pytest.raises(ValueError):work_policy('new_agent')
