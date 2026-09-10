import importlib.util
from pathlib import Path
import pytest


def test_summary_propagates_failed_step_to_scheduler():
    spec = importlib.util.spec_from_file_location("routine_runner_audit", Path(__file__).resolve().parents[2] / "ADWs/runner.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    with pytest.raises(SystemExit) as error:
        runner.summary([{"success": False, "duration": 0}], "test")
    assert error.value.code == 1
    assert runner.summary([{"success": True, "duration": 0}], "test") is None
