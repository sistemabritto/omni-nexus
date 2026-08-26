"""tests/backend/test_vision_fallback.py

2026-08-26 — vision_fallback.py existe porque o único código que chamava um
modelo multimodal (`ig_reels_full_map.py`, script hand-placed, perdido no
restart do scheduler) tinha um modelo só e nenhum fallback: se ele caísse, a
interpretação da imagem simplesmente sumia, sem erro visível. Este arquivo
prova a cadeia de fallback: o segundo modelo assume quando o primeiro falha,
e só devolve `None` quando TODOS falham — nunca lança.

Run:
    pytest tests/backend/test_vision_fallback.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

import vision_fallback  # noqa: E402


@pytest.fixture
def providers_config(tmp_path, monkeypatch):
    cfg = tmp_path / "providers.json"
    cfg.write_text(json.dumps({
        "providers": {
            "omnirouter": {
                "default_base_url": "http://omniroute:20128/v1",
                "env_vars": {"OPENAI_API_KEY": "sk-chave-real-de-teste"},
            }
        }
    }), encoding="utf-8")
    monkeypatch.setattr(vision_fallback, "PROVIDERS_CONFIG", cfg)
    return cfg


def _resposta(status=200, content="uma pessoa sorrindo"):
    r = MagicMock()
    r.status_code = status
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    else:
        r.raise_for_status.side_effect = None
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


def test_usa_o_primeiro_modelo_quando_ele_responde(providers_config):
    with patch.object(vision_fallback.requests, "post", return_value=_resposta()) as post:
        out = vision_fallback.vision_call("descreva", "base64fake")
    assert out == "uma pessoa sorrindo"
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["model"] == vision_fallback.VISION_MODEL_CHAIN[0]


def test_cai_para_o_segundo_modelo_quando_primeiro_falha(providers_config):
    """O caso real do incidente: modelo primário fora do ar não pode significar
    interpretação vazia — o segundo da cadeia tem que assumir."""
    respostas = [requests.RequestException("gateway timeout"), _resposta(content="um carro azul")]

    def fake_post(*args, **kwargs):
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    with patch.object(vision_fallback.requests, "post", side_effect=fake_post) as post:
        out = vision_fallback.vision_call("descreva", "base64fake")
    assert out == "um carro azul"
    assert post.call_count == 2
    assert post.call_args.kwargs["json"]["model"] == vision_fallback.VISION_MODEL_CHAIN[1]


def test_devolve_none_sem_lancar_quando_todos_falham(providers_config):
    with patch.object(vision_fallback.requests, "post", side_effect=requests.RequestException("boom")):
        out = vision_fallback.vision_call("descreva", "base64fake")
    assert out is None


def test_devolve_none_sem_chave_utilizavel(tmp_path, monkeypatch):
    cfg = tmp_path / "providers.json"
    cfg.write_text(json.dumps({
        "providers": {"omnirouter": {"default_base_url": "http://omniroute:20128/v1",
                                      "env_vars": {"OPENAI_API_KEY": "sk-761...3957"}}}
    }), encoding="utf-8")
    monkeypatch.setattr(vision_fallback, "PROVIDERS_CONFIG", cfg)
    with patch.object(vision_fallback.requests, "post") as post:
        out = vision_fallback.vision_call("descreva", "base64fake")
    assert out is None
    post.assert_not_called()


def test_devolve_none_quando_config_nao_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(vision_fallback, "PROVIDERS_CONFIG", tmp_path / "nao-existe.json")
    assert vision_fallback.vision_call("descreva", "base64fake") is None


def test_ignora_resposta_vazia_e_tenta_o_proximo(providers_config):
    """Modelo que responde 200 mas com conteúdo vazio não pode ser tratado
    como sucesso — é a mesma falha silenciosa disfarçada de HTTP 200."""
    respostas = [_resposta(content="   "), _resposta(content="um gato")]

    def fake_post(*args, **kwargs):
        return respostas.pop(0)

    with patch.object(vision_fallback.requests, "post", side_effect=fake_post) as post:
        out = vision_fallback.vision_call("descreva", "base64fake")
    assert out == "um gato"
    assert post.call_count == 2


def test_respeita_lista_de_modelos_customizada(providers_config):
    with patch.object(vision_fallback.requests, "post", return_value=_resposta()) as post:
        vision_fallback.vision_call("descreva", "base64fake", models=["custom/modelo-x"])
    assert post.call_args.kwargs["json"]["model"] == "custom/modelo-x"
