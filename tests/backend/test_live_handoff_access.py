"""Complete indexes, paged source reads and unchanged human/company ACLs."""
from tests.backend.test_live_experience import experience,call
from tests.backend.test_managed_live_context import setup
from tests.backend.test_live_recording_source import seed


def test_complete_skills_index_and_read_beyond_first_page(experience,tmp_path):
    _,c,_,_,ctx,_=experience
    root=tmp_path/'.claude/skills'
    for number in range(236):
        folder=root/f'skill-{number:03}';folder.mkdir(parents=True)
        (folder/'SKILL.md').write_text('---\ndescription: Reference\n---\n'+('A'*13000 if number==235 else 'Reference'))
    result=call(c,ctx,'capabilities').json['skills']
    assert result['total']==236 and len(result['items'])==236 and not result['truncated']
    assert len(call(c,ctx,'inspect_area',{'area':'skills'}).json['data']['items'])==236
    first=call(c,ctx,'skill',{'name':'skill-235'}).json
    second=call(c,ctx,'skill',{'name':'skill-235','offset':first['nextOffset']}).json
    assert second['nextOffset'] is None
    assert first['text']+second['text']==(root/'skill-235/SKILL.md').read_text()
    assert call(c,ctx,'skill',{'name':'skill-235','offset':True}).status_code==400


def test_heartbeat_index_includes_late_and_legacy_entries(experience,monkeypatch):
    _,c,_,_,ctx,_=experience
    import live_workspace_actions as actions
    rows=[{'id':f'heartbeat-{n:03}','agent':'retired-agent' if n==79 else 'hawk-debugger',
           'enabled':True,'decision_prompt':'SECRET_PROMPT','token':'PRIVATE'} for n in range(80)]
    monkeypatch.setattr(actions,'native',lambda *_a,**_kw:{'heartbeats':rows})
    data=call(c,ctx,'inspect_area',{'area':'heartbeats'})
    assert data.status_code==200
    assert data.json['data']['total']==80
    assert data.json['data']['heartbeats'][-1]['id']=='heartbeat-079'
    assert data.json['data']['heartbeats'][-1]['legacy'] is True
    assert 'SECRET_PROMPT' not in data.text and 'PRIVATE' not in data.text
    assert not data.json['data']['truncated']


def test_assets_include_current_recording_script_and_read_rechecks_scope(experience,monkeypatch):
    app,c,login,_,ctx,_=experience
    seed(app)
    response=call(c,ctx,'assets')
    assert response.status_code==200
    items=response.json['sharedMaterials']['items']
    assert [x['artifactId'] for x in items]==['recording:rec-a']
    assert call(c,ctx,'artifact',{'artifactId':'recording:rec-a'}).json['content']=='Zephyr roteiro corrente'
    assert call(c,ctx,'artifact',{'artifactId':'recording:rec-b'}).status_code==403
    from models import db,RecordingScript
    with app.app_context():
        script=db.session.get(RecordingScript,'rec-a-2');script.sha256='0'*64;db.session.commit()
    assert call(c,ctx,'artifact',{'artifactId':'recording:rec-a'}).status_code==403
    login(32)
    assert call(c,ctx,'assets').status_code==403


def test_secret_beyond_first_skill_page_is_never_returned(experience,tmp_path):
    _,c,_,_,ctx,_=experience
    folder=tmp_path/'.claude/skills/secret-tail';folder.mkdir(parents=True)
    (folder/'SKILL.md').write_text('Reference\n'*1600+'api_key=sk-private-value')
    assert call(c,ctx,'skill',{'name':'secret-tail'}).status_code==400
