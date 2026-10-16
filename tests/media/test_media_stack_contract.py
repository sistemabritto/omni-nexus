"""The API producer and worker consumer must share writable persistent media.

No Docker daemon, model, credential, or production service is used here.
"""
from pathlib import Path

import yaml


STACK = Path(__file__).resolve().parents[2] / "evonexus-vps.stack.yml"


def test_dashboard_and_worker_share_writable_media_workspace():
    stack = yaml.safe_load(STACK.read_text())
    for name in ("evonexus_dashboard", "evonexus_media_worker"):
        service = stack["services"][name]
        mounts = [value.split(":") for value in service["volumes"]]
        media = [mount for mount in mounts if mount[1] == "/workspace/media"]
        assert len(media) == 1, f"{name} needs one persistent media mount"
        assert media[0][0] == "evonexus_media"
        assert len(media[0]) == 2 or media[0][2] == "rw", f"{name} must write media"
        assert "MEDIA_WORKSPACE=/workspace/media" in service["environment"]
    assert "evonexus_media" in stack["volumes"]


def test_manifest_handoff_through_approval_and_schedule(admin_client, monkeypatch, tmp_path):
    """Simulate the agent/render and Postiz; exercise the real API/state machine."""
    import json
    import hashlib
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock

    import media_executor
    import routes.media_jobs as routes

    # Do not inherit a host catalog symlink: fixtures write only under tmp_path.
    monkeypatch.setenv("MEDIA_SKILLS_DIR", str(tmp_path / "unmounted-fixture-catalog"))

    postiz = Mock()
    postiz.upload_file.return_value = {"id": "media-1", "path": "https://media.invalid/final.mp4", "name": "final.mp4"}
    postiz.list_integrations.return_value = [{"id":"test-only","identifier":"instagram"}]
    postiz.create_draft.return_value = [{"postId": "simulated-post"}]
    monkeypatch.setattr(routes.PostizClient, "from_env", lambda: postiz)

    when = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
    created = admin_client.post("/api/media/jobs", json={
        "title": "Simulated media handoff", "platform": "instagram", "width": 720,
        "height": 1280, "fps": 30, "duration_seconds": 6,
        "publication_mode": "schedule", "scheduled_at": when, "timezone": "UTC",
    })
    assert created.status_code == 201
    job = created.get_json()
    base = Path(job["workspace_path"])
    # This simulated worker still needs the real scoped instruction documents.
    root = Path(__file__).resolve().parents[2]
    for relative in media_executor.REQUIRED_SKILL_DOCUMENTS:
        name = Path(relative).parts[-2]
        source = root / '.claude' / ('skills' if name == 'social-media-production' else 'skills-media') / name / 'SKILL.md'
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    url = f"/api/media/jobs/{job['id']}"

    def agent(**kwargs):
        assert kwargs["cwd"] == base
        manifest = json.loads((kwargs["cwd"] / "input/job.json").read_text())
        assert manifest["job_id"] == job["id"]
        (base / "output/publication_manifest.json").write_text(json.dumps(manifest))
        return {"status": "success"}

    monkeypatch.setattr(media_executor, "invoke_with_fallback", agent)
    assert admin_client.post(url + "/run", json={"agent": "simulated-worker"}).status_code == 200
    media_executor.run_opencode_media_job(base)
    render = base / "output/final.mp4"
    render.write_bytes(b"simulated-render-not-real-video")
    # No real render/ffprobe is run: this test simulates the worker's result.
    for state in ("generating", "rendering", "validating", "ready_for_review"):
        assert admin_client.patch(url, json={"status": state, "render_path": str(render), "render_sha256": hashlib.sha256(render.read_bytes()).hexdigest()}).status_code == 200
    assert admin_client.post(url + "/create-draft").status_code == 409
    postiz.upload_file.assert_not_called()
    # Legacy approval alone must not enable a draft or schedule after PR56.
    assert admin_client.post(url + "/approve").status_code == 200
    assert admin_client.post(url + "/create-draft").get_json()["error"] == "bound_release_required"
    assert admin_client.post(url + "/schedule").status_code == 409
    postiz.upload_file.assert_not_called()
    release = admin_client.put(url + "/release", json={"render_version":"simulated-v1","channels":[{
        "platform":"instagram","integration_id":"test-only","content":"Copy explicitamente revisada",
        "scheduled_at_utc":job["scheduled_at_utc"],
    }]})
    assert release.status_code == 200
    assert admin_client.post(url + "/release/approve",json={"digest":release.get_json()["digest"]}).status_code == 200
    postiz.list_posts.return_value = [{"id":"simulated-post","state":"QUEUE",
        "content":"Copy explicitamente revisada","publishDate":job["scheduled_at_utc"],"integration":{"id":"test-only"}}]
    distributed = admin_client.post(url + "/release/distribute")
    assert distributed.status_code == 200
    assert distributed.get_json()["progress"]["channels"]["test-only"]["state"] == "scheduled"
    assert admin_client.post(url + "/release/distribute").status_code == 200
    postiz.upload_file.assert_called_once()
    postiz.create_draft.assert_called_once()
    assert datetime.fromisoformat(postiz.create_draft.call_args.kwargs["now_iso_utc"].replace("Z","+00:00")) == datetime.fromisoformat(job["scheduled_at_utc"].replace("Z","+00:00"))
    postiz.change_status.assert_called_once_with("simulated-post", "schedule")
