"""tests/media/test_config_real_tem_os_providers_pinados.py

2026-08-26 — o buraco que `test_force_provider_fora_da_cadeia.py` não cobria.

Aquele teste prova que o motor de fallback SABE montar a entry de um provider
forçado que está fora da cadeia ativa. Mas ele prova isso contra um dicionário
fabricado no próprio arquivo (`CONFIG_VPS_REAL`), que inventa uma entry
`"opencode"` — e o `config/providers.json` de verdade, tanto local quanto no
volume da VPS, **não tinha essa entry**.

Resultado: três chamadas de `force_provider="opencode"` na esteira de vídeo
(`corte_editorial`, `cortes_virais`, `resumo_tematico`) caíam em cadeia vazia
— "No attempts made" — enquanto a suíte ficava verde contra a ficção.

Este arquivo fecha a distância: lê o arquivo REAL e confere que todo provider
que o código pina existe nele, com o binário certo.

Run:
    pytest tests/media/test_config_real_tem_os_providers_pinados.py -v
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

CONFIG_REAL = REPO / "config" / "providers.json"

# Onde o código pina provider explicitamente. Varrer o repo inteiro pegaria
# docstring e teste; estas são as chamadas de produção.
FONTES = [
    REPO / "dashboard" / "backend" / "corte_editorial.py",
    REPO / "dashboard" / "backend" / "cortes_virais.py",
    REPO / "dashboard" / "backend" / "resumo_tematico.py",
]

_PIN = re.compile(r'force_provider\s*=\s*"([a-z0-9_-]+)"')


def _providers_reais() -> dict:
    return json.loads(CONFIG_REAL.read_text(encoding="utf-8"))["providers"]


def _pinados() -> set[str]:
    achados: set[str] = set()
    for f in FONTES:
        if not f.is_file():
            continue
        for linha in f.read_text(encoding="utf-8").splitlines():
            # ignora comentário e docstring — só a chamada de verdade conta
            if linha.lstrip().startswith("#"):
                continue
            achados.update(_PIN.findall(linha))
    return achados


def test_encontrou_algum_pin():
    """Se a varredura não achar nada, os testes abaixo passariam vazios."""
    assert _pinados(), "nenhum force_provider encontrado — a regex parou de casar?"


@pytest.mark.parametrize("provider_id", sorted(_pinados()))
def test_provider_pinado_existe_na_config_real(provider_id):
    provs = _providers_reais()
    assert provider_id in provs, (
        f"o código pina force_provider=\"{provider_id}\", mas ele não existe em "
        f"config/providers.json (tem: {sorted(provs)}). A cadeia fica VAZIA e a "
        f"chamada morre com 'No attempts made' — sem erro de import, sem "
        f"traceback, só silêncio."
    )


def test_provider_opencode_usa_o_binario_opencode():
    """A imagem media-worker instala só o binário `opencode`; um cli_command
    diferente aqui falha com 'binary not found in PATH'."""
    assert _providers_reais()["opencode"]["cli_command"] == "opencode"


def test_modelos_do_opencode_estao_declarados_no_opencode_json():
    """`provider_fallback` monta `-m {provider_id}/{model}` para o opencode, e
    o binário só aceita modelo declarado em opencode.json sob aquele provider.
    Modelo fora da lista volta como ProviderModelNotFoundError disfarçado de
    'Unexpected server error' — caro de debugar."""
    cfg = json.loads((REPO / "opencode.json").read_text(encoding="utf-8"))
    declarados = set(cfg["provider"]["opencode"]["models"])
    na_cadeia = set(_providers_reais()["opencode"]["model_chain"])
    faltando = na_cadeia - declarados
    assert not faltando, (
        f"model_chain do provider 'opencode' pede {sorted(faltando)}, que não "
        f"está declarado em opencode.json (declarados: {sorted(declarados)})"
    )


def test_opencode_json_declara_o_provider_com_o_id_que_o_codigo_usa():
    """O id tem de ser literalmente 'opencode' nos dois arquivos: o model_ref
    é `f\"{provider_id}/{model}\"`. Renomear de um lado só quebra tudo."""
    cfg = json.loads((REPO / "opencode.json").read_text(encoding="utf-8"))
    assert "opencode" in cfg.get("provider", {}), (
        "opencode.json não declara o provider 'opencode' — model_ref "
        "'opencode/auto/coding' não resolve"
    )
