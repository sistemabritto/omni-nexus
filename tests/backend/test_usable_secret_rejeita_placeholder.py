"""tests/backend/test_usable_secret_rejeita_placeholder.py

2026-08-26 — `_usable_secret()` deixava passar placeholder truncado.

`config/providers.json` tinha `OPENAI_API_KEY: "sk-761...3957"` (13
caracteres, pontos literais) para o `omnirouter` E o `opencode`, e a função
só filtrava `[REDACTED]`/`REDACTED`. O gateway (OmniRoute) não valida chave
nenhuma, então a chave falsa passava direto e ninguém percebia — o `/v1`
ficou exposto publicamente sem NENHUM consumidor interno mandando uma chave
de verdade. Reticências literais (`...`) são o padrão de todo placeholder
truncado neste arquivo (`sk-or-...de1c`, `sk-...`); nenhuma chave real do
OpenAI/OmniRoute as contém.

Run:
    pytest tests/backend/test_usable_secret_rejeita_placeholder.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

from provider_fallback import _usable_secret  # noqa: E402


def test_rejeita_placeholder_truncado_do_incidente():
    assert _usable_secret("sk-761...3957") is False


def test_rejeita_outros_placeholders_truncados_do_arquivo():
    assert _usable_secret("sk-or-...de1c") is False
    assert _usable_secret("sk-...") is False


def test_rejeita_marcadores_conhecidos():
    assert _usable_secret("[REDACTED]") is False
    assert _usable_secret("REDACTED") is False
    assert _usable_secret("your_bot_token_here") is False
    assert _usable_secret("your_chat_id_here") is False


def test_rejeita_vazio_e_none():
    assert _usable_secret("") is False
    assert _usable_secret(None) is False
    assert _usable_secret("   ") is False


def test_aceita_chave_real_sem_reticencias():
    assert _usable_secret("sk-fake00000000000000000000000000000000") is True
    assert _usable_secret("sk-ant-api03-abc123def456") is True
