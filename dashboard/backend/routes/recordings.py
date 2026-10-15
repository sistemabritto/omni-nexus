"""Private Gravações queue: explicit batch closure, immutable versions, no paid APIs."""
from __future__ import annotations
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, abort, jsonify, request, send_file, g
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
import models as m
from media_workspace import ensure_job_scaffold
from media_release import assert_current, ReleaseError
from recording_edits import edit_decisions
from recordings_access import require_company
from recordings_storage import CHUNK_BYTES, atomic_write, hash_file, media_kind, private_path, valid_signature

bp = Blueprint('recordings', __name__)
MAX_FILE = int(os.environ.get('RECORDINGS_MAX_FILE_BYTES', str(2 * 1024**3)))


def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
def uid(): return str(uuid.uuid4())
def encoded(value): return json.dumps(value, ensure_ascii=False, sort_keys=True)
def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict): abort(400, description='object_required')
    return data

def text(value, name, maximum=20000):
    if not isinstance(value, str) or not value.strip() or len(value)>maximum:
        abort(400, description=name+'_required_or_too_long')
    return value

def integer(value, name, minimum=0):
    if isinstance(value,bool) or not isinstance(value,int) or value<minimum:
        abort(400, description='invalid_'+name)
    return value

def record(recording_id, edit=False):
    row = m.db.get_or_404(m.Recording, recording_id)
    require_company(row.company_id, edit=edit)
    return row

def touch(row, *, require_open=True, expected=None):
    if require_open and row.closed: abort(409, description='batch_closed')
    previous = row.revision if expected is None else expected
    query = m.db.update(m.Recording).where(m.Recording.id==row.id, m.Recording.revision==previous)
    if require_open: query = query.where(m.Recording.closed.is_(False))
    result = m.db.session.execute(query.values(revision=previous+1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        m.db.session.rollback(); abort(409, description='recording_changed_reload')
    m.db.session.refresh(row)
    active=m.RecordingVersion.query.filter_by(recording_id=row.id).all()
    if active and m.MediaRelease.query.filter(m.MediaRelease.job_id.in_([v.job_id for v in active]),m.MediaRelease.busy.is_(True)).first():
        m.db.session.rollback();abort(409,description='release_busy')


def references(value):
    if not isinstance(value,list) or len(value)>200: abort(400,description='invalid_references')
    for ref in value:
        if not isinstance(ref,dict): abort(400,description='invalid_reference')
        text(ref.get('label'),'reference_label',250)
        target = text(ref.get('reference'),'reference',1500)
        parsed = urlparse(target)
        if parsed.scheme not in ('https','reel','artifact') or parsed.username or parsed.password or (parsed.scheme=='https' and not parsed.netloc):
            abort(400,description='reference_must_be_https_reel_or_artifact')
    return value  # Preserve order and duplicates; never fetch or delete historical artifacts.


def upload_dict(upload):
    return {key:getattr(upload,key) for key in ('id','batch','client_key','position','name','kind','mime','declared_size','received','sha256','status','duplicate_of')}


def version_dict(version):
    job = m.db.session.get(m.MediaJob,version.job_id)
    release = m.db.session.get(m.MediaRelease,version.job_id)
    delivery = release.to_dict() if release else None
    if release:
        try: assert_current(job,release)
        except ReleaseError as exc: delivery.update(approval_valid=False,invalidated_reason=str(exc))
    return {'id':version.id,'number':version.number,'batch':version.batch,'script_revision':version.script_revision,
            'snapshot':json.loads(version.snapshot_json),'created_at':version.created_at,
            'qa_valid':bool(version.qa_sha256 and version.qa_sha256==job.render_sha256),'qa_by':version.qa_by,
            'job':job.to_dict(),'release':delivery}


def state_for(row,uploads,versions):
    current = next((v for v in versions if v['batch']==row.batch and v['script_revision']==row.script_revision),None)
    if not row.closed:
        return 'receiving_raw' if uploads else 'ready_to_record'
    if not current: return 'ready_to_edit'
    job,release = current['job'],current['release']
    if job['status'] in ('failed','retryable_failure','cancelled'): return 'editing_attention'
    if job['status'] in ('queued','preparing'): return 'ready_to_edit'
    if job['status'] in ('generating','rendering','validating'): return 'editing'
    if job['status'] not in ('ready_for_review','approved'): return 'in_review'
    if release:
        states=[c.get('state') for c in release['progress'].get('channels',{}).values()]
        count=len(release['snapshot']['channels'])
        if len(states)==count and all(s=='published' for s in states): return 'published'
        if len(states)==count and all(s in ('scheduled','published') for s in states): return 'scheduled'
        if any(s in ('unknown','remote_error','remote_mismatch','calendar_expired','retryable_failure') for s in states): return 'distribution_attention'
        if any(s in ('scheduled','published') for s in states): return 'partial_distribution'
        if release['approval_valid']: return 'approved'
    return 'in_review'


def detail(row):
    uploads = m.RecordingUpload.query.filter_by(recording_id=row.id).order_by(m.RecordingUpload.position).all()
    versions = [version_dict(v) for v in m.RecordingVersion.query.filter_by(recording_id=row.id).order_by(m.RecordingVersion.number.desc())]
    scripts = m.RecordingScript.query.filter_by(recording_id=row.id).order_by(m.RecordingScript.number.desc()).all()
    feedback = m.RecordingFeedback.query.filter_by(recording_id=row.id).order_by(m.RecordingFeedback.created_at).all()
    return {'id':row.id,'company_id':row.company_id,'title':row.title,'origin_type':row.origin_type,'origin_id':row.origin_id,
        'script_revision':row.script_revision,'batch':row.batch,'closed':row.closed,'revision':row.revision,
        'state':state_for(row,uploads,versions),'uploads':[upload_dict(u) for u in uploads], 'versions':versions,
        'scripts':[{'id':s.id,'number':s.number,'text':s.text,'sha256':s.sha256,'references':json.loads(s.references_json)} for s in scripts],
        'feedback':[{'id':f.id,'version_id':f.version_id,'text':f.text,'author_id':f.author_id,'created_at':f.created_at,
            'audio_url':f'/api/recordings/{row.id}/feedback/{f.id}/audio' if f.audio_path else None} for f in feedback],
        'capabilities':{'audio_feedback':True,'automatic_transcription':False,'assembly_only':True}}


@bp.errorhandler(HTTPException)
def api_error(exc):
    m.db.session.rollback()
    return jsonify(error=exc.description),exc.code


@bp.errorhandler(IntegrityError)
def conflict(exc):
    m.db.session.rollback(); return jsonify(error='concurrent_or_duplicate_request_reload'),409


@bp.route('/api/recordings/access',methods=['PUT'])
def grant_access():
    if not current_user.is_authenticated: abort(401)
    if current_user.role!='admin': abort(403)
    data=body(); company=integer(data.get('company_id'),'company_id',1); user=integer(data.get('user_id'),'user_id',1)
    m.db.get_or_404(m.Company,company); m.db.get_or_404(m.User,user)
    level=data.get('level')
    if level not in ('viewer','editor'): abort(400,description='invalid_access_level')
    row=m.db.session.get(m.RecordingAccess,(user,company))
    if not row: row=m.RecordingAccess(user_id=user,company_id=company);m.db.session.add(row)
    row.level=level;m.db.session.commit()
    m.audit(current_user,'manage','media_jobs',f'recordings access user={user} company={company} level={level}')
    return jsonify(user_id=user,company_id=company,level=level)


@bp.route('/api/recordings',methods=['GET','POST'])
def recordings():
    data=body() if request.method=='POST' else request.args
    company=integer(data.get('company_id'),'company_id',1) if request.method=='POST' else request.args.get('company_id',type=int)
    if not company: abort(400,description='company_required')
    require_company(company,edit=request.method=='POST')
    if request.method=='GET':
        return jsonify([detail(r) for r in m.Recording.query.filter_by(company_id=company).order_by(m.Recording.created_at.desc()).limit(100)])
    origin_type=data.get('origin_type','manual')
    if origin_type not in ('manual','reel','script'):abort(400,description='invalid_origin_type')
    origin_id=text(data.get('origin_id') or uid(),'origin_id',200)
    existing=m.Recording.query.filter_by(company_id=company,origin_type=origin_type,origin_id=origin_id).first()
    if existing:return jsonify(detail(existing)),200
    title=text(data.get('title'),'title',300);script=text(data.get('script'),'script')
    refs=references(data.get('references',[]))
    row=m.Recording(id=uid(),company_id=company,created_by=int(current_user.id),title=title,origin_type=origin_type,origin_id=origin_id,created_at=now())
    m.db.session.add(row);m.db.session.flush()
    m.db.session.add(m.RecordingScript(id=uid(),recording_id=row.id,number=1,text=script,
        sha256=hashlib.sha256(script.encode()).hexdigest(),references_json=encoded(refs),created_at=now()))
    m.db.session.commit();return jsonify(detail(row)),201


@bp.route('/api/recordings/<recording_id>',methods=['GET'])
def get_recording(recording_id):return jsonify(detail(record(recording_id)))


@bp.route('/api/recordings/<recording_id>/scripts',methods=['POST'])
def revise_script(recording_id):
    row=record(recording_id,True);data=body();script=text(data.get('script'),'script')
    refs=references(data.get('references',[]))
    touch(row,require_open=False,expected=integer(data.get('expected_revision'),'expected_revision'))
    row.script_revision+=1
    if row.closed:row.batch+=1;row.closed=False
    m.db.session.add(m.RecordingScript(id=uid(),recording_id=row.id,number=row.script_revision,text=script,
        sha256=hashlib.sha256(script.encode()).hexdigest(),references_json=encoded(refs),created_at=now()))
    m.db.session.commit();return jsonify(detail(row)),201


@bp.route('/api/recordings/<recording_id>/uploads',methods=['POST'])
def start_upload(recording_id):
    row=record(recording_id,True);data=body()
    name=text(data.get('name'),'name',250);key=text(data.get('client_key'),'client_key',200)
    size=integer(data.get('size'),'size',1);position=integer(data.get('position'),'position')
    if size>MAX_FILE:abort(413)
    try:kind,mime,ext=media_kind(name,data.get('mime'))
    except ValueError:abort(400,description='unsupported_media')
    checksum=data.get('sha256')
    if checksum is not None and (not isinstance(checksum,str) or len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum)):
        abort(400,description='invalid_checksum')
    existing=m.RecordingUpload.query.filter_by(recording_id=row.id,batch=row.batch,client_key=key).first()
    if existing:
        if (existing.name,existing.declared_size,existing.position,existing.expected_sha256)!=(name,size,position,checksum):abort(409,description='upload_key_conflict')
        return jsonify(upload_dict(existing))
    touch(row)
    upload_id=uid()
    item=m.RecordingUpload(id=upload_id,recording_id=row.id,batch=row.batch,client_key=key,position=position,name=name,
        kind=kind,mime=mime,declared_size=size,expected_sha256=checksum,
        storage_path=f'recordings/{row.company_id}/{row.id}/uploads/{upload_id}/source{ext}')
    m.db.session.add(item);m.db.session.commit();return jsonify(upload_dict(item)),201


def get_upload(row,upload_id):
    item=m.RecordingUpload.query.filter_by(id=upload_id,recording_id=row.id).first_or_404()
    return item


@bp.route('/api/recordings/<recording_id>/uploads/<upload_id>',methods=['PUT'])
def put_chunk(recording_id,upload_id):
    row=record(recording_id,True);item=get_upload(row,upload_id)
    try:offset=int(request.headers.get('Upload-Offset',request.args.get('offset','-1')))
    except ValueError:abort(400,description='invalid_upload_offset')
    data=request.stream.read(CHUNK_BYTES+1)
    if not data or len(data)>CHUNK_BYTES:abort(413,description='chunk_size_invalid')
    digest=hashlib.sha256(data).hexdigest()
    previous=m.db.session.get(m.RecordingChunk,(item.id,offset))
    if previous:
        if previous.sha256!=digest or previous.size!=len(data):abort(409,description='chunk_conflict')
        return jsonify(upload_dict(item))
    if item.status!='receiving' or offset!=item.received or offset+len(data)>item.declared_size:
        return jsonify(error='offset_mismatch',expected_offset=item.received),409
    touch(row)
    target=private_path(item.storage_path).parent/f'chunk-{offset}'
    if target.exists() and hash_file(target)!=digest:abort(409,description='uncommitted_chunk_conflict')
    if not target.exists():atomic_write(target,data)
    m.db.session.add(m.RecordingChunk(upload_id=item.id,offset=offset,size=len(data),sha256=digest))
    item.received+=len(data);m.db.session.commit();return jsonify(upload_dict(item))


@bp.route('/api/recordings/<recording_id>/uploads/<upload_id>/complete',methods=['POST'])
def complete_upload(recording_id,upload_id):
    row=record(recording_id,True);item=get_upload(row,upload_id)
    if item.status=='complete':return jsonify(upload_dict(item))
    if item.received!=item.declared_size:abort(409,description='upload_incomplete')
    touch(row)
    target=private_path(item.storage_path);temporary=target.with_name(uid()+'.part')
    try:
        with temporary.open('wb') as output:
            for part in m.RecordingChunk.query.filter_by(upload_id=item.id).order_by(m.RecordingChunk.offset):
                chunk=target.parent/f'chunk-{part.offset}'
                if not chunk.is_file() or hash_file(chunk)!=part.sha256:abort(409,description='chunk_corrupted')
                with chunk.open('rb') as source:
                    for block in iter(lambda:source.read(CHUNK_BYTES),b''):output.write(block)
        digest=hash_file(temporary)
        if temporary.stat().st_size!=item.declared_size or (item.expected_sha256 and item.expected_sha256!=digest):
            abort(422,description='checksum_mismatch')
        if not valid_signature(temporary):abort(422,description='invalid_media_signature')
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    duplicate=m.RecordingUpload.query.filter_by(recording_id=row.id,sha256=digest,status='complete').order_by(m.RecordingUpload.position).first()
    item.sha256=digest;item.status='complete';item.duplicate_of=duplicate.id if duplicate else None
    m.db.session.commit();return jsonify(upload_dict(item))


@bp.route('/api/recordings/<recording_id>/uploads/<upload_id>/file')
def raw_file(recording_id,upload_id):
    row=record(recording_id);item=get_upload(row,upload_id)
    if item.status!='complete':abort(404)
    return send_file(private_path(item.storage_path),mimetype=item.mime,conditional=True,as_attachment=False,download_name=Path(item.name).name)


@bp.route('/api/recordings/<recording_id>/order',methods=['PUT'])
def reorder(recording_id):
    row=record(recording_id,True);data=body();ids=data.get('upload_ids')
    items=m.RecordingUpload.query.filter_by(recording_id=row.id).all()
    if not isinstance(ids,list) or not all(isinstance(i,str) for i in ids) or len(set(ids))!=len(ids) or set(ids)!={i.id for i in items}:
        abort(400,description='order_requires_all_uploads_once')
    touch(row,expected=integer(data.get('expected_revision'),'expected_revision'))
    by_id={i.id:i for i in items}
    for position,item_id in enumerate(ids):by_id[item_id].position=-position-1
    m.db.session.flush()
    for position,item_id in enumerate(ids):by_id[item_id].position=position
    m.db.session.commit();return jsonify(detail(row))


@bp.route('/api/recordings/<recording_id>/reopen',methods=['POST'])
def reopen(recording_id):
    row=record(recording_id,True);data=body()
    if row.closed:
        touch(row,require_open=False,expected=integer(data.get('expected_revision'),'expected_revision'))
        row.closed=False;row.batch+=1;m.db.session.commit()
    return jsonify(detail(row))


@bp.route('/api/recordings/<recording_id>/close',methods=['POST'])
def close_batch(recording_id):
    row=record(recording_id,True);data=body()
    expected=integer(data.get('expected_revision'),'expected_revision')
    seconds=data.get('photo_seconds',3)
    if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not 1<=seconds<=30:abort(400,description='invalid_photo_seconds')
    selected=data.get('upload_ids')
    if not isinstance(selected,list) or not selected or not all(isinstance(i,str) for i in selected) or len(set(selected))!=len(selected):
        abort(400,description='select_uploaded_assets')
    try: edits=edit_decisions(data.get('edits',{}),selected)
    except ValueError as exc: abort(400,description=str(exc))
    intent={'upload_ids':selected,'photo_seconds':seconds}
    if edits:intent['edits']=edits
    signature=hashlib.sha256(encoded(intent).encode()).hexdigest()
    if row.closed:
        version=m.RecordingVersion.query.filter_by(recording_id=row.id,batch=row.batch,script_revision=row.script_revision).order_by(m.RecordingVersion.number.desc()).first()
        snapshot=json.loads(version.snapshot_json) if version else {}
        if snapshot.get('close_revision')==expected and snapshot.get('close_signature')==signature:return jsonify(detail(row))
        abort(409,description='batch_already_closed')
    touch(row,expected=expected)
    all_items=m.RecordingUpload.query.filter_by(recording_id=row.id).order_by(m.RecordingUpload.position).all()
    if not all_items or any(i.status=='receiving' for i in all_items):abort(409,description='all_uploads_must_finish')
    selected=data.get('upload_ids')
    if not isinstance(selected,list) or not selected or not all(isinstance(i,str) for i in selected) or len(set(selected))!=len(selected) or not set(selected).issubset({i.id for i in all_items}):
        abort(400,description='select_uploaded_assets')
    items=[i for i in all_items if i.id in selected]
    if any(i.status!='complete' for i in items):abort(400,description='select_complete_assets')
    if any(i.id in edits and i.kind!='video' for i in items):abort(400,description='trim_requires_video')
    for item in items:
        if not private_path(item.storage_path).is_file() or hash_file(private_path(item.storage_path))!=item.sha256:abort(409,description='source_changed')
    script=m.RecordingScript.query.filter_by(recording_id=row.id,number=row.script_revision).one()
    number=(m.db.session.query(m.db.func.max(m.RecordingVersion.number)).filter_by(recording_id=row.id).scalar() or 0)+1
    version_id,job_id=uid(),uid();base=ensure_job_scaffold(job_id)
    snapshot={'recording_id':row.id,'version_id':version_id,'script_revision':row.script_revision,'script_sha256':script.sha256,
        'close_revision':expected,'close_signature':signature,'photo_seconds':seconds,
        'assets':[{'id':i.id,'path':i.storage_path,'kind':i.kind,'sha256':i.sha256,'photo_seconds':seconds,**({'trim':edits[i.id]} if i.id in edits else {})} for i in items],
        'edit_plan_version':1,'stage':'rough_assembly','automatic_transcription':False,'feedback_applied':False}
    job=m.MediaJob(id=job_id,company_id=row.company_id,created_by=current_user.username,job_type='recording_batch',
        title=row.title,brief='Montagem inicial dos arquivos na ordem aprovada; sem IA, transcrição, memes ou publicação.',
        caption='',platform='instagram',width=720,height=1280,fps=30,duration_seconds=0,publication_mode='draft',
        status='queued',workspace_path=str(base),result_json=encoded(snapshot),created_at=now(),updated_at=now())
    m.db.session.add(job);m.db.session.flush()
    m.db.session.add(m.RecordingVersion(id=version_id,recording_id=row.id,number=number,batch=row.batch,
        script_revision=row.script_revision,job_id=job_id,snapshot_json=encoded(snapshot),created_at=now()))
    row.closed=True;m.db.session.commit()
    m.audit(current_user,'execute','media_jobs',f'closed recording {row.id} batch={row.batch} version={number} job={job_id}')
    return jsonify(detail(row)),201


@bp.route('/api/recordings/<recording_id>/versions/<version_id>/feedback',methods=['POST'])
def feedback(recording_id,version_id):
    row=record(recording_id,True)
    version=m.RecordingVersion.query.filter_by(id=version_id,recording_id=row.id).first_or_404()
    if request.content_length and request.content_length>20*1024**2:abort(413)
    data=request.form if request.mimetype=='multipart/form-data' else body()
    key=text(data.get('client_key'),'client_key',200)
    previous=m.RecordingFeedback.query.filter_by(version_id=version.id,client_key=key).first()
    content=data.get('text','')
    if not isinstance(content,str) or len(content)>20000:abort(400)
    audio=request.files.get('audio') if request.mimetype=='multipart/form-data' else None
    if previous:
        if previous.author_id!=int(current_user.id) or previous.text!=content:
            abort(409,description='feedback_key_conflict')
        if audio and hashlib.sha256(audio.stream.read(16*1024**2+1)).hexdigest()!=previous.audio_sha256:
            abort(409,description='feedback_key_conflict')
        return jsonify(id=previous.id,version_id=version.id),200
    if not content.strip() and not audio:abort(400,description='text_or_audio_required')
    item=m.RecordingFeedback(id=uid(),recording_id=row.id,version_id=version.id,author_id=int(current_user.id),client_key=key,text=content,created_at=now())
    if audio:
        try:kind,mime,ext=media_kind(audio.filename or '',audio.mimetype)
        except ValueError:abort(400,description='audio_type_not_supported')
        if kind!='audio':abort(400,description='audio_required')
        binary=audio.stream.read(16*1024**2+1)
        if not binary or len(binary)>16*1024**2:abort(413)
        item.audio_path=f'recordings/{row.company_id}/{row.id}/feedback/{item.id}{ext}'
        target=private_path(item.audio_path);atomic_write(target,binary)
        if not valid_signature(target):target.unlink();abort(422,description='invalid_audio')
        item.audio_sha256=hash_file(target);item.audio_mime=mime
    m.db.session.add(item);m.db.session.commit();return jsonify(id=item.id,version_id=version.id,transcribed=False),201


@bp.route('/api/recordings/<recording_id>/feedback/<feedback_id>/audio')
def feedback_audio(recording_id,feedback_id):
    row=record(recording_id)
    item=m.RecordingFeedback.query.filter_by(id=feedback_id,recording_id=row.id).first_or_404()
    if not item.audio_path:abort(404)
    return send_file(private_path(item.audio_path),mimetype=item.audio_mime,conditional=True)


@bp.route('/api/recordings/reel-sources')
def reel_sources():
    # Legacy reels have no trustworthy company owner. Only an admin may explicitly classify them.
    if not current_user.is_authenticated:abort(401)
    if current_user.role!='admin':abort(403)
    from sqlalchemy import inspect
    company=request.args.get('company_id',type=int)
    require_company(company)
    if not inspect(m.db.engine).has_table('reels'):return jsonify([])
    rows=m.db.session.execute(m.db.text('SELECT * FROM reels ORDER BY created_at DESC LIMIT 200')).mappings()
    result=[]
    for source in rows:
        refs=[{'label':'Reel de origem','reference':'reel:'+str(source['id'])}]
        for key,value in source.items():
            if key.endswith('_url') and isinstance(value,str) and value.startswith('https://'):
                refs.append({'label':key,'reference':value})
        result.append({'id':source['id'],'title':source.get('headline') or source.get('theme') or 'Reel',
                       'script':source.get('script_md') or '', 'references':refs})
    return jsonify(result)


@bp.after_request
def private_response(response):
    response.headers['Cache-Control']='private, no-store'
    return response


@bp.route('/api/recordings/<recording_id>/uploads/<upload_id>/exclude',methods=['POST'])
def exclude_incomplete(recording_id,upload_id):
    row=record(recording_id,True);item=get_upload(row,upload_id)
    if item.status=='complete':abort(409,description='complete_files_are_preserved_choose_assembly_selection')
    touch(row);item.status='excluded';m.db.session.commit()
    return jsonify(detail(row))


@bp.route('/api/recordings/<recording_id>/versions/<version_id>/qa',methods=['POST'])
def qa_recording(recording_id,version_id):
    row=record(recording_id,True)
    if getattr(g,'auth_via_api_token',False) or not m.has_permission(current_user.role,'media_jobs','manage'):abort(403)
    version=m.RecordingVersion.query.filter_by(id=version_id,recording_id=row.id).first_or_404()
    latest=m.RecordingVersion.query.filter_by(recording_id=row.id).order_by(m.RecordingVersion.number.desc()).first()
    if version.id!=latest.id or version.batch!=row.batch or version.script_revision!=row.script_revision or not row.closed:abort(409,description='version_superseded')
    data=body();checks=data.get('checks')
    if not isinstance(checks,dict) or not all(checks.get(k) is True for k in ('audio','captions','face','safe_zones','rights')):abort(400,description='qa_checks_required')
    job=m.db.session.get(m.MediaJob,version.job_id)
    if job.status not in ('ready_for_review','approved') or data.get('render_sha256')!=job.render_sha256:abort(409,description='render_not_current')
    from media_release import render_binding
    try:render_binding(job)
    except ReleaseError:abort(409,description='render_changed')
    touch(row,require_open=False)
    version.qa_sha256=job.render_sha256;version.qa_by=current_user.username;version.qa_at=now()
    m.db.session.commit();return jsonify(detail(row))
