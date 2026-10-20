"""New adapter contracts, real Live approval routes; native effects are synthetic."""
import json
import pytest
from tests.backend.test_live_experience import experience,call
from tests.backend.test_managed_live_context import setup,ORIGIN


@pytest.fixture
def adapters(experience,tmp_path,monkeypatch):
    import live_adapters as mod
    app,c,_,_,ctx,_=experience
    policy=tmp_path/'adapters.json'
    policy.write_text(json.dumps({'version':1,'bindings':[{'companyId':7,'userId':31,
        'workspaceAdministration':True}],'routineExecutors':['daily_status_report.py']}))
    monkeypatch.setattr(mod,'POLICY',policy)
    effects=[]
    def native(method,path,body=None,params=None):
        if method=='GET':return {'id':'example','enabled':False,'name':'Existing','revision':1}
        effects.append((method,path,body));return {'id':'new-id','status':'saved'}
    monkeypatch.setattr(mod,'native',native)
    return mod,app,c,ctx,effects


def operate(c,ctx,adapter,operation,args,key='adapter-1'):
    return call(c,ctx,'adapter_action',{'adapter':adapter,'operation':operation,
        'argumentsJson':json.dumps(args)},key)


def approve(c,ctx,result):
    return c.post(f"/api/live/omni-context/{ctx['contextId']}/approvals",json={
        'conversationId':'conv-fixture','approvalId':result.json['approvalId'],'decision':'approve'},headers=ORIGIN)


def test_routine_creation_is_reviewed_disabled_and_reloaded(adapters):
    _,_,c,ctx,effects=adapters
    result=operate(c,ctx,'routines','create',{'name':'Relatório','script':'daily_status_report.py',
        'frequency':'daily','time':'09:00'})
    assert result.status_code==200 and result.json['approvalRequired'] and not effects
    applied=approve(c,ctx,result)
    assert applied.status_code==200 and applied.json['status']=='success'
    assert effects[0][0:2]==('POST','/api/settings/routines')
    assert effects[0][2]['enabled'] is False
    assert effects[1][1]=='/api/settings/scheduler/reload'
    assert approve(c,ctx,result).status_code==409


def test_global_admin_scope_and_credentials_are_not_inferred(adapters,monkeypatch):
    mod,_,c,ctx,effects=adapters
    mod.POLICY.write_text('{"version":1,"bindings":[]}')
    assert operate(c,ctx,'heartbeats','update',{'identifier':'existing','changes':{'enabled':False}}).status_code==403
    assert not effects


@pytest.mark.parametrize('adapter,operation,args',[
    ('routines','create',{'name':'Bad','frequency':'daily','script':'../../secret.py','time':'09:00'}),
    ('routines','create',{'name':'Bad','frequency':'daily','script':'daily_status_report.py','time':'28:90'}),
    ('integrations','create',{'slug':'acme','displayName':'Acme','envValues':{'TOKEN':'hidden'}}),
    ('integrations','create',{'slug':'acme','displayName':'Acme','envKeys':['GITHUB_PLUGIN_TOKEN']}),
    ('triggers','create',{'name':'Unsafe','type':'event','source':'custom','action_type':'prompt','action_payload':'run arbitrary tools'}),
])
def test_invalid_or_implicit_execution_is_rejected_before_approval(adapters,adapter,operation,args):
    _,_,c,ctx,effects=adapters
    assert operate(c,ctx,adapter,operation,args).status_code==400
    assert not effects


def test_removal_requires_human_even_with_yolo_and_preserves_backup(adapters,tmp_path):
    _,_,c,ctx,effects=adapters
    pending=operate(c,ctx,'removal','remove',{'area':'heartbeats','identifier':'old-heartbeat'})
    assert pending.status_code==200 and pending.json['approvalRequired'] and not effects
    result=approve(c,ctx,pending)
    assert result.status_code==200
    assert effects[0][0:2]==('DELETE','/api/heartbeats/old-heartbeat')
    assert list((tmp_path/'backups/live-adapter-edits').glob('*.enc'))


def test_stale_target_cannot_be_approved(adapters,monkeypatch):
    mod,_,c,ctx,effects=adapters
    pending=operate(c,ctx,'heartbeats','update',{'identifier':'existing','changes':{'enabled':False}})
    monkeypatch.setattr(mod,'native',lambda *a,**kw:{'id':'existing','enabled':True,'revision':2})
    result=approve(c,ctx,pending)
    assert result.status_code==409 and result.json['error']=='approval_target_changed'
    assert not effects


def test_integration_create_never_accepts_credential_values(adapters):
    _,_,c,ctx,effects=adapters
    pending=operate(c,ctx,'integrations','create',{'slug':'acme','displayName':'Acme',
        'envKeys':['CUSTOM_ACME_API_KEY']})
    result=approve(c,ctx,pending)
    assert result.status_code==200 and result.json['credentialEntry']=='integrations_panel_only'
    assert 'envValues' not in effects[0][2]


def test_conditional_trigger_supports_bounded_logic_without_eval():
    from live_trigger_conditions import matches,validate
    tree={'all':[{'field':'data.amount','op':'gte','value':100},
                 {'any':[{'field':'source','op':'eq','value':'github'},
                         {'field':'event_type','op':'glob','value':'issue*'}]}]}
    validate(tree)
    assert matches({'source':'github','data':{'amount':150}},tree)
    assert not matches({'source':'github','data':{'amount':1}},tree)
    with pytest.raises(ValueError):validate({'field':'x','op':'eval','value':'arbitrary()'})
    node={'field':'x','op':'eq','value':1}
    for _ in range(9):node={'not':node}
    with pytest.raises(ValueError):validate(node)


def test_material_edit_keeps_ownership_and_updates_binding_revision(adapters,tmp_path):
    _,app,c,ctx,effects=adapters
    from routes.live_experience import live
    root=tmp_path/'workspace/editorial';root.mkdir(parents=True)
    source=root/'brief.md';source.write_text('Original authored material')
    base=f"/api/live/omni-context/{ctx['contextId']}/file-sources/"
    def post(suffix,**extra):return c.post(base+suffix,json={'conversationId':'conv-fixture',**extra},headers=ORIGIN)
    preview=post('preview',path='workspace/editorial/brief.md');assert preview.status_code==200
    binding=post('bind',path='workspace/editorial/brief.md',sha256=preview.json['sha256'],expectedRevision=0,confirmOwnership=True)
    assert binding.status_code==200
    pending=operate(c,ctx,'materials','edit',{'artifactId':'file:'+binding.json['id'],
        'content':'Updated material','expectedSha256':preview.json['sha256']})
    assert pending.json['approvalRequired']
    applied=approve(c,ctx,pending);assert applied.status_code==200,applied.json
    assert applied.json['data']['revision']==2 and source.read_text()=='Updated material'
    assert next((tmp_path/'backups/live-document-edits').rglob('brief.md')).read_text()=='Original authored material'
    with app.app_context(),live._store() as conn:
        record=conn.execute('SELECT user_id,company_id,revision FROM live_file_sources').fetchone()
        assert tuple(record)==(31,7,2)
        audit=conn.execute('SELECT previous_sha256,new_sha256 FROM live_material_edits').fetchone()
        assert audit[0]==preview.json['sha256'] and audit[1]!=audit[0]


def test_skill_executor_uses_registered_read_adapter_and_receipt(adapters,tmp_path,monkeypatch):
    _,_,c,ctx,_=adapters
    from routes.live_experience import live
    path=tmp_path/'.claude/skills/mkt-brand-review';path.mkdir(parents=True)
    (path/'SKILL.md').write_text('---\ndescription: Brand review\n---\nReview the supplied brand references.')
    calls=[]
    monkeypatch.setattr(live,'_query_files',lambda *a:calls.append(a) or {'status':'available','results':[]})
    pending=operate(c,ctx,'skills','execute',{'name':'mkt-brand-review','capability':'brand-review-context',
        'input':{'query':'Revisar marca'}})
    assert pending.status_code==200 and pending.json['approvalRequired']
    result=approve(c,ctx,pending);assert result.status_code==200,result.json
    assert calls and result.json['data']['execution']['adapter']=='authorized_brand_references'
    assert result.json['data']['execution']['status']=='completed'
    assert operate(c,ctx,'skills','execute',{'name':'arbitrary','capability':'shell','input':{'query':'run script'}},'bad-skill').status_code==400


def test_provider_client_parameters_have_an_explicit_value_source():
    """ElevenLabs rejects properties without description or another value source."""
    from pathlib import Path
    contract=json.loads((Path(__file__).resolve().parents[2]/'config/live-experience/client-tools.json').read_text())
    for tool in contract['tools']:
        for name,parameter in tool.get('parameters',{}).get('properties',{}).items():
            assert parameter.get('description') or parameter.get('dynamic_variable') or parameter.get('is_system_provided') or 'constant_value' in parameter or parameter.get('is_omitted'),(tool['name'],name)
