"""Documented nullable provider metadata, no provider calls or permission changes."""
import ast
import re
import types
from pathlib import Path
import pytest

# Compile the real pure functions without importing routes/models at collection.
# Other integration fixtures rebuild SQLAlchemy registries; holding an old route
# module here keeps stale weak-reference mappers alive in the combined suite.
_source = Path(__file__).resolve().parents[2] / 'dashboard/backend/routes/live_voices.py'
_nodes = [node for node in ast.parse(_source.read_text()).body
          if isinstance(node, (ast.FunctionDef, ast.ClassDef))
          and node.name in {'VoiceUnavailable', '_eligible', '_voice'}]
mod = types.ModuleType('real_voice_metadata_functions')
mod._ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
mod._get = lambda *_args, **_kwargs: None
exec(compile(ast.Module(body=_nodes, type_ignores=[]), str(_source), 'exec'), mod.__dict__)
_eligible = mod._eligible

@pytest.mark.parametrize('category,access', [('premade', {}),('cloned', {'is_owner':True}),('generated', {'permission_on_resource':'viewer'})])
@pytest.mark.parametrize('safety', [None,'NONE'])
def test_documented_nullable_safety_is_not_a_ban(category,access,safety):
    assert _eligible(dict(category=category,safety_control=safety,**access),'fixture-model')

@pytest.mark.parametrize('safety', ['BAN','CAPTCHA','ENTERPRISE_BAN','ENTERPRISE_CAPTCHA','unknown',''])
def test_real_or_unknown_controls_remain_blocked(safety):
    assert not _eligible(dict(category='premade',safety_control=safety),'fixture-model')


def test_nullable_safety_does_not_grant_access_or_skip_verification_or_fine_tuning():
    assert not _eligible(dict(category='cloned',safety_control=None),'fixture-model')
    assert not _eligible(dict(category='premade',safety_control=None,voice_verification={'requires_verification':True,'is_verified':False}),'fixture-model')
    base=dict(category='professional',is_owner=True,safety_control=None)
    for fine_tuning in (None,{}, {'state':None},{'state':{'other-model':'fine_tuned'}}):
        assert not _eligible({**base,'fine_tuning':fine_tuning},'fixture-model')
    assert _eligible({**base,'fine_tuning':{'state':{'fixture-model':'fine_tuned'}}},'fixture-model')


def test_detail_can_use_verified_same_account_listing_permission(monkeypatch):
    listing=dict(voice_id='shared_fixture',category='professional',permission_on_resource='viewer',is_owner=False,safety_control=None,fine_tuning={'state':{'fixture-model':'fine_tuned'}})
    detail={**listing,'permission_on_resource':None,'is_owner':None}
    def get(path,**kw):return {'voices':[listing]} if path=='/v2/voices' else detail
    monkeypatch.setattr(mod,'_get',get)
    result=mod._voice('shared_fixture','fixture-model')
    assert result['permission_on_resource']=='viewer'
    assert detail['permission_on_resource'] is None  # Never mutate provider evidence.
    detail['permission_on_resource']='denied'
    with pytest.raises(mod.VoiceUnavailable):mod._voice('shared_fixture','fixture-model')
    detail['permission_on_resource']=None;detail['safety_control']='BAN'
    with pytest.raises(mod.VoiceUnavailable):mod._voice('shared_fixture','fixture-model')
    detail['safety_control']=None;listing['safety_control']='CAPTCHA'
    with pytest.raises(mod.VoiceUnavailable):mod._voice('shared_fixture','fixture-model')
    listing['safety_control']=None;listing['voice_id']='different_fixture'
    with pytest.raises(mod.VoiceUnavailable):mod._voice('shared_fixture','fixture-model')


def test_detail_still_requires_own_model_training(monkeypatch):
    listing=dict(voice_id='shared_fixture',category='professional',permission_on_resource='admin',safety_control=None,fine_tuning={'state':{'fixture-model':'fine_tuned'}})
    detail={**listing,'permission_on_resource':None,'fine_tuning':{'state':{'other-model':'fine_tuned'}}}
    monkeypatch.setattr(mod,'_get',lambda path,**kw:{'voices':[listing]} if path=='/v2/voices' else detail)
    with pytest.raises(mod.VoiceUnavailable):mod._voice('shared_fixture','fixture-model')
