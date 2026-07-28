"""
tests/backend/test_cota_esgotada.py

2026-07-28 — a cota do Claude Code acaba e nada rotaciona.

O texto que o CLI devolve quando o limite mensal estoura é "You've hit your
monthly spend limit · raise it at claude.ai/settings/usage?from=cc_cli_limit_message".
Nenhuma das palavras que o motor de fallback procurava (429, "rate limit",
"quota") aparece ali, então `is_429_error` respondia False e a rotina/heartbeat
morria em vez de tentar o próximo provider.

O par deste teste no chat é
`dashboard/terminal-server/test/chat-bridge-fallback.test.js`.

Run:
    pytest tests/backend/test_cota_esgotada.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from provider_fallback import is_429_error  # noqa: E402

COTA_MENSAL = (
    "Claude Code returned an error result: You've hit your monthly spend limit "
    "· raise it at claude.ai/settings/usage?from=cc_cli_limit_message"
)


@pytest.mark.parametrize("texto", [
    COTA_MENSAL,
    "Claude AI usage limit reached",
    "You've hit your weekly limit",
    "Your credit balance is too low to run this request",
])
def test_cota_esgotada_rotaciona(texto):
    assert is_429_error(texto), "cota esgotada precisa avançar a cadeia de providers"


def test_cota_esgotada_nao_e_erro_de_credencial():
    """Fatal encerra a rotação; cota esgotada tem de continuar rotacionando.

    A distinção importa: chave inválida não melhora trocando de modelo, mas
    cota estourada de um provider é exatamente o caso em que outro resolve.
    """
    assert is_429_error(COTA_MENSAL) is True


@pytest.mark.parametrize("texto", [
    "401 Unauthorized: invalid api key",
    "SyntaxError: unexpected token",
    "",
])
def test_o_que_nao_deve_rotacionar(texto):
    assert not is_429_error(texto)
