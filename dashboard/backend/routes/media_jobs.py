"""Media Jobs API — social-media-production pipeline orchestration.

Ownership split (see workspace/development/features/social-media-production/
[C]architecture-social-media-production.md):
  - CPU-heavy composition+render+validation (queued/retryable_failure ->
    ready_for_review) runs in the isolated media-worker service, which polls
    this API (`/run` to claim) and reports progress via PATCH — never inside
    this Flask process (Etapa 3: "em vez de executar renderizações dentro
    do processo web do dashboard").
  - I/O-bound Postiz upload/draft/schedule (approved -> draft_created ->
    scheduled) runs directly here — no CPU-bound work, and the render file
    is readable from the shared evonexus_media volume.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError

from flask import Blueprint, jsonify, request, send_file, g
from flask_login import current_user

from models import db, GoalProject, MediaJob, MediaRelease, has_permission, audit
from media_state_machine import assert_transition, can_transition, InvalidTransition, allowed_targets
from media_workspace import ensure_job_scaffold, new_job_id, media_workspace_root, PathSecurityError
from media_retry import MAX_ATTEMPTS, failure_state
from sqlalchemy import or_
from postiz_client import PostizClient, PostizError, MEDIA_JOB_PLATFORMS, build_platform_settings, providers_for
from media_editorial import build_editorial_plan, EditorialPlanError
from media_release import canonical, digest_of, make_snapshot, render_binding, assert_current, distribute, ReleaseError

bp = Blueprint("media_jobs", __name__)


@bp.before_request
def recordings_tenant_boundary():
    if request.view_args and request.view_args.get("job_id"):
        from recordings_access import require_recording_job_access
        require_recording_job_access(request.view_args["job_id"])


@bp.after_request
def private_recording_media(response):
    if getattr(g, "recording_scoped", False):
        response.headers["Cache-Control"] = "private, no-store"
    return response


_WORKER_PATCHABLE_FIELDS = (
    "render_path", "render_sha256", "render_size_bytes", "render_duration_seconds",
    "render_width", "render_height", "render_fps", "render_has_audio", "last_error",
    "title", "brief", "caption", "progress_message", "result_json",
)

MEDIA_JOB_TYPES = frozenset({
    "social_clip", "corte_bruto", "corte_editorial", "aplicar_corte_editorial",
    "cortes_virais", "resumo_tematico", "aplicar_resumo_tematico",
})


def _require(action: str):
    if not has_permission(current_user.role, "media_jobs", action):
        return jsonify({"error": "Forbidden"}), 403
    return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _transition(job: MediaJob, target: str) -> None:
    """Single choke point for every status write — no route may set
    `job.status` directly (briefing: "Valide transições").
    """
    assert_transition(job.status, target)
    job.status = target
    job.updated_at = _now()


def _invalid_transition_response(job: MediaJob, target: str):
    return jsonify({
        "error": "invalid_transition",
        "detail": f"MediaJob está em '{job.status}', não pode ir para '{target}'.",
        "current_status": job.status,
        "allowed_from_current": allowed_targets(job.status),
    }), 409


def _localize_to_utc(local_iso: str, tz_name: str) -> str:
    """MEDIA_TIMEZONE input -> normalized ISO-8601 UTC (briefing Etapa 10:
    the user enters America/Bahia; Postiz gets UTC). Never relies on the
    container's implicit local timezone — always resolves via zoneinfo.
    """
    try:
        tz = ZoneInfo(tz_name)
    except Exception as exc:
        raise ValueError(f"timezone inválido: {tz_name!r}") from exc
    try:
        dt = datetime.fromisoformat(local_iso)
    except ValueError as exc:
        raise ValueError(f"scheduled_at inválido (esperado ISO-8601): {local_iso!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _resolve_platform_settings(job: MediaJob) -> dict:
    if job.platform_settings:
        try:
            data = json.loads(job.platform_settings)
            if isinstance(data, dict) and data.get("__type"):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
    if job.platform == "youtube":
        return build_platform_settings("youtube", title=(job.title or "Vídeo")[:100])
    if job.platform in ("instagram", "linkedin", "tiktok"):
        return build_platform_settings(job.platform)
    raise ValueError(f"Plataforma sem builder de settings: {job.platform!r}")


# ── CRUD ─────────────────────────────────────────────────────────────────

@bp.route("/api/media/editorial/plan", methods=["POST"])
def plan_editorial_media():
    """Offline preview on the media API; never queues jobs or calls a provider.

    Pixel presents the returned beat sheet to Felipe, then submits approved
    work through existing /jobs actions. Client-supplied approval flags are
    not accepted as authorization by this endpoint.
    """
    denied = _require("execute")
    if denied:
        return denied
    try:
        plan = build_editorial_plan(request.get_json(silent=True))
    except EditorialPlanError as exc:
        return jsonify({"error": "invalid_editorial_plan", "detail": str(exc)}), 400
    return jsonify(plan)


def _claim_release(release):
    result = db.session.execute(db.update(MediaRelease).where(
        MediaRelease.job_id == release.job_id, MediaRelease.busy.is_(False),
        MediaRelease.digest == release.digest,
    ).values(busy=True).execution_options(synchronize_session=False))
    db.session.commit()
    db.session.refresh(release)
    return result.rowcount == 1


@bp.route("/api/media/channels")
def media_release_channels():
    denied = _require("manage")
    if denied:
        return denied
    client = PostizClient.from_env()
    if client is None:
        return jsonify({"error": "postiz_not_configured"}), 400
    try:
        connected = client.list_integrations()
    except PostizError as exc:
        return jsonify({"error": "postiz_error", "detail": str(exc)}), 502
    return jsonify([{"id": item["id"], "name": item.get("name") or item["id"],
                     "platform": platform, "provider": item["identifier"]}
                    for item in connected if isinstance(item, dict) and item.get("id") and not item.get("disabled")
                    for platform in MEDIA_JOB_PLATFORMS if item.get("identifier") in providers_for(platform)])


@bp.route("/api/media/jobs/<string:job_id>/release", methods=["GET", "PUT"])
def media_release_plan(job_id):
    denied = _require("view" if request.method == "GET" else "manage")
    if denied:
        return denied
    job = MediaJob.query.get_or_404(job_id)
    release = db.session.get(MediaRelease, job_id)
    if request.method == "GET":
        if not release:
            return jsonify({"error": "no_release"}), 404
        result = release.to_dict()
        try:
            assert_current(job, release)
        except ReleaseError as exc:
            result.update(approval_valid=False, invalidated_reason=str(exc))
        return jsonify(result)
    if job.status not in ("ready_for_review", "approved") or job.postiz_post_id:
        return jsonify({"error": "render_review_required_or_legacy_post_exists"}), 409
    data = request.get_json(silent=True)
    try:
        snapshot = make_snapshot(job, data, (release.revision + 1) if release else 1)
    except (ReleaseError, ValueError) as exc:
        return jsonify({"error": "invalid_release", "detail": str(exc)}), 400
    if release:
        if not isinstance(data, dict) or data.get("expected_digest") != release.digest:
            return jsonify({"error": "stale_release_revision"}), 409
        if not _claim_release(release):
            return jsonify({"error": "release_busy"}), 409
        progress = json.loads(release.progress_json)
        if any(c.get("post_id") or c.get("state") in ("creating_draft", "unknown")
               for c in progress.get("channels", {}).values()):
            release.busy = False
            db.session.commit()
            return jsonify({"error": "reconcile_existing_posts_before_replacing_release"}), 409
    else:
        release = MediaRelease(job_id=job_id, progress_json="{}")
        db.session.add(release)
    release.revision = snapshot["revision"]
    release.snapshot_json = canonical(snapshot)
    release.digest = digest_of(snapshot)
    release.approved_digest = release.approved_at = release.approved_by = None
    release.invalidated_reason = "nova revisão exige aprovação humana"
    release.progress_json = "{}"
    release.busy = False
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "release_revision_conflict"}), 409
    audit(current_user, "manage", "media_jobs", f"release revision {release.revision} for {job_id}")
    return jsonify(release.to_dict())


@bp.route("/api/media/jobs/<string:job_id>/release/approve", methods=["POST"])
def approve_media_release(job_id):
    denied = _require("manage")
    if denied:
        return denied
    if getattr(g, "auth_via_api_token", False):
        return jsonify({"error": "human_session_required"}), 403
    job = MediaJob.query.get_or_404(job_id)
    release = db.get_or_404(MediaRelease, job_id)
    from recordings_access import release_readiness_error
    readiness = release_readiness_error(job)
    if readiness:
        return jsonify({"error": readiness}), 409
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or data.get("digest") != release.digest:
        return jsonify({"error": "stale_release_revision"}), 409
    try:
        if render_binding(job) != json.loads(release.snapshot_json)["binding"]:
            raise ReleaseError("job mudou; criar nova revisão")
    except ReleaseError as exc:
        return jsonify({"error": "approval_stale", "detail": str(exc)}), 409
    if job.status not in ("ready_for_review", "approved") or not _claim_release(release):
        return jsonify({"error": "release_busy_or_not_ready"}), 409
    try:
        if render_binding(job) != json.loads(release.snapshot_json)["binding"]:
            raise ReleaseError("job mudou; criar nova revisão")
    except ReleaseError as exc:
        release.busy = False
        db.session.commit()
        return jsonify({"error": "approval_stale", "detail": str(exc)}), 409
    readiness = release_readiness_error(job)
    if readiness:
        release.busy = False
        db.session.commit()
        return jsonify({"error": readiness}), 409
    release.approved_digest = release.digest
    release.approved_by = current_user.username
    release.approved_at = _now()
    release.invalidated_reason = None
    release.busy = False
    if job.status == "ready_for_review":
        _transition(job, "approved")
    job.approved_at = release.approved_at
    db.session.commit()
    audit(current_user, "manage", "media_jobs", f"approved release {release.digest} for {job_id}")
    return jsonify(release.to_dict())


@bp.route("/api/media/jobs/<string:job_id>/release/distribute", methods=["POST"])
@bp.route("/api/media/jobs/<string:job_id>/release/refresh", methods=["POST"])
def distribute_media_release(job_id):
    denied = _require("manage")
    if denied:
        return denied
    job = MediaJob.query.get_or_404(job_id)
    release = db.get_or_404(MediaRelease, job_id)
    refresh_only = request.path.endswith("/refresh")
    if not _claim_release(release):
        return jsonify({"error": "release_busy"}), 409
    try:
        if not refresh_only:
            assert_current(job, release)
        client = PostizClient.from_env()
        if client is None:
            return jsonify({"error": "postiz_not_configured"}), 400

        def save(progress):
            release.progress_json = canonical(progress)
            db.session.commit()

        distribute(job, release, client, save, refresh_only=refresh_only)
        release.busy = False
        db.session.commit()
        return jsonify(release.to_dict())
    except ReleaseError as exc:
        if not refresh_only:
            release.approved_digest = None
            release.invalidated_reason = str(exc)
            db.session.commit()
        return jsonify({"error": "approval_stale_or_account_unavailable", "detail": str(exc)}), 409
    except PostizError as exc:
        return jsonify({"error": "postiz_error", "detail": str(exc)}), 502
    finally:
        release.busy = False
        db.session.commit()

@bp.route("/api/media/jobs")
def list_media_jobs():
    denied = _require("view")
    if denied:
        return denied
    query = MediaJob.query
    # Legacy jobs retain existing policy; private Gravações never leak through this list.
    if current_user.role != "admin":
        import models as m
        linked = db.select(m.RecordingVersion.job_id)
        allowed = db.select(m.RecordingVersion.job_id).join(m.Recording, m.Recording.id == m.RecordingVersion.recording_id).join(
            m.RecordingAccess, m.RecordingAccess.company_id == m.Recording.company_id).where(m.RecordingAccess.user_id == int(current_user.id))
        query = query.filter((~MediaJob.id.in_(linked)) | MediaJob.id.in_(allowed))
    status = request.args.get("status")
    if status:
        query = query.filter(MediaJob.status == status)
    project_id = request.args.get("project_id", type=int)
    if project_id:
        query = query.filter(MediaJob.project_id == project_id)
    company_id = request.args.get("company_id", type=int)
    if company_id:
        query = query.filter(MediaJob.company_id == company_id)
    platform = request.args.get("platform")
    if platform:
        query = query.filter(MediaJob.platform == platform)
    if request.args.get("eligible") == "true":
        query = query.filter(
            MediaJob.status.in_(("queued", "retryable_failure")),
            MediaJob.locked_at.is_(None),
            MediaJob.attempt_count < MAX_ATTEMPTS,
            or_(MediaJob.next_retry_at.is_(None), MediaJob.next_retry_at <= _now()),
        )
    limit = min(request.args.get("limit", default=200, type=int) or 200, 500)
    jobs = query.order_by(MediaJob.created_at.desc()).limit(limit).all()
    return jsonify([j.to_dict() for j in jobs])


@bp.route("/api/media/jobs/<string:job_id>")
def get_media_job(job_id):
    denied = _require("view")
    if denied:
        return denied
    job = MediaJob.query.get_or_404(job_id)
    return jsonify(job.to_dict())


@bp.route("/api/media/jobs", methods=["POST"])
def create_media_job():
    denied = _require("execute")
    if denied:
        return denied
    data = request.get_json() or {}

    job_type = data.get("job_type", "social_clip")
    if job_type not in MEDIA_JOB_TYPES:
        return jsonify({"error": f"job_type inválido: {job_type!r}. Aceita: {sorted(MEDIA_JOB_TYPES)}"}), 400

    if job_type in ("corte_bruto", "corte_editorial", "aplicar_corte_editorial", "cortes_virais",
                    "resumo_tematico", "aplicar_resumo_tematico"):
        # Fase 1A/1B/1C: não passam por OpenCode/Postiz, então platform/width/
        # height/duration_seconds não descrevem uma saída de rede — são
        # preenchidos com o formato conhecido do material de origem e
        # sobrescritos pelos campos render_* reais quando o worker termina
        # (ver worker.py). corte_editorial e cortes_virais não produzem um
        # único vídeo final (o primeiro só a proposta + página de revisão, o
        # segundo N cortes verticais separados), mas usam os mesmos
        # placeholders por simplicidade — nenhum dos dois é lido de fato pra
        # estes tipos.
        if not (data.get("title") or "").strip():
            return jsonify({"error": "Campos obrigatórios ausentes: ['title']"}), 400
        if not (data.get("source_path") or "").strip():
            return jsonify({"error": f"{job_type} exige source_path (vídeo já acessível ao worker)."}), 400
        if job_type == "aplicar_corte_editorial":
            cortes = data.get("cortes")
            if not isinstance(cortes, list) or not cortes:
                return jsonify({"error": "aplicar_corte_editorial exige 'cortes': lista não vazia de {inicio, fim} já aprovados."}), 400
            for c in cortes:
                if not isinstance(c, dict) or "inicio" not in c or "fim" not in c:
                    return jsonify({"error": "cada corte precisa de 'inicio' e 'fim' (segundos)."}), 400
            data["result_json"] = json.dumps({"cortes": cortes}, ensure_ascii=False)
        if job_type == "resumo_tematico":
            if not (data.get("tema") or "").strip():
                return jsonify({"error": "resumo_tematico exige 'tema' (o que o resumo deve reunir)."}), 400
            # Sem coluna própria pro tema — reaproveita `brief` (texto livre já
            # existente no schema) em vez de migrar o banco pra um campo usado
            # por um job_type só.
            data["brief"] = data["tema"]
        if job_type == "aplicar_resumo_tematico":
            trechos = data.get("trechos")
            if not isinstance(trechos, list) or not trechos:
                return jsonify({"error": "aplicar_resumo_tematico exige 'trechos': lista não vazia de {inicio, fim} já aprovados."}), 400
            for t in trechos:
                if not isinstance(t, dict) or "inicio" not in t or "fim" not in t:
                    return jsonify({"error": "cada trecho precisa de 'inicio' e 'fim' (segundos)."}), 400
            data["result_json"] = json.dumps({"trechos": trechos}, ensure_ascii=False)
        data.setdefault("platform", "youtube")
        data.setdefault("width", 1280)
        data.setdefault("height", 720)
        data.setdefault("fps", 24)
        data.setdefault("duration_seconds", 0.0)
        data.setdefault("format", "landscape")

    required = ["title", "platform", "width", "height", "duration_seconds"]
    missing = [f for f in required if data.get(f) in (None, "")]
    if missing:
        return jsonify({"error": f"Campos obrigatórios ausentes: {missing}"}), 400

    platform = data["platform"]
    if platform not in MEDIA_JOB_PLATFORMS:
        return jsonify({"error": f"platform inválido: {platform!r}. Aceita: {list(MEDIA_JOB_PLATFORMS)}"}), 400

    publication_mode = data.get("publication_mode", os.environ.get("SOCIAL_DEFAULT_POST_MODE", "draft"))
    if publication_mode not in ("draft", "schedule"):
        return jsonify({"error": f"publication_mode inválido: {publication_mode!r}"}), 400

    tz_name = data.get("timezone") or os.environ.get("MEDIA_TIMEZONE", "America/Bahia")
    scheduled_at = data.get("scheduled_at")
    scheduled_at_utc = None
    if scheduled_at:
        try:
            scheduled_at_utc = _localize_to_utc(scheduled_at, tz_name)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if publication_mode == "schedule":
            scheduled_dt = datetime.strptime(scheduled_at_utc, "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc)
            if scheduled_dt <= datetime.now(timezone.utc):
                return jsonify({"error": "scheduled_at precisa estar no futuro."}), 400

    platform_settings = data.get("platform_settings")
    if platform_settings is not None and not isinstance(platform_settings, dict):
        return jsonify({"error": "platform_settings deve ser um objeto."}), 400

    job_id = new_job_id()
    now = _now()
    _proj = GoalProject.query.get(data.get("project_id")) if data.get("project_id") else None
    job = MediaJob(
        id=job_id,
        project_id=data.get("project_id"),
        company_id=data.get("company_id") or (_proj.company_id if _proj else None),
        campaign_id=data.get("campaign_id"),
        goal_id=data.get("goal_id"),
        task_id=data.get("task_id"),
        created_by=getattr(current_user, "username", "system"),
        job_type=job_type,
        source_path=data.get("source_path"),
        result_json=data.get("result_json"),
        title=data["title"],
        brief=data.get("brief"),
        platform=platform,
        postiz_integration_id=data.get("postiz_integration_id"),
        format=data.get("format", "vertical"),
        width=int(data["width"]),
        height=int(data["height"]),
        fps=int(data.get("fps", 30)),
        duration_seconds=float(data["duration_seconds"]),
        language=data.get("language", "pt-BR"),
        caption=data.get("caption"),
        platform_settings=json.dumps(platform_settings) if platform_settings else None,
        publication_mode=publication_mode,
        scheduled_at=scheduled_at,
        scheduled_at_utc=scheduled_at_utc,
        timezone=tz_name,
        status="queued",
        attempt_count=0,
        created_at=now,
        updated_at=now,
    )
    # Do not expose a queued row until its required input exists on disk.
    # A read-only/full volume must return a controlled failure, never an orphan.

    # Scaffold the isolated workspace. Só job_type='social_clip' escreve o
    # manifesto que o OpenCode lê — corte_bruto não passa por composição.
    try:
        base = ensure_job_scaffold(job_id)
        job.workspace_path = str(base)
        if job_type == "social_clip":
            manifest = {
                "job_id": job_id, "title": job.title, "brief": job.brief, "platform": job.platform,
                "format": job.format, "width": job.width, "height": job.height, "fps": job.fps,
                "duration_seconds": job.duration_seconds, "language": job.language, "caption": job.caption,
                "platform_settings": platform_settings or {},
                "project_id": job.project_id, "campaign_id": job.campaign_id,
            }
            (base / "input" / "job.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        db.session.rollback()
        return jsonify({"error": "media_workspace_unavailable", "detail": str(exc)}), 503
    db.session.add(job)
    db.session.commit()

    audit(current_user, "execute", "media_jobs", f"create media job {job_id} ({platform})")
    return jsonify(job.to_dict()), 201


@bp.route("/api/media/jobs/<string:job_id>", methods=["PATCH"])
def update_media_job(job_id):
    """Worker progress-reporting endpoint. Also used for minor pre-run edits
    (title/brief/caption). Any `status` change goes through the same
    transition matrix every other action uses — the worker cannot bypass it.
    """
    denied = _require("execute")
    if denied:
        return denied
    job = MediaJob.query.get_or_404(job_id)
    data = request.get_json() or {}

    target_status = data.get("status")
    if target_status in ("approved", "uploading", "creating_draft", "draft_created", "scheduling", "scheduled", "published") and can_transition(job.status, target_status):
        return jsonify({"error": "dedicated_publication_action_required"}), 403
    release = db.session.get(MediaRelease, job_id)
    if release:
        if release.busy:
            return jsonify({"error": "release_busy"}), 409
        changed = any(field in data and data[field] != getattr(job, field)
                      for field in ("title", "caption", "render_path", "render_sha256")) or target_status is not None
        if changed:
            result = db.session.execute(db.update(MediaRelease).where(
                MediaRelease.job_id == job_id, MediaRelease.busy.is_(False),
            ).values(approved_digest=None, invalidated_reason="job editado; nova revisão/aprovação obrigatória")
              .execution_options(synchronize_session=False))
            if result.rowcount == 0:
                db.session.rollback()
                return jsonify({"error": "release_busy"}), 409
    if target_status:
        try:
            assert_transition(job.status, target_status)
        except InvalidTransition as exc:
            return jsonify({
                "error": "invalid_transition", "detail": str(exc),
                "allowed_from_current": allowed_targets(job.status),
            }), 409
        if target_status == "retryable_failure":
            target_status, job.next_retry_at = failure_state(
                job.attempt_count, str(data.get("last_error") or ""))
        else:
            job.next_retry_at = None
        job.status = target_status
        if target_status in ("ready_for_review", "failed", "cancelled", "retryable_failure"):
            # Worker relinquishes the lock once its portion of the pipeline ends —
            # retryable_failure precisa soltar também: `/run`'s atomic claim exige
            # locked_at IS NULL, então sem isso um job em retryable_failure fica
            # travado pra sempre e o polling do worker nunca consegue reclamá-lo de
            # volta (confirmado em produção: job ficou preso em retryable_failure
            # com o worker rodando e reivindicando outros jobs normalmente).
            job.locked_at = None
            job.locked_by = None

    for field in _WORKER_PATCHABLE_FIELDS:
        if field in data:
            setattr(job, field, data[field])

    job.updated_at = _now()
    db.session.commit()
    audit(current_user, "execute", "media_jobs", f"update media job {job_id}")
    return jsonify(job.to_dict())


# ── Pipeline actions ─────────────────────────────────────────────────────

@bp.route("/api/media/jobs/<string:job_id>/run", methods=["POST"])
def run_media_job(job_id):
    """Atomic claim + (re)start. Used both by a human clicking "Iniciar" and
    by the media-worker's polling loop. Mirrors routes/tickets.py's
    checkout_ticket: the atomicity comes from `WHERE locked_at IS NULL` in a
    raw UPDATE, not from a read-then-write in Python.
    """
    denied = _require("execute")
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    locked_by = data.get("agent") or "media-worker"

    job = MediaJob.query.get_or_404(job_id)

    if job.status == "rejected":
        _transition(job, "queued")
        job.attempt_count = 0
        job.last_error = None
        job.next_retry_at = None
        db.session.commit()

    if job.status not in ("queued", "retryable_failure"):
        return _invalid_transition_response(job, "preparing")

    now = _now()
    if job.attempt_count >= MAX_ATTEMPTS:
        _transition(job, "failed")
        job.locked_at = job.locked_by = job.next_retry_at = None
        db.session.commit()
        return jsonify({"error": "retry_limit_reached", "max_attempts": MAX_ATTEMPTS}), 409
    if job.next_retry_at and job.next_retry_at > now:
        return jsonify({"error": "retry_not_due", "next_retry_at": job.next_retry_at}), 409
    result = db.session.execute(
        db.text(
            "UPDATE media_jobs SET locked_at = :now, locked_by = :agent, "
            "status = 'preparing', updated_at = :now, next_retry_at = NULL, attempt_count = attempt_count + 1 "
            "WHERE id = :id AND locked_at IS NULL AND status IN ('queued','retryable_failure') "
            "AND attempt_count < :max_attempts AND (next_retry_at IS NULL OR next_retry_at <= :now)"
        ),
        {"id": job_id, "agent": locked_by, "now": now, "max_attempts": MAX_ATTEMPTS},
    )
    db.session.commit()
    if result.rowcount == 0:
        db.session.refresh(job)
        return jsonify({
            "error": "already_locked_or_invalid_state",
            "locked_by": job.locked_by, "status": job.status,
        }), 409

    db.session.refresh(job)
    audit(current_user, "execute", "media_jobs", f"run media job {job_id}")
    payload = job.to_dict()
    # Execution intent is the frozen closure snapshot, never worker-writable result_json.
    import models as m
    version = m.RecordingVersion.query.filter_by(job_id=job_id).first()
    if version:
        payload["result"] = json.loads(version.snapshot_json)
    return jsonify(payload)


@bp.route("/api/media/jobs/<string:job_id>/cancel", methods=["POST"])
def cancel_media_job(job_id):
    denied = _require("execute")
    if denied:
        return denied
    job = MediaJob.query.get_or_404(job_id)
    if not can_transition(job.status, "cancelled"):
        return _invalid_transition_response(job, "cancelled")
    release = db.session.get(MediaRelease, job_id)
    if release:
        result = db.session.execute(db.update(MediaRelease).where(
            MediaRelease.job_id == job_id, MediaRelease.busy.is_(False),
        ).values(approved_digest=None, invalidated_reason="job cancelado")
          .execution_options(synchronize_session=False))
        if result.rowcount == 0:
            db.session.rollback()
            return jsonify({"error": "release_busy"}), 409
    _transition(job, "cancelled")
    job.locked_at = None
    job.locked_by = None
    db.session.commit()
    audit(current_user, "execute", "media_jobs", f"cancelled media job {job_id}")
    return jsonify(job.to_dict())


@bp.route("/api/media/jobs/<string:job_id>/approve", methods=["POST"])
def approve_media_job(job_id):
    denied = _require("manage")
    if denied:
        return denied
    job = MediaJob.query.get_or_404(job_id)
    if getattr(g, "auth_via_api_token", False):
        return jsonify({"error": "human_session_required"}), 403
    if db.session.get(MediaRelease, job_id):
        return jsonify({"error": "use_bound_release_approval"}), 409
    if not can_transition(job.status, "approved"):
        return _invalid_transition_response(job, "approved")
    _transition(job, "approved")
    job.approved_at = _now()
    db.session.commit()
    audit(current_user, "manage", "media_jobs", f"approved media job {job_id}")
    return jsonify(job.to_dict())


@bp.route("/api/media/jobs/<string:job_id>/reject", methods=["POST"])
def reject_media_job(job_id):
    denied = _require("manage")
    if denied:
        return denied
    data = request.get_json() or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "reason (comentário) é obrigatório para rejeitar."}), 400
    job = MediaJob.query.get_or_404(job_id)
    if not can_transition(job.status, "rejected"):
        return _invalid_transition_response(job, "rejected")
    _transition(job, "rejected")
    job.reject_reason = reason
    db.session.commit()
    audit(current_user, "manage", "media_jobs", f"rejected media job {job_id}: {reason}")
    return jsonify(job.to_dict())


@bp.route("/api/media/jobs/<string:job_id>/create-draft", methods=["POST"])
@bp.route("/api/media/jobs/<string:job_id>/schedule", methods=["POST"])
def legacy_publication_requires_bound_release(job_id):
    """Do not retain an unbound publication bypass alongside release approvals."""
    denied = _require("manage")
    if denied:
        return denied
    MediaJob.query.get_or_404(job_id)
    return jsonify({"error": "bound_release_required",
                    "detail": "Revise copy/canais/calendário em /release, aprove o digest e use /release/distribute."}), 409


# ── Observability ────────────────────────────────────────────────────────

@bp.route("/api/media/jobs/<string:job_id>/logs")
def get_media_job_logs(job_id):
    denied = _require("view")
    if denied:
        return denied
    job = MediaJob.query.get_or_404(job_id)
    logs: dict[str, str] = {}
    if job.workspace_path:
        logs_dir = Path(job.workspace_path) / "logs"
        if logs_dir.is_dir():
            for f in sorted(logs_dir.glob("*")):
                if f.is_file():
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    logs[f.name] = content[-32 * 1024:]  # tail last 32KB
    return jsonify({
        "job_id": job_id, "status": job.status, "attempt_count": job.attempt_count,
        "last_error": job.last_error, "logs": logs,
    })


@bp.route("/api/media/jobs/<string:job_id>/video")
def get_media_job_video(job_id):
    denied = _require("view")
    if denied:
        return denied
    job = MediaJob.query.get_or_404(job_id)
    if not job.render_path:
        return jsonify({"error": "no_render_available"}), 404

    root = media_workspace_root()
    try:
        resolved = Path(job.render_path).resolve()
        if resolved != root and root not in resolved.parents:
            raise PathSecurityError("render_path fora do workspace de mídia")
    except (OSError, PathSecurityError):
        return jsonify({"error": "invalid_render_path"}), 400
    if not resolved.is_file():
        return jsonify({"error": "file_not_found"}), 404

    # conditional=True makes Flask/Werkzeug handle Range requests (video
    # scrubbing in the browser) and If-Modified-Since automatically.
    return send_file(str(resolved), mimetype="video/mp4", conditional=True, download_name=f"{job_id}.mp4")
