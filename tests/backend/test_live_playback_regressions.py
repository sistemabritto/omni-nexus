"""Exercise actual Playback/ManagedSession + installed SDK with synthetic IO in CI."""
import json
from pathlib import Path
import subprocess


def test_playback_order_interruption_and_lifecycle_regressions():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["node", "qa/managed-live-context/playback-regression-audit.cjs"],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["provider_calls"] == 0 and report["hardware_audio"] is False
    assert len(report["checks"]) == 12
    assert all(check["status"] == "PASS" for check in report["checks"])
