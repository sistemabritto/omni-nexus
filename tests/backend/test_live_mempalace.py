"""Real manifest/Live scope and fixture index: never mine or query global corpus."""
import hashlib,json
from tests.backend.test_live_experience import experience,call
from tests.backend.test_managed_live_context import setup,ORIGIN


def configure(experience,tmp_path,monkeypatch):
    import live_mempalace as palace
    app,c,_,_,ctx,_=experience
    digest=hashlib.sha256(b'Zephyr retroactive historical memory').hexdigest()
    path=tmp_path/'memory-grants.json'
    grants=[{'drawerId':'owned','companyId':7,'userId':31,'sha256':digest,'approved':True},
            {'drawerId':'other-company','companyId':8,'userId':31,'sha256':digest,'approved':True},
            {'drawerId':'other-user','companyId':7,'userId':32,'sha256':digest,'approved':True},
            {'drawerId':'not-approved','companyId':7,'userId':31,'sha256':digest,'approved':False}]
    path.write_text(json.dumps({'version':1,'grants':grants}));monkeypatch.setattr(palace,'POLICY',path)
    calls=[]
    class Collection:
        def get(self,*,ids,include):
            calls.append(ids);assert ids==['owned']
            # Even a faulty backend returning out-of-scope hits is rejected.
            return {'ids':['owned','other-company'],'documents':['Zephyr retroactive historical memory']*2,
                'metadatas':[{'added_by':'original-author','source_file':'/legacy/original.md'}]*2}
    monkeypatch.setattr(palace,'_collection',lambda:Collection())
    return palace,ctx,path,grants,calls


def test_all_squad_agents_share_only_owned_company_user_memory(experience,tmp_path,monkeypatch):
    palace,ctx,_,_,calls=configure(experience,tmp_path,monkeypatch)
    app,c,_,base,_,api=experience
    from operational_squad import load_operational_squad
    roster=load_operational_squad()
    # Exercise the exact same scoped reader for every approved squad persona.
    from flask_login import login_user
    from models import db,User
    with app.test_request_context('/'):
        login_user(db.session.get(User,31))
        for agent in roster:
            out=palace.inspect({'user_id':31,'company_id':7,'agent_name':agent})
            assert out['total']==1 and out['items'][0]['historicalAuthor']=='original-author'
            assert 'content' not in out['items'][0]
    result=call(c,ctx,'inspect_area',{'area':'mempalace','identifier':'owned'})
    assert result.json['content']=='Zephyr retroactive historical memory'
    assert call(c,ctx,'inspect_area',{'area':'mempalace','identifier':'other-company'}).status_code==403
    query=c.post(f"/api/live/omni-context/{ctx['contextId']}/query",json={'conversationId':'conv-fixture','query':'Zephyr'},headers=ORIGIN)
    assert query.status_code==200
    assert query.json['mempalace']['results'][0]['historicalAuthor']=='original-author'
    assert 'reviewed_scoped_mempalace_drawers' in query.json['coverage']
    assert all(ids==['owned'] for ids in calls)


def test_unowned_stale_revoked_and_sensitive_memories_never_return(experience,tmp_path,monkeypatch):
    palace,ctx,path,grants,calls=configure(experience,tmp_path,monkeypatch)
    _,c,_,_,_,_=experience
    grants[0]['sha256']='0'*64;path.write_text(json.dumps({'version':1,'grants':grants}))
    assert call(c,ctx,'inspect_area',{'area':'mempalace'}).json['total']==0
    grants[0]['approved']=False;path.write_text(json.dumps({'version':1,'grants':grants}))
    calls.clear();response=call(c,ctx,'inspect_area',{'area':'mempalace'})
    assert response.json['status']=='ownership_not_configured' and calls==[]
    grants[0]['approved']=True;path.write_text(json.dumps({'version':1,'grants':grants}))
    import live_mempalace
    def revoke():
        class Collection:
            def get(self,**kw):
                path.write_text(json.dumps({'version':1,'grants':[]}))
                return {'ids':['owned'],'documents':['Zephyr retroactive historical memory'],'metadatas':[{}]}
        return Collection()
    monkeypatch.setattr(palace,'_collection',revoke)
    assert call(c,ctx,'inspect_area',{'area':'mempalace'}).json['total']==0
