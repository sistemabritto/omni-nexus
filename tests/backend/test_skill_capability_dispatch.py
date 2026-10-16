"""Real local skill/file-adapter I/O, fake terminal HTTP. No external/model call."""
import hashlib
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"dashboard/backend"))
import pytest
from skill_capability_dispatch import dispatch_query
from tests.backend.test_live_file_sources import files,bind_file  # noqa:F401
from tests.backend.test_live_continuity_endpoints import enabled,bound,post  # noqa:F401
from tests.backend.test_managed_live_context import setup,ORIGIN  # noqa:F401

ROOT=Path(__file__).resolve().parents[2]
ROW={'id':1,'company_id':7,'user_id':31}


def test_query_selects_installed_skill_and_calls_adapter_without_plugin_name():
    calls=[]
    def read(row,terms):
        calls.append((row,terms))
        return {'status':'available','results':[{'path':'workspace/brand.md','text':'Marca original','sha256':'a'*64}]}
    result=dispatch_query('Quero uma thumbnail seguindo nossa marca',root=ROOT,row=ROW,read_files=read,verify_scope=lambda:True)
    assert result['status']=='context_ready'
    assert calls==[(ROW,['marca','identidade','brand'])]
    assert result['skills'][0]['name']=='mkt-creative-brief'
    content=(ROOT/'.claude/skills/mkt-creative-brief/SKILL.md').read_bytes()
    assert result['skills'][0]['sha256']==hashlib.sha256(content).hexdigest()
    assert result['skills'][0]['text']==content.decode()
    assert len(result['skills'][0]['documents'])==3
    assert result['external_call_status']=='not_attempted'
    assert result['model_read_status']=='not_attested'
    assert result['tools_list'][0]['effect']=='read'


def test_review_specificity_and_no_unrelated_skill_dump():
    result=dispatch_query('revisar thumbnail',root=ROOT,row=ROW,read_files=lambda *_:{'status':'available','results':[]},verify_scope=lambda:True)
    assert result['skills'][0]['name']=='mkt-brand-review'
    assert len(result['skills'])==1 and result['status']=='needs_authorized_brand_reference'
    result=dispatch_query('Qual o status do ticket?',root=ROOT,row=ROW,read_files=lambda *_:pytest.fail('unrelated read'),verify_scope=lambda:True)
    assert result['status']=='no_matching_binding' and not result['skills']


@pytest.mark.parametrize('mode',['no_tools','denied'])
def test_intentional_no_tools_and_denied_scope_never_call_adapter(mode):
    kwargs=dict(root=ROOT,row=ROW,read_files=lambda *_:pytest.fail('forbidden read'),verify_scope=lambda:mode!='denied')
    if mode=='denied':
        with pytest.raises(PermissionError):dispatch_query('thumbnail',**kwargs)
    else:
        result=dispatch_query('thumbnail',tool_policy='no_tools',**kwargs)
        assert result['reason']=='intentional_no_tools' and not result['skills']


@pytest.mark.parametrize('issue',['missing','symlink','secret','budget'])
def test_unavailable_skill_fails_before_adapter(tmp_path,issue):
    path=tmp_path/'.claude/skills/mkt-creative-brief/SKILL.md';path.parent.mkdir(parents=True)
    if issue=='symlink':path.symlink_to(ROOT/'.claude/skills/mkt-creative-brief/SKILL.md')
    if issue=='secret':path.write_text('api_key = sk-'+'X'*30)
    if issue=='budget':path.write_text('x'*25000)
    result=dispatch_query('thumbnail',root=tmp_path,row=ROW,read_files=lambda *_:pytest.fail('unavailable skill cannot execute'),verify_scope=lambda:True)
    assert result['status']=='blocked' and not result['execution']


def test_scope_revocation_during_read_drops_result():
    states=iter([True,True,False])
    with pytest.raises(PermissionError):
        dispatch_query('thumbnail',root=ROOT,row=ROW,read_files=lambda *_:{'status':'available','results':[]},verify_scope=lambda:next(states))


def test_real_query_route_uses_existing_file_adapter_and_owned_company(files,monkeypatch):
    fixture,_,save=files;app,c,_,mod,_,_=fixture
    # Static authorial skill comes from checkout; file refs remain tmp and ACLed.
    monkeypatch.setattr(mod,'WORKSPACE',ROOT)
    path,file=save('brand.md','Marca aprovada: cor azul. Identidade fixture, não comercial.')
    ctx=bound(c);binding=bind_file(c,ctx,path)
    result=post(c,ctx,'query',query='Quero criar uma thumbnail')
    assert result.status_code==200,result.json
    cap=result.json['capabilities']
    assert cap['status']=='context_ready'
    assert cap['references'][0]['sha256']==hashlib.sha256(file.read_bytes()).hexdigest()
    assert cap['execution']['status']=='completed'
    from tests.backend.test_managed_live_context import read
    import json
    post(c,ctx,'transcript',eventId='thumbnail-question',role='user',text='Quero criar uma thumbnail')
    delivered=read(c,ctx['contextId'],'provider-a')
    assert delivered.status_code==200,delivered.json
    assert delivered.json['queryResult']['capabilities']['selected']=='creative-brand-context'
    assert len(json.dumps(delivered.json,ensure_ascii=False))<24000
    digest=cap['execution']['receipt_sha256']
    with sqlite3.connect(app.config['NEXUS_LIVE_CONTEXT_DB']) as conn:
        row=conn.execute('SELECT user_id,company_id,adapter FROM skill_capability_receipts WHERE id=?',(digest,)).fetchone()
        assert row==(31,7,'authorized_brand_references')
    again=post(c,ctx,'query',query='Quero criar uma thumbnail').json['capabilities']
    assert again['execution']['receipt_sha256']==digest
    other=bound(c,company=8,connection='provider-b')
    assert post(c,other,'query','provider-b',query='thumbnail').json['capabilities']['references']==[]
    assert post(c,ctx,'query','foreign-conversation',query='thumbnail').status_code==403
    assert post(c,ctx,'file-sources/revoke',id=binding['id'],expectedRevision=1).status_code==200
    assert post(c,ctx,'query',query='thumbnail').json['capabilities']['status']=='needs_authorized_brand_reference'


def test_transport_budget_never_silently_truncates_skill():
    from skill_capability_dispatch import fit_context_budget
    packet=dispatch_query('thumbnail',root=ROOT,row=ROW,read_files=lambda *_:{'status':'available','results':[]},verify_scope=lambda:True)
    fitted=fit_context_budget({'other_context':'x'*15000},packet)
    assert fitted['status']=='blocked' and fitted['skills']==[]
    assert fitted['reason']=='transport_budget_requires_narrow_context'
