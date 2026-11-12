"""Server-side access for Gravações, including direct linked MediaJob URLs."""
from flask import abort, request, g
from flask_login import current_user


def require_company(company_id, *, edit=False):
    import models as m
    if not current_user.is_authenticated:
        abort(401)
    if not m.has_permission(current_user.role, "media_jobs", "execute" if edit else "view"):
        abort(403)
    company = m.db.session.get(m.Company, company_id)
    if not company:
        abort(404)
    if current_user.role == "admin":
        return company
    grant = m.db.session.get(m.RecordingAccess, (int(current_user.id), company_id))
    if not grant or (edit and grant.level != "editor"):
        abort(404)
    return company


def require_recording_job_access(job_id):
    import models as m
    version = m.RecordingVersion.query.filter_by(job_id=job_id).first()
    if not version:
        return
    g.recording_scoped = True
    recording = m.db.session.get(m.Recording, version.recording_id)
    require_company(recording.company_id, edit=request.method != "GET")
    if request.method == "POST" and request.path.endswith("/run"):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get("recording_batch") != "v1":
            abort(409, description="recording_worker_upgrade_required")
    if request.method == "PATCH":
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            abort(400)
        technical = any(key.startswith("render_") or key in ("status", "result_json", "progress_message", "last_error") for key in data)
        if technical and current_user.role != "admin" and not getattr(g, "auth_via_api_token", False):
            abort(403, description="worker_fields_require_service")
        if data.get("render_path"):
            from pathlib import Path
            from media_workspace import job_dir
            if job_dir(job_id).resolve() not in Path(data["render_path"]).resolve().parents:
                abort(400, description="recording_render_outside_job")
    # Older previews stay readable; approval/distribution of superseded versions cannot continue.
    if request.method != "GET" and request.path.endswith(("/release/approve", "/release/distribute")):
        latest = m.RecordingVersion.query.filter_by(recording_id=recording.id).order_by(m.RecordingVersion.number.desc()).first()
        if (version.id != latest.id or version.batch != recording.batch
                or version.script_revision != recording.script_revision or not recording.closed):
            abort(409, description="recording_version_superseded")


def release_readiness_error(job):
    import models as m
    version=m.RecordingVersion.query.filter_by(job_id=job.id).first()
    if not version:return None
    row=m.db.session.get(m.Recording,version.recording_id)
    latest=m.RecordingVersion.query.filter_by(recording_id=row.id).order_by(m.RecordingVersion.number.desc()).first()
    if version.id!=latest.id or version.batch!=row.batch or version.script_revision!=row.script_revision or not row.closed:
        return 'recording_version_superseded'
    if not version.qa_sha256 or version.qa_sha256!=job.render_sha256:
        return 'recording_requires_human_audio_caption_rights_qa'
    return None
