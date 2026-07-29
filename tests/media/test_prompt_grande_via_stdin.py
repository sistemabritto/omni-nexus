"""tests/media/test_prompt_grande_via_stdin.py

2026-07-29 — regressão do bug real que travou o segundo job de
`cortes_virais` em produção, já com o `force_provider="opencode"` aplicado:
`[Errno 7] Argument list too long: '/usr/local/bin/opencode'`. A transcrição
de um vídeo de 3h02 (~30 mil palavras) embutida no prompt via
`formatar_para_selecao` passa de centenas de KB — argv+envp compartilham o
ARG_MAX do kernel, e um prompt desse tamanho como argumento literal de CLI
estoura isso sempre, em qualquer um dos três binários (claude/openclaude/
opencode), não só opencode.

Fix em `provider_fallback.py::_invoke_cli`: acima de `PROMPT_ARG_SAFE_BYTES`
o prompt sai do argv e vai por stdin — leitura suportada nativamente por
`claude --print` e `opencode run` quando o prompt/mensagem posicional não é
passado.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import provider_fallback as pf

PROMPT_GIGANTE = "x " * (pf.PROMPT_ARG_SAFE_BYTES // 2 + 1000)  # > 100KB
PROMPT_PEQUENO = "responda apenas OK"


def _run_capturado(cli_command, **kwargs):
    """Roda _invoke_cli mas intercepta o Popen pra inspecionar cmd/stdin sem
    executar um binário de verdade."""
    captured = {}

    class _FakeProc:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            captured["stdin"] = input
            return ('{"type":"text","text":"ok"}\n' if cli_command == "opencode" else '{"result":"ok"}', "")

    def _fake_popen(cmd, **popen_kwargs):
        captured["cmd"] = cmd
        captured["popen_kwargs"] = popen_kwargs
        return _FakeProc()

    with patch("subprocess.Popen", side_effect=_fake_popen), \
         patch.object(pf.shutil, "which", return_value=f"/usr/local/bin/{cli_command}"), \
         patch.object(pf, "_model_lock") as mock_lock:
        mock_lock.return_value.acquire.return_value = True
        pf._invoke_cli(cli_command=cli_command, provider_id="opencode", model="auto", **kwargs)
    return captured


def test_prompt_grande_sai_do_argv_vai_por_stdin_opencode():
    captured = _run_capturado("opencode", prompt=PROMPT_GIGANTE, max_turns=10, timeout_seconds=60)
    assert PROMPT_GIGANTE not in captured["cmd"]
    assert captured["stdin"] == pf._embed_agent_for_openclaude(PROMPT_GIGANTE, "")
    assert captured["popen_kwargs"]["stdin"] is not None


def test_prompt_pequeno_continua_no_argv_opencode():
    captured = _run_capturado("opencode", prompt=PROMPT_PEQUENO, max_turns=10, timeout_seconds=60)
    assert any(PROMPT_PEQUENO in str(c) for c in captured["cmd"])
    assert captured["stdin"] is None


def test_prompt_grande_sai_do_argv_vai_por_stdin_claude():
    captured = _run_capturado("claude", prompt=PROMPT_GIGANTE, max_turns=10, timeout_seconds=60)
    assert not any(PROMPT_GIGANTE == c for c in captured["cmd"])
    assert "--" not in captured["cmd"][-2:]
    assert captured["stdin"] == PROMPT_GIGANTE


def test_prompt_pequeno_continua_no_argv_claude():
    captured = _run_capturado("claude", prompt=PROMPT_PEQUENO, max_turns=10, timeout_seconds=60)
    assert captured["cmd"][-2:] == ["--", PROMPT_PEQUENO]
    assert captured["stdin"] is None
