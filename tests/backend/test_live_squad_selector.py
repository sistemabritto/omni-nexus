"""Actual TS presentation contract; no provider or permissions mutation."""
import subprocess
from pathlib import Path

def test_live_squad_selector_contract():
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(['node','qa/live-squad-selector/contract-tests.cjs'],cwd=root,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert 'PASS selector' in result.stdout
