"""Read-only adapter for existing recording scripts and their canonical ACL."""
import hashlib
from live_file_sources import source_text_allowed
from sqlalchemy import or_
from werkzeug.exceptions import HTTPException


def search_current_scripts(company_id, terms):
    # Resolve identity/permissions through the SAME gate used by /api/recordings.
    from recordings_access import require_company
    from models import Recording, RecordingScript
    try:
        require_company(company_id)
    except HTTPException as exc:
        if exc.code not in (401, 403, 404):
            raise
        return {'status': 'denied', 'source': 'authorized_recording_scripts', 'results': []}
    query = RecordingScript.query.join(Recording, Recording.id == RecordingScript.recording_id).filter(
        Recording.company_id == company_id,
        RecordingScript.number == Recording.script_revision,
        or_(*(or_(Recording.title.ilike('%' + term + '%'),
                   RecordingScript.text.ilike('%' + term + '%')) for term in terms)))
    results = []
    for script in query.order_by(RecordingScript.created_at.desc(), RecordingScript.id).limit(3).all():
        recording = Recording.query.filter_by(id=script.recording_id, company_id=company_id).first()
        if recording is None or recording.script_revision != script.number:
            continue
        # A broken digest is not silently presented as a verified current version.
        if not source_text_allowed(script.text) or hashlib.sha256(script.text.encode()).hexdigest() != script.sha256:
            continue
        positions = [script.text.lower().find(term.lower()) for term in terms]
        position = min((p for p in positions if p >= 0), default=0)
        start = max(0, position - 120)
        results.append({'reference': '/api/recordings/' + recording.id,
                        'recordingId': recording.id, 'scriptId': script.id,
                        'title': recording.title[:200], 'revision': script.number,
                        'sha256': script.sha256, 'authoredAt': script.created_at,
                        'text': script.text[start:start + 600],
                        'source': 'recording_current_script'})
    # Recheck canonical grant before delivering the selected excerpts.
    try:
        require_company(company_id)
    except HTTPException as exc:
        if exc.code not in (401, 403, 404):
            raise
        return {'status': 'denied', 'source': 'authorized_recording_scripts', 'results': []}
    return {'status': 'available', 'source': 'authorized_recording_scripts',
            'results': results, 'limit': 3}
