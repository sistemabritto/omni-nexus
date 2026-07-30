"""provider_fallback.py::_build_agent_run_env — IS_SANDBOX.

Achado ao vivo em 30/07/2026 investigando por que o bot do Telegram parecia
"burro": claude/openclaude recusam --dangerously-skip-permissions rodando
como root sem IS_SANDBOX=1 no ambiente, e todo container desta esteira
(telegram, media-worker, dashboard) roda como root. IS_SANDBOX nunca era
setado em lugar nenhum — nem no Dockerfile, nem em _build_agent_run_env —
então qualquer chamada que caísse em cli_command claude/openclaude falhava
sempre com "cannot be used with root/sudo privileges for security reasons".
Confirmado ao vivo: force_provider="anthropic" no container real do
Telegram só passou a funcionar depois deste fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import provider_fallback as pf


def test_build_agent_run_env_seta_is_sandbox(monkeypatch):
    monkeypatch.delenv("IS_SANDBOX", raising=False)
    env = pf._build_agent_run_env()
    assert env["IS_SANDBOX"] == "1"


def test_build_agent_run_env_respeita_is_sandbox_ja_setado(monkeypatch):
    """setdefault, não sobrescrita — se algum dia precisar desligar
    explicitamente (IS_SANDBOX=0), este código não pode forçar de volta."""
    monkeypatch.setenv("IS_SANDBOX", "0")
    env = pf._build_agent_run_env()
    assert env["IS_SANDBOX"] == "0"
