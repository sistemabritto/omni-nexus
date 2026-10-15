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


def test_manifest_handoff_through_approval_and_schedule(admin_client, monkeypatch):
    """Simulate the agent/render and Postiz; exercise the real API/state machine."""
    import json
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock

    import media_executor
    import routes.media_jobs as routes

    postiz = Mock()
    postiz.upload_file.return_value = {"id": "media-1", "path": "https://media.invalid/final.mp4", "name": "final.mp4"}
    postiz.select_integration.return_value = {"id": "test-only"}
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
        assert admin_client.patch(url, json={"status": state, "render_path": str(render)}).status_code == 200
    assert admin_client.post(url + "/create-draft").status_code == 409
    postiz.upload_file.assert_not_called()
    assert admin_client.post(url + "/approve").status_code == 200
    assert admin_client.post(url + "/create-draft").status_code == 200
    assert admin_client.post(url + "/create-draft").status_code == 200
    postiz.upload_file.assert_called_once()
    postiz.create_draft.assert_called_once()
    assert postiz.create_draft.call_args.kwargs["now_iso_utc"] == job["scheduled_at_utc"]
    scheduled = admin_client.post(url + "/schedule")
    assert scheduled.status_code == 200
    assert scheduled.get_json()["status"] == "scheduled"
    postiz.change_status.assert_called_once_with("simulated-post", "schedule")
