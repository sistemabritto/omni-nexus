"""Fixture-driven decisions and real media API planning, without media/network."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from media_editorial import EditorialPlanError, build_editorial_plan, source_to_edited

FIXTURES = Path(__file__).parent / "fixtures/editorial"


def fixture(mode="personal_footage"):
    return json.loads((FIXTURES / f"{mode}.json").read_text())


@pytest.mark.parametrize("mode,entry", [("faceless_montage", "social_clip"), ("personal_footage", "corte_bruto")])
def test_real_api_selects_existing_workflow_without_queue_or_provider(admin_client, app, monkeypatch, mode, entry):
    import routes.media_jobs as routes
    provider = Mock(side_effect=AssertionError("No Postiz in planning"))
    monkeypatch.setattr(routes.PostizClient, "from_env", provider)
    data = fixture(mode)
    data.update({"approved": True, "approver": "Felipe", "schedule": "now"})
    response = admin_client.post("/api/media/editorial/plan", json=data)
    assert response.status_code == 200
    plan = response.get_json()
    assert plan["workflow"]["entry_job_type"] == entry
    assert plan["state"] == "awaiting_beat_sheet_review"
    assert not plan["execution_limits"]["auto_queue"]
    assert not plan["execution_limits"]["auto_schedule"]
    assert plan["release_gates"][-2:] == ["felipe_final_approval", "destination_and_schedule_authorization"]
    assert admin_client.get("/api/media/jobs").get_json() == []
    provider.assert_not_called()
    # The selected entry maps to an actual existing API type, not a dead label.
    # This is a simulated subsequent human handoff; no worker is running here.
    body = {"title": plan["title"], "job_type": entry}
    if mode == "personal_footage":
        body["source_path"] = "/authorized-test-input/raw.mp4"
    else:
        body.update(platform="instagram", width=720, height=1280, duration_seconds=5)
    created = admin_client.post("/api/media/jobs", json=body)
    assert created.status_code == 201
    assert created.get_json()["job_type"] == entry
    assert created.get_json()["status"] == "queued"
    assert admin_client.post(f"/api/media/jobs/{created.get_json()['id']}/schedule").status_code == 409


def test_removed_time_and_caption_sync():
    plan = build_editorial_plan(fixture())
    assert plan["edited_duration_seconds"] == 5
    assert source_to_edited(plan["time_map"], 0) is None
    assert source_to_edited(plan["time_map"], 3) is None
    assert source_to_edited(plan["time_map"], 5) == 2
    assert source_to_edited(plan["time_map"], 7) == 4
    assert plan["captions"] == [{"word": "OmniNexus", "start": 0, "end": 1},
                                 {"word": "ajuda", "start": 2, "end": 3}]


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(mode="guess"),
    lambda d: d.update(source_asset="missing"),
    lambda d: d["assets"][0].update(rights="unknown"),
    lambda d: d["assets"][0].update(path="../../private.mp4"),
    lambda d: d["assets"][0].update(path="/etc/passwd"),
    lambda d: d["assets"][0].update(rights_evidence=""),
    lambda d: d.update(keep=[{"start":1.5,"end":3}]),
    lambda d: d.update(keep=[{"start":0,"end":5.5}]),
    lambda d: d.update(keep=[{"start":5,"end":8},{"start":1,"end":3}]),
    lambda d: d.update(keep=[]),
    lambda d: d.update(source_duration_seconds=float("nan")),
    lambda d: d["words"][0].update(start=True),
    lambda d: d.update(beats=[]),
    lambda d: d["beats"][0].update(end=100),
    lambda d: d["beats"][0]["elements"][0].update(word_index=1),
    lambda d: d["beats"][1]["elements"][0].update(asset="unlicensed"),
    lambda d: d.update(revision=2),
    lambda d: d.update(face_box={"x":0.8,"y":0,"width":0.3,"height":0.5}),
    lambda d: d.update(transcription={"engine":"elevenlabs"}),
    lambda d: d.update(transcription={"engine":"whisper_local","model":"small.en"}),
])
def test_invalid_editorial_contracts_fail_closed(mutation):
    data = fixture()
    mutation(data)
    with pytest.raises(EditorialPlanError):
        build_editorial_plan(data)


def test_transition_cannot_split_kept_word():
    data = fixture()
    data["beats"][0]["elements"].append({"kind":"transition", "position":"full frame", "start":0.5,"end":1.5})
    with pytest.raises(EditorialPlanError, match="transição divide"):
        build_editorial_plan(data)


def test_prior_revision_and_local_transcription_are_explicit():
    data = fixture()
    data.update(revision=2, previous_revision=1, transcription={"engine":"whisper_local","model":"small"})
    plan = build_editorial_plan(data)
    assert plan["previous_revision"] == 1
    assert plan["transcription"]["engine"] == "whisper_local"
    assert plan["face_tracking"] is False
    assert plan["frame_sampling"]["max_frames"] == 80


def test_viewer_cannot_plan(viewer_client):
    assert viewer_client.post("/api/media/editorial/plan", json=fixture()).status_code == 403


@pytest.mark.parametrize("data", [None, [], {"mode":[]}, {"mode":"personal_footage"}])
def test_bad_api_payload_is_400_not_500(admin_client, data):
    assert admin_client.post("/api/media/editorial/plan", json=data).status_code == 400


def test_silent_faceless_and_time_map_invalidation():
    data = fixture("faceless_montage")
    data["words"] = []
    for beat in data["beats"]:
        for element in beat["elements"]:
            element.pop("word_index", None)
    plan = build_editorial_plan(data)
    assert plan["captions"] == []
    assert plan["time_map_scope"]["refresh_after_any_additional_cut"] is True


def test_whole_word_removal_does_not_leave_stale_caption():
    data = fixture()
    data["keep"] = [{"start": 5, "end": 8}]
    data["beats"] = [{"start":0,"end":3,"speech":"ajuda","sound":"voz","elements":[]}]
    plan = build_editorial_plan(data)
    assert plan["captions"] == [{"word":"ajuda","start":0,"end":1}]
    assert source_to_edited(plan["time_map"], 1) is None
