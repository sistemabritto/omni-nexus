"""tests/media/test_force_provider_fora_da_cadeia.py

2026-07-29 — regressão do bug real que travou o primeiro job de
`cortes_virais` em produção: `force_provider="opencode"` virava cadeia vazia
("No attempts made") sempre que o `active_provider` corrente não listasse
"opencode" no seu `fallback_providers` — que é exatamente a config ao vivo da
VPS (`active_provider=omnirouter`, cadeia omnirouter→nvidia→openrouter→
anthropic, nenhum deles "opencode"). `media_worker` só tem o binário
`opencode` instalado (ver Dockerfile.media-worker); forçar qualquer provider
que não seja opencode ali falha sempre com "binary not found in PATH".

Fix em `provider_fallback.py::_invoke_with_fallback_locked.attempts()`: quando
force_provider não aparece na cadeia resolvida, mas existe em
`config["providers"]`, monta a entry direto de lá em vez de devolver cadeia
vazia.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import provider_fallback as pf

CONFIG_VPS_REAL = {
    "active_provider": "omnirouter",
    "providers": {
        "omnirouter": {
            "cli_command": "openclaude",
            "env_vars": {"OPENAI_BASE_URL": "http://omniroute:20128/v1", "OPENAI_MODEL": "NEVE-Mastery"},
            "fallback_providers": ["nvidia", "openrouter", "anthropic"],
        },
        "nvidia": {"cli_command": "openclaude", "env_vars": {}, "fallback_providers": ["omnirouter", "anthropic"]},
        "openrouter": {"cli_command": "openclaude", "env_vars": {}, "fallback_providers": None},
        "anthropic": {"cli_command": "claude", "env_vars": {}, "fallback_providers": None},
        "opencode": {
            "cli_command": "opencode",
            "env_vars": {"OPENAI_BASE_URL": "https://omni.workflowapi.com.br/v1"},
            "default_model": "auto",
            "fallback_providers": ["nvidia", "anthropic", "openrouter"],
        },
    },
}


def test_force_provider_ausente_da_cadeia_ativa_monta_direto_do_config():
    """opencode não está na cadeia de omnirouter (active_provider) — sem o
    fix, chain ficava vazia e nenhum attempt era gerado."""
    with patch.object(pf, "_read_providers_config", return_value=CONFIG_VPS_REAL):
        engine = pf.FallbackEngine()
        attempts = list(engine.attempts(prompt="x", force_provider="opencode"))
    assert len(attempts) >= 1
    assert attempts[0].provider_id == "opencode"


def test_force_provider_opencode_usa_cli_command_opencode():
    with patch.object(pf, "_read_providers_config", return_value=CONFIG_VPS_REAL):
        engine = pf.FallbackEngine()
        attempts = list(engine.attempts(prompt="x", force_provider="opencode"))
    assert all(a.cli_command == "opencode" for a in attempts)


def test_force_provider_desconhecido_continua_vazio():
    """provider que não existe nem na cadeia nem no config inteiro — não deve
    inventar nada, cadeia continua vazia (comportamento pré-existente)."""
    with patch.object(pf, "_read_providers_config", return_value=CONFIG_VPS_REAL):
        engine = pf.FallbackEngine()
        attempts = list(engine.attempts(prompt="x", force_provider="provider-que-nao-existe"))
    assert attempts == []
