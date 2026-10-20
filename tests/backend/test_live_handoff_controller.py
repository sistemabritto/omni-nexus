import subprocess
from pathlib import Path


def test_handoff_controller_all_personas_and_failure_paths():
    result=subprocess.run(['node','qa/managed-live-context/handoff-tests.cjs'],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
