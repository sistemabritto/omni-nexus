"""Contract checks for image destinations, event boundaries and immutable source."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("image_targets", ROOT / "scripts/ci/image_targets.py")
targets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(targets)


@pytest.mark.parametrize("target,names", [
    ("all", {"evo-nexus-runtime", "evo-nexus-dashboard", "evo-nexus-media-worker"}),
    ("core", {"evo-nexus-runtime", "evo-nexus-dashboard"}),
    ("dashboard", {"evo-nexus-dashboard"}),
    ("media-worker", {"evo-nexus-media-worker"}),
    ("media", {"evo-nexus-dashboard", "evo-nexus-media-worker"}),
])
def test_manual_targets_are_exact_and_have_real_dockerfiles(target, names):
    rows = targets.select_images("workflow_dispatch", "refs/heads/review/test", target)
    assert {row["image"] for row in rows} == names
    assert len(rows) == len(names)
    assert all((ROOT / row["dockerfile"]).is_file() for row in rows)


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/tags/v1.2.3", "refs/tags/rc12"])
def test_release_events_publish_one_coherent_three_image_revision(ref):
    rows = targets.select_images("push", ref, "dashboard")
    assert {row["image"] for row in rows} == {
        "evo-nexus-dashboard", "evo-nexus-runtime", "evo-nexus-media-worker",
    }


@pytest.mark.parametrize("event,ref,target", [
    ("pull_request", "refs/pull/1/merge", "all"),
    ("push", "refs/heads/review/test", "all"),
    ("push", "refs/tags/random", "all"),
    ("workflow_dispatch", "unresolved", "all"),
    ("workflow_dispatch", "refs/heads/main", "omniroute"),
    ("workflow_dispatch", "refs/heads/main", "evoapicloud"),
])
def test_unsupported_events_refs_and_targets_fail_closed(event, ref, target):
    with pytest.raises(ValueError):
        targets.select_images(event, ref, target)


def test_resolver_exports_exact_revision_and_matrix(tmp_path, monkeypatch):
    output = tmp_path / "outputs"
    sha = "a" * 40
    for name, value in {"SOURCE_SHA": sha, "SOURCE_REF": "refs/heads/review/test",
                        "EVENT_NAME": "workflow_dispatch", "IMAGE_TARGET": "media-worker",
                        "GITHUB_OUTPUT": str(output)}.items():
        monkeypatch.setenv(name, value)
    targets.main()
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["revision"] == sha
    assert json.loads(values["matrix"])["include"] == [{
        "image": "evo-nexus-media-worker", "dockerfile": "Dockerfile.media-worker",
    }]
    monkeypatch.setenv("SOURCE_SHA", "main")
    with pytest.raises(ValueError):
        targets.main()


def test_workflow_has_one_fixed_destination_and_no_legacy_publisher():
    assert not (ROOT / ".github/workflows/docker-publish.yml").exists()
    path = ROOT / ".github/workflows/docker-publish-britto.yml"
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert workflow["env"] == {"REGISTRY": "docker.io", "NAMESPACE": "excarplex"}
    assert workflow["on"]["push"] == {"branches": ["main"], "tags": ["v*", "rc*"]}
    assert set(workflow["on"]["workflow_dispatch"]["inputs"]["target"]["options"]) == set(targets.TARGETS)
    assert workflow["concurrency"] == {
        "group": "omninexus-image-publication", "queue": "max", "cancel-in-progress": "false",
    }
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert jobs["prepare"]["steps"][0]["with"]["ref"] == "${{ github.sha }}"
    steps = jobs["build-and-push"]["steps"]
    assert steps[0]["with"]["ref"] == "${{ needs.prepare.outputs.revision }}"
    metadata = next(step for step in steps if step.get("id") == "meta")
    assert metadata["with"]["images"] == "${{ env.REGISTRY }}/${{ env.NAMESPACE }}/${{ matrix.image }}"
    assert "org.opencontainers.image.revision=${{ needs.prepare.outputs.revision }}" in metadata["with"]["labels"]
    build = next(step for step in steps if step.get("id") == "build")
    assert build["with"]["push"] == "true"
    assert build["with"]["context"] == "."
    assert "secrets." not in build["with"]["build-args"]
    assert not any("evoapicloud" in p.read_text() for p in (ROOT / ".github/workflows").glob("*.yml"))
    ignored = set((ROOT / ".dockerignore").read_text().splitlines())
    assert {".env", ".git/", ".claude/.env"}.issubset(ignored)
