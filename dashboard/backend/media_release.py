"""Bound release approvals and durable distribution using the existing Postiz client.

Unknown create outcomes never retry automatically: Postiz has no idempotency
key in our client contract. Reads/retries with known post IDs cannot create
another post. Callers serialize a release and persist every checkpoint.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from media_workspace import media_workspace_root, sha256_file
from postiz_client import MEDIA_JOB_PLATFORMS, PostizError, PostizAPIError, build_platform_settings, providers_for


class ReleaseError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest_of(snapshot):
    return hashlib.sha256(canonical(snapshot).encode()).hexdigest()


def parse_date(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("timezone required")
        return date.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise ReleaseError("calendário exige ISO-8601 com timezone explícito") from None


def render_binding(job):
    if not job.render_path:
        raise ReleaseError("render ausente")
    path = Path(job.render_path).resolve()
    root = media_workspace_root()
    if root not in path.parents or not path.is_file():
        raise ReleaseError("render fora do workspace ou ausente")
    try:
        checksum = sha256_file(path)
    except OSError:
        raise ReleaseError("render indisponível para conferir SHA-256") from None
    if checksum != job.render_sha256:
        raise ReleaseError("render mudou ou checksum de validação ausente")
    return {"job_id": job.id, "render_sha256": checksum, "render_path": str(path),
            "title": job.title, "caption": job.caption, "platform": job.platform,
            "platform_settings": job.platform_settings, "scheduled_at_utc": job.scheduled_at_utc,
            "publication_mode": job.publication_mode, "integration_id": job.postiz_integration_id}


def make_snapshot(job, data, revision):
    if not isinstance(data, dict) or not isinstance(data.get("channels"), list) or not data["channels"]:
        raise ReleaseError("channels não vazio obrigatório")
    channels, seen = [], set()
    for channel in data["channels"]:
        if not isinstance(channel, dict):
            raise ReleaseError("canal deve ser objeto")
        platform, integration = channel.get("platform"), channel.get("integration_id")
        if platform not in MEDIA_JOB_PLATFORMS or not isinstance(integration, str) or not integration.strip():
            raise ReleaseError("plataforma suportada e integration_id explícitos obrigatórios")
        if integration in seen:
            raise ReleaseError("integration_id duplicado")
        seen.add(integration)
        content = channel.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ReleaseError("copy específica por canal obrigatória")
        date = parse_date(channel.get("scheduled_at_utc"))
        if date <= datetime.now(timezone.utc):
            raise ReleaseError("horário precisa estar no futuro")
        settings = channel.get("settings")
        if settings is None:
            provider = channel.get("provider", providers_for(platform)[0])
            if provider not in providers_for(platform):
                raise ReleaseError("provider incompatível com plataforma")
            kwargs = ({"title": job.title[:100]} if platform == "youtube" else
                      {"standalone": provider == "instagram-standalone"} if platform == "instagram" else
                      {"page": provider == "linkedin-page"} if platform == "linkedin" else {})
            settings = build_platform_settings(platform, **kwargs)
        if not isinstance(settings, dict) or settings.get("__type") not in providers_for(platform):
            raise ReleaseError("settings incompatíveis com canal")
        channels.append({"platform": platform, "integration_id": integration, "content": content,
                         "scheduled_at_utc": date.isoformat().replace("+00:00", "Z"), "settings": settings})
    version = data.get("render_version")
    if not isinstance(version, str) or not version.strip():
        raise ReleaseError("render_version explícita obrigatória")
    return {"revision": revision, "render_version": version, "binding": render_binding(job),
            "channels": sorted(channels, key=lambda c: c["integration_id"])}


def assert_current(job, release):
    from recordings_access import release_readiness_error
    readiness = release_readiness_error(job)
    if readiness:
        raise ReleaseError(readiness)
    if job.status != "approved":
        raise ReleaseError("job precisa da aprovação final da revisão atual")
    snapshot = json.loads(release.snapshot_json)
    if render_binding(job) != snapshot["binding"]:
        raise ReleaseError("render/copy/calendário do job mudou; nova aprovação obrigatória")
    if release.approved_digest != release.digest or digest_of(snapshot) != release.digest or release.invalidated_reason:
        raise ReleaseError("aprovação da revisão atual obrigatória")
    return snapshot


def observe_post(client, channel, post_id):
    date = parse_date(channel["scheduled_at_utc"])
    posts = client.list_posts(((date - timedelta(days=1)).isoformat(), (date + timedelta(days=1)).isoformat()))
    post = next((p for p in posts if p.get("id") == post_id), None)
    if not post:
        return {"state": "awaiting_confirmation", "remote_state": None}
    raw = post.get("state")
    result = {"state": "awaiting_confirmation", "remote_state": raw, "release_url": None}
    if raw == "ERROR":
        result.update(state="remote_error", error=str(post.get("error") or "Postiz ERROR"))
        return result
    # ID alone is insufficient: confirm exact approved copy, account and date.
    try:
        matches = (post.get("integration", {}).get("id") == channel["integration_id"]
                   and post.get("content") == channel["content"]
                   and parse_date(post.get("publishDate")) == date)
    except (ReleaseError, AttributeError):
        matches = False
    if not matches:
        result.update(state="remote_mismatch", error="Postiz diverge da copy/conta/data aprovadas")
        return result
    if raw == "QUEUE":
        result["state"] = "scheduled"
    elif raw == "PUBLISHED":
        result["state"] = "published"
        url = post.get("releaseURL")
        if isinstance(url, str) and urlparse(url).scheme == "https" and urlparse(url).hostname:
            result["release_url"] = url
    return result


def distribute(job, release, client, save, *, refresh_only=False):
    """One serialized pass; save(progress) commits before/after each side effect."""
    snapshot = json.loads(release.snapshot_json) if refresh_only else assert_current(job, release)
    progress = json.loads(release.progress_json)
    channels = progress.setdefault("channels", {})
    if not refresh_only:
        integrations = client.list_integrations()
        for channel in snapshot["channels"]:
            if not any(i.get("id") == channel["integration_id"] and not i.get("disabled")
                       and i.get("identifier") == channel["settings"]["__type"] for i in integrations):
                raise ReleaseError("conta aprovada não está conectada/ativa; nenhuma conta será criada")
    for channel in snapshot["channels"]:
        key = channel["integration_id"]
        entry = channels.setdefault(key, {"state": "pending", "attempts": 0, "post_id": None,
                                          "release_url": None})
        if entry["state"] == "creating_draft":
            entry.update(state="unknown", error="criação interrompida; reconciliar antes de retentar")
            save(progress)
        # A crash or timeout after POST cannot be distinguished from a created post.
        if not refresh_only and entry["state"] in ("unknown", "remote_mismatch", "remote_error"):
            continue
        if entry.get("post_id") and (refresh_only or entry["state"] in ("scheduled", "published", "awaiting_confirmation")):
            try:
                entry.update(observe_post(client, channel, entry["post_id"]))
                if entry["state"] == "remote_mismatch":
                    release.approved_digest = None
                    release.invalidated_reason = "post remoto diverge da aprovação"
            except PostizError as exc:
                entry["error"] = str(exc)
            save(progress)
            continue
        if refresh_only or entry["attempts"] >= 3:
            continue
        if parse_date(channel["scheduled_at_utc"]) <= datetime.now(timezone.utc):
            entry.update(state="calendar_expired", error="nova data exige nova revisão/aprovação")
            release.approved_digest = None
            release.invalidated_reason = "calendário expirou; nova revisão/aprovação obrigatória"
            save(progress)
            break
        assert_current(job, release)
        entry["attempts"] += 1
        save(progress)
        try:
            if not progress.get("media"):
                uploaded = client.upload_file(Path(snapshot["binding"]["render_path"]))
                if not isinstance(uploaded, dict) or not uploaded.get("id") or not uploaded.get("path"):
                    raise PostizError("upload sem id/path")
                progress["media"] = {"id": uploaded["id"], "path": uploaded["path"]}
                save(progress)
            if not entry["post_id"]:
                entry["state"] = "creating_draft"
                save(progress)
                created = client.create_draft(integration_id=key, content=channel["content"],
                    media=[progress["media"]], settings=channel["settings"], now_iso_utc=channel["scheduled_at_utc"])
                ids = [item.get("postId") for item in created
                       if isinstance(item, dict) and isinstance(item.get("postId"), str) and item["postId"]]
                entry["observed_post_ids"] = ids
                save(progress)
                if len(ids) != 1:
                    raise PostizError("resposta de criação ambígua; reconciliar antes de retentar")
                entry.update(post_id=ids[0], state="draft_created")
                save(progress)
            assert_current(job, release)  # render bytes must still match before enabling schedule
            if parse_date(channel["scheduled_at_utc"]) <= datetime.now(timezone.utc):
                entry.update(state="calendar_expired", error="horário expirou durante upload/draft; não agendado")
                release.approved_digest = None
                release.invalidated_reason = "calendário expirou; nova revisão/aprovação obrigatória"
                save(progress)
                break
            entry["state"] = "scheduling"
            save(progress)
            client.change_status(entry["post_id"], "schedule")
            entry["state"] = "awaiting_confirmation"
            save(progress)
            entry.update(observe_post(client, channel, entry["post_id"]))
            if entry["state"] == "remote_mismatch":
                release.approved_digest = None
                release.invalidated_reason = "post remoto diverge da aprovação"
        except PostizError as exc:
            rejected = isinstance(exc, PostizAPIError) and exc.status_code in (400, 401, 403, 404, 422, 429)
            entry["state"] = ("retryable_failure" if entry.get("post_id") or rejected
                              or entry["state"] != "creating_draft" else "unknown")
            entry["error"] = str(exc)
        save(progress)
    return progress
