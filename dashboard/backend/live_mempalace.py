"""Scoped lexical recall over existing drawers, without global search or mining.

The reviewed ownership manifest is an overlay, not a rewrite of historical
author/source metadata. No embeddings, remote model, credentials or agent ACL.
"""
import hashlib
import json
import re
from pathlib import Path,PurePosixPath
from flask_login import current_user
from models import has_permission,Company,db
from live_file_sources import source_text_allowed

POLICY=Path(__file__).resolve().parents[2]/'config/live-mempalace-access.json'
ID=re.compile(r'[A-Za-z0-9_.:-]{1,256}')


def scoped_grants(row):
    if (not current_user.is_authenticated or int(current_user.get_id())!=row['user_id']
            or not has_permission(current_user.role,'memory','view')
            or not has_permission(current_user.role,'mempalace','view')):raise PermissionError()
    data=json.loads(POLICY.read_text())
    if data.get('version')!=1 or not isinstance(data.get('grants'),list):raise ValueError('invalid_memory_manifest')
    company=db.session.get(Company,row['company_id'])
    if not company or company.status!='active':raise PermissionError()
    attribution=data.get('attribution') or {}
    if (attribution.get('companyId')==row['company_id']
            and attribution.get('companySlug')!=company.slug):raise PermissionError()
    rows={}
    for item in data['grants']:
        if item.get('companyId')!=row['company_id'] or item.get('userId')!=row['user_id']:continue
        if (item.get('approved') is not True or not isinstance(item.get('drawerId'),str) or not ID.fullmatch(item['drawerId'])
                or not isinstance(item.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',item['sha256'])):continue
        if item['drawerId'] in rows:raise ValueError('duplicate_memory_grant')
        rows[item['drawerId']]=item['sha256']
    return rows


def _collection():
    from routes.mempalace import PALACE_DIR
    import chromadb
    base=PALACE_DIR/'chroma' if (PALACE_DIR/'chroma').is_dir() else PALACE_DIR
    if not base.is_dir():raise ValueError('memory_index_unavailable')
    return chromadb.PersistentClient(path=str(base)).get_collection('mempalace_drawers')


def _records(row):
    grants=scoped_grants(row)
    if not grants:return [],'ownership_not_configured'
    # IDs are selected by the server manifest BEFORE touching the vector index.
    # Collection.get never runs embedding/search against unowned legacy drawers.
    collection=_collection();records=[];identifiers=sorted(grants)
    for start in range(0,len(identifiers),100):
        data=collection.get(ids=identifiers[start:start+100],include=['documents','metadatas'])
        for ident,text,meta in zip(data.get('ids',[]),data.get('documents',[]),data.get('metadatas',[])):
            if ident not in grants or not source_text_allowed(text):continue
            digest=hashlib.sha256(text.encode()).hexdigest()
            if digest!=grants[ident]:continue
            meta=meta if isinstance(meta,dict) else {}
            title=PurePosixPath(str(meta.get('source_file','Memória'))).name[:160]
            author=str(meta.get('added_by','historical_author_not_recorded'))[:120]
            if not source_text_allowed(title+'\n'+author):continue
            records.append({'drawerId':ident,'reference':'mempalace:'+ident,'sha256':digest,
                'title':title,'historicalAuthor':author,'content':text})
    current=scoped_grants(row)
    return sorted((x for x in records if current.get(x['drawerId'])==x['sha256']),key=lambda x:x['drawerId']),'available'


def inspect(row,identifier=None,page=1):
    if type(page) is not int or not 1<=page<=10000:raise ValueError('invalid_memory_page')
    records,status=_records(row)
    if identifier is not None:
        if not isinstance(identifier,str) or not ID.fullmatch(identifier):raise PermissionError()
        record=next((x for x in records if x['drawerId']==identifier),None)
        if record is None:raise PermissionError()
        from live_asset_reads import text_page
        return {**{k:v for k,v in record.items() if k!='content'},**text_page(record['content'],(page-1)*12000),
                'kind':'untrusted_reference_data','scope':'current_user_company_all_authorized_squad_agents'}
    start=(page-1)*50;items=[{k:v for k,v in x.items() if k!='content'} for x in records[start:start+50]]
    bound_count=len(scoped_grants(row))
    return {'status':status,'items':items,'total':len(records),'boundCount':bound_count,
            'unavailableCount':bound_count-len(records),'page':page,'hasMore':start+50<len(records),
            'nextPage':page+1 if start+50<len(records) else None,'editableFields':[],
            'scope':'reviewed_user_company_drawers_shared_across_squad','searchMode':'lexical_read_only',
            'unownedLegacyIncluded':False}


def search(row,terms):
    try:
        records,status=_records(row)
        from live_query_excerpt import matching_excerpt
        hits=[x for x in records if any(t.casefold() in (x['title']+' '+x['content']).casefold() for t in terms)]
        return {'status':status,'results':[{**{k:v for k,v in x.items() if k!='content'},
                 'text':matching_excerpt(x['content'],terms)} for x in hits[:3]],
                'authorizedCount':len(records),'searchMode':'lexical_read_only','limit':3}
    except PermissionError:return {'status':'denied','results':[]}
    except Exception:
        # Optional index failures must not break authorized Live history. No
        # provider exception text, paths or document fragments enter responses.
        return {'status':'unavailable','results':[]}
