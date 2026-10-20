"""Read only the current human/company's explicit sources and recording scripts."""
import hashlib
import re
from flask_login import current_user
from werkzeug.exceptions import HTTPException
from live_file_sources import list_bindings, resolve_binding, source_text_allowed, FileSourceDenied


def shared_sources(row):
    from routes import live_experience as api
    from recordings_access import require_company
    from models import Recording, RecordingScript
    if int(current_user.get_id()) != row['user_id']:raise PermissionError()
    try:
        with api.live._store() as conn:
            files=list_bindings(conn,row)['bindings']
    except FileSourceDenied:
        files=[]
    items=[{'artifactId':'file:'+f['id'],'title':f['path'],'source':'explicit_workspace_file',
            'sha256':f['sha256'],'revision':f['revision']} for f in files if f['status']=='current']
    try:
        require_company(row['company_id'])
    except HTTPException as exc:
        if exc.code not in (401,403,404):raise
        return {'items':items,'total':len(items),'recordingScriptsStatus':'denied'}
    for recording,script in __import__('models').db.session.query(Recording,RecordingScript).join(
            RecordingScript,RecordingScript.recording_id==Recording.id).filter(
            Recording.company_id==row['company_id'],RecordingScript.number==Recording.script_revision).order_by(Recording.id).all():
        if source_text_allowed(script.text) and hashlib.sha256(script.text.encode()).hexdigest()==script.sha256:
            items.append({'artifactId':'recording:'+recording.id,'title':recording.title[:200],
                          'source':'recording_current_script','sha256':script.sha256,'revision':script.number})
    return {'items':items,'total':len(items),'recordingScriptsStatus':'available'}


def read_source(row,identifier,offset=0):
    from routes import live_experience as api
    if int(current_user.get_id())!=row['user_id']:raise PermissionError()
    if not isinstance(identifier,str) or not re.fullmatch(r'(file|recording):[A-Za-z0-9_-]{1,128}',identifier):raise ValueError('invalid_source')
    kind,ident=identifier.split(':',1)
    sources=shared_sources(row)['items']
    source=next((s for s in sources if s['artifactId']==identifier),None)
    if source is None:raise PermissionError()
    try:
        if kind=='file':
            with api.live._store() as conn:
                text=resolve_binding(conn,row,ident,source['sha256'],source['revision'])['text']
        else:
            from live_file_receipts import _recording
            text=_recording(row,ident,source['sha256'],source['revision'])['text']
    except FileSourceDenied:raise PermissionError() from None
    return {**source,**text_page(text,offset),'kind':'untrusted_reference_data'}


def text_page(text,offset):
    if type(offset) is not int or not 0<=offset<=len(text):raise ValueError('invalid_offset')
    end=min(offset+12000,len(text))
    return {'content':text[offset:end],'offset':offset,'nextOffset':end if end<len(text) else None,
            'totalCharacters':len(text),'truncated':end<len(text)}
