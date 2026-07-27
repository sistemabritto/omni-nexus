"""Tests for heartbeat schema validation (pydantic + YAML)."""

import sys
import textwrap
import tempfile
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_yaml(content: str) -> Path:
    """Write YAML content to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.flush()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# Schema validation — valid cases
# ---------------------------------------------------------------------------

def test_valid_minimal_heartbeat():
    """A minimal valid heartbeat config should load without error."""
    from heartbeat_schema import HeartbeatConfig

    hb = HeartbeatConfig.model_validate({
        "id": "test-1h",
        "agent": "atlas-project",
        "interval_seconds": 3600,
        "wake_triggers": ["interval", "manual"],
        "decision_prompt": "You are Atlas. Decide if there is work to do.",
    })
    assert hb.id == "test-1h"
    assert hb.agent == "atlas-project"
    assert hb.interval_seconds == 3600
    assert hb.enabled is False  # default
    assert hb.max_turns == 10  # default


def test_valid_all_wake_triggers():
    """All 5 wake trigger types should be accepted."""
    from heartbeat_schema import HeartbeatConfig

    hb = HeartbeatConfig.model_validate({
        "id": "full-triggers",
        "agent": "zara-cs",
        "interval_seconds": 7200,
        "wake_triggers": ["interval", "new_task", "mention", "manual", "approval_decision"],
        "decision_prompt": "Check everything and decide what to do next.",
    })
    assert len(hb.wake_triggers) == 5


def test_valid_seeds_from_yaml():
    """The seed heartbeats shipped with the repo should parse, all disabled.

    Reads heartbeats.example.yaml explicitly. It used to call
    load_heartbeats_yaml() with no argument, which prefers the operator's own
    config/heartbeats.yaml when present — so on any machine that had actually
    configured heartbeats, this test asserted things about a personal file it
    has no business policing, and failed for the right reason on the wrong
    subject. The example is what a fresh install gets, and that is the thing
    that must never wake an agent without an explicit opt-in.
    """
    from heartbeat_schema import load_heartbeats_yaml

    example = REPO_ROOT / "config" / "heartbeats.example.yaml"
    cfg = load_heartbeats_yaml(path=example, include_plugins=False)
    assert len(cfg.heartbeats) >= 3

    ids = [h.id for h in cfg.heartbeats]
    assert "atlas-4h" in ids
    assert "zara-2h" in ids
    assert "flux-6h" in ids

    ligados = [h.id for h in cfg.heartbeats if h.enabled]
    assert ligados == [], f"seeds ligados por padrão: {ligados}"


def test_seeds_interval_values():
    """Verify seed intervals match spec."""
    from heartbeat_schema import load_heartbeats_yaml

    cfg = load_heartbeats_yaml()
    by_id = {h.id: h for h in cfg.heartbeats}

    assert by_id["atlas-4h"].interval_seconds == 14400   # 4h
    assert by_id["zara-2h"].interval_seconds == 7200     # 2h
    assert by_id["flux-6h"].interval_seconds == 21600    # 6h


# ---------------------------------------------------------------------------
# Schema validation — invalid cases
# ---------------------------------------------------------------------------

def test_invalid_interval_below_minimum():
    """interval_seconds < 60 should raise ValidationError."""
    from pydantic import ValidationError
    from heartbeat_schema import HeartbeatConfig

    with pytest.raises(ValidationError) as exc_info:
        HeartbeatConfig.model_validate({
            "id": "too-fast",
            "agent": "atlas-project",
            "interval_seconds": 30,  # below minimum
            "wake_triggers": ["interval"],
            "decision_prompt": "Short but invalid decision prompt here.",
        })
    errors = exc_info.value.errors()
    assert any("interval_seconds" in str(e) for e in errors)


def test_invalid_id_with_spaces():
    """ID with spaces should fail pattern validation."""
    from pydantic import ValidationError
    from heartbeat_schema import HeartbeatConfig

    with pytest.raises(ValidationError):
        HeartbeatConfig.model_validate({
            "id": "has spaces",
            "agent": "atlas-project",
            "interval_seconds": 3600,
            "wake_triggers": ["manual"],
            "decision_prompt": "Valid decision prompt text here.",
        })


def test_invalid_empty_wake_triggers():
    """Empty wake_triggers list should fail min_length validation."""
    from pydantic import ValidationError
    from heartbeat_schema import HeartbeatConfig

    with pytest.raises(ValidationError) as exc_info:
        HeartbeatConfig.model_validate({
            "id": "no-triggers",
            "agent": "atlas-project",
            "interval_seconds": 3600,
            "wake_triggers": [],
            "decision_prompt": "Valid decision prompt text here, long enough.",
        })
    errors = exc_info.value.errors()
    assert any("wake_triggers" in str(e) for e in errors)


def test_invalid_decision_prompt_too_short():
    """decision_prompt < 20 chars should fail."""
    from pydantic import ValidationError
    from heartbeat_schema import HeartbeatConfig

    with pytest.raises(ValidationError) as exc_info:
        HeartbeatConfig.model_validate({
            "id": "short-prompt",
            "agent": "atlas-project",
            "interval_seconds": 3600,
            "wake_triggers": ["manual"],
            "decision_prompt": "Too short.",  # only 10 chars
        })
    errors = exc_info.value.errors()
    assert any("decision_prompt" in str(e) for e in errors)


def test_invalid_nonexistent_agent():
    """Agent that doesn't exist as .claude/agents/{agent}.md should fail."""
    from pydantic import ValidationError
    from heartbeat_schema import HeartbeatConfig

    with pytest.raises(ValidationError) as exc_info:
        HeartbeatConfig.model_validate({
            "id": "bad-agent",
            "agent": "nonexistent-agent-xyz",
            "interval_seconds": 3600,
            "wake_triggers": ["manual"],
            "decision_prompt": "Valid decision prompt text here, long enough.",
        })
    errors = exc_info.value.errors()
    assert any("agent" in str(e).lower() or "Agent" in str(e) for e in errors)


def test_invalid_unknown_wake_trigger():
    """Unknown wake trigger value should fail."""
    from pydantic import ValidationError
    from heartbeat_schema import HeartbeatConfig

    with pytest.raises(ValidationError):
        HeartbeatConfig.model_validate({
            "id": "bad-trigger",
            "agent": "atlas-project",
            "interval_seconds": 3600,
            "wake_triggers": ["interval", "webhook_external"],  # not allowed
            "decision_prompt": "Valid decision prompt text here, long enough.",
        })


def test_duplicate_ids_in_file():
    """Duplicate IDs in the heartbeats file should fail."""
    from pydantic import ValidationError
    from heartbeat_schema import HeartbeatsFile, HeartbeatConfig

    hb1 = {
        "id": "same-id",
        "agent": "atlas-project",
        "interval_seconds": 3600,
        "wake_triggers": ["manual"],
        "decision_prompt": "Valid decision prompt text here, long enough.",
    }
    hb2 = {
        "id": "same-id",  # duplicate
        "agent": "zara-cs",
        "interval_seconds": 7200,
        "wake_triggers": ["manual"],
        "decision_prompt": "Another valid decision prompt text here too.",
    }

    with pytest.raises(ValidationError) as exc_info:
        HeartbeatsFile.model_validate({"heartbeats": [hb1, hb2]})
    assert "Duplicate" in str(exc_info.value)


# ---------------------------------------------------------------------------
# YAML atomic write
# ---------------------------------------------------------------------------

def test_atomic_yaml_write_and_read():
    """save_heartbeats_yaml → load_heartbeats_yaml round-trip."""
    from heartbeat_schema import HeartbeatConfig, HeartbeatsFile, save_heartbeats_yaml, load_heartbeats_yaml

    hb = HeartbeatConfig.model_validate({
        "id": "write-test",
        "agent": "atlas-project",
        "interval_seconds": 3600,
        "wake_triggers": ["manual"],
        "decision_prompt": "Valid decision prompt text here, long enough.",
    })
    file_data = HeartbeatsFile(heartbeats=[hb])

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "heartbeats.yaml"
        save_heartbeats_yaml(file_data, path)

        # File must exist
        assert path.exists()
        # No temp file left over
        tmp_path = path.with_suffix(".yaml.tmp")
        assert not tmp_path.exists()

        # Round-trip
        loaded = load_heartbeats_yaml(path)
        assert len(loaded.heartbeats) == 1
        assert loaded.heartbeats[0].id == "write-test"
        assert loaded.heartbeats[0].interval_seconds == 3600


def test_empty_yaml_returns_empty_file():
    """Missing or empty YAML file should return HeartbeatsFile with no heartbeats."""
    from heartbeat_schema import load_heartbeats_yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "missing.yaml"
        cfg = load_heartbeats_yaml(path)
        assert cfg.heartbeats == []
