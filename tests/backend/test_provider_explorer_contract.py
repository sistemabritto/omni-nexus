"""Keep the Flask/TypeScript integration contract in the existing offline CI lane."""
import os
from pathlib import Path
import subprocess
import sys


def test_actual_backend_payloads_are_accepted_by_shipped_provider_client():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["node", "qa/providers-explorer/backend-client-tests.cjs"], cwd=root,
        env={**os.environ, "QA_PYTHON": sys.executable}, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS actual Flask routes + shipped TS client" in result.stdout
