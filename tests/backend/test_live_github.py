"""GitHub policy and dispatch under the real Live guards; HTTP is synthetic."""
import json
from tests.backend.test_live_experience import experience,call
from tests.backend.test_managed_live_context import setup


def configure(experience,tmp_path,monkeypatch):
    import live_github as github
    from models import db,Company
    app,c,_,_,ctx,_=experience
    with app.app_context():
        db.session.get(Company,7).slug='sistema-britto';db.session.commit()
    path=tmp_path/'github-policy.json'
    path.write_text(json.dumps({'version':1,'bindings':[{'companyId':7,'companySlug':'sistema-britto',
        'userId':31,'owner':'fixture-owner','repositories':'*','write':True,'delete':False}]}))
    monkeypatch.setattr(github,'POLICY',path)
    return github,c,ctx


def test_all_repositories_paginated_and_cross_owner_denied(experience,tmp_path,monkeypatch):
    github,c,ctx=configure(experience,tmp_path,monkeypatch)
    calls=[]
    def request(method,path,**kw):
        calls.append((method,path,kw));return [
            {'full_name':'fixture-owner/any-repo','private':True,'patch':'a'*5000},
            {'full_name':'other/hidden-repo','private':True},
            {'full_name':'fixture-owner/any-repo/pulls'},
        ],True
    monkeypatch.setattr(github,'_request',request)
    response=call(c,ctx,'inspect_area',{'area':'github','page':2})
    assert response.status_code==200 and response.json['nextPage']==3
    assert calls[0][1]=='user/repos'
    assert calls[0][2]['params']=={'per_page':50,'page':2,'affiliation':'owner','visibility':'all'}
    assert len(response.json['data'])==1 and response.json['data'][0]['private'] is True
    assert len(response.json['data'][0]['patch'])==5000
    for path in ('repos/other/repo/pulls','repos/fixture-owner/../pulls','https://evil.invalid'):
        assert call(c,ctx,'inspect_area',{'area':'github','identifier':path}).status_code==403
    assert len(calls)==1


def test_repository_index_rechecks_repository_allowlist(experience,tmp_path,monkeypatch):
    github,c,ctx=configure(experience,tmp_path,monkeypatch)
    policy=json.loads(github.POLICY.read_text());policy['bindings'][0]['repositories']=['allowed']
    github.POLICY.write_text(json.dumps(policy))
    monkeypatch.setattr(github,'_request',lambda *a,**kw:([
        {'full_name':'fixture-owner/allowed','private':True},
        {'full_name':'fixture-owner/forbidden','private':True},
        {'full_name':'other/allowed','private':True},
    ],False))
    response=call(c,ctx,'inspect_area',{'area':'github'})
    assert response.status_code==200
    assert [x['full_name'] for x in response.json['data']]==['fixture-owner/allowed']


def test_explicit_owner_alias_resolves_to_same_authorized_owner(experience,tmp_path,monkeypatch):
    github,c,ctx=configure(experience,tmp_path,monkeypatch)
    policy=json.loads(github.POLICY.read_text());policy['bindings'][0]['ownerAliases']=['sistema-britto']
    github.POLICY.write_text(json.dumps(policy));requests=[]
    monkeypatch.setattr(github,'_request',lambda method,path,**kw:(requests.append(path) or {'number':93},False))
    result=call(c,ctx,'inspect_area',{'area':'github','identifier':'repos/sistema-britto/omni-nexus-live/pulls/93'})
    assert result.status_code==200 and result.json['data']['number']==93
    assert requests==['repos/fixture-owner/omni-nexus-live/pulls/93']
    assert result.json['canonicalIdentifier']==requests[0]
    assert call(c,ctx,'inspect_area',{'area':'github','identifier':'repos/other/omni-nexus-live/pulls/93'}).status_code==403


def test_large_diff_has_lossless_transport_pages(experience,tmp_path,monkeypatch):
    github,c,ctx=configure(experience,tmp_path,monkeypatch)
    data=[{'filename':'large.py','patch':'print("line")\n'*12000}]
    monkeypatch.setattr(github,'_request',lambda *a,**kw:(data,True))
    parameters={'area':'github','identifier':'repos/fixture-owner/repo/pulls/93/files'}
    chunks=[];offset=0;digest=None
    while True:
        response=call(c,ctx,'inspect_area',{**parameters,'offset':offset},'read-'+str(offset))
        assert response.status_code==200
        result=response.json
        assert len(json.dumps(result,ensure_ascii=False))<24000
        assert result['hasMore'] and result['nextPage']==2
        assert not digest or result['sha256']==digest
        digest=result['sha256'];chunks.append(result['content'])
        if result['nextOffset'] is None:break
        offset=result['nextOffset']
    assert json.loads(''.join(chunks))==data


def test_github_failure_has_static_actionable_code(experience,tmp_path,monkeypatch):
    github,c,ctx=configure(experience,tmp_path,monkeypatch)
    monkeypatch.delenv('GITHUB_PLUGIN_TOKEN',raising=False)
    result=call(c,ctx,'inspect_area',{'area':'github'})
    assert result.json['error']=='github_credential_not_configured'


def test_no_delete_admin_force_or_ambiguous_write_retry(experience,tmp_path,monkeypatch):
    github,c,ctx=configure(experience,tmp_path,monkeypatch)
    calls=[]
    monkeypatch.setattr(github,'_request',lambda method,path,**kw:(calls.append(method) or {'id':1},False))
    def write(method,path,body={},key='request-1'):
        return call(c,ctx,'update_area',{'area':'github','identifier':'fixture-owner/any-repo',
            'changesJson':json.dumps({'method':method,'path':path,'body':body})},key)
    assert write('DELETE','repos/fixture-owner/any-repo/issues/1').status_code==403
    assert write('PATCH','repos/fixture-owner/any-repo').status_code==403
    assert write('POST','repos/fixture-owner/any-repo/transfer').status_code==403
    assert write('PATCH','repos/fixture-owner/any-repo/git/refs',{'force':True}).status_code==403
    path='repos/fixture-owner/any-repo/issues/1/comments'
    assert write('POST',path,{'body':'Review comment'}).status_code==200
    assert write('POST',path,{'body':'Review comment'}).json['replayed'] is True
    assert calls==['POST']


def test_missing_credential_and_policy_do_not_imply_health(experience,tmp_path,monkeypatch):
    github,c,ctx=configure(experience,tmp_path,monkeypatch)
    monkeypatch.delenv('GITHUB_PLUGIN_TOKEN',raising=False)
    assert call(c,ctx,'inspect_area',{'area':'github'}).status_code==400
    data=call(c,ctx,'capabilities').json['integrations']['items']
    item=next(x for x in data if x['name']=='GitHub')
    assert not item['configured'] and item['health']=='not_checked'
