"""Fase 1B: propor_cortes (julgamento via modelo) e a página de revisão
(determinística). Mocka invoke_with_fallback — não bate em provider real.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import corte_editorial  # noqa: E402
from corte_editorial import gerar_pagina_revisao, propor_cortes  # noqa: E402
from transcricao import Segmento  # noqa: E402


def _segmentos():
    return [
        Segmento(0, 600, "fala normal sobre o tema"),
        Segmento(600, 1200, "aqui teve queda de conexão, deixa eu recomeçar essa parte"),
    ]


def test_propor_cortes_parseia_resposta_do_modelo():
    resposta = '[{"inicio": 610.0, "fim": 640.5, "motivo": "queda de conexão"}]'
    with patch.object(corte_editorial, "invoke_with_fallback",
                       return_value={"status": "success", "output": resposta}):
        cortes = propor_cortes(_segmentos(), cwd=Path("/tmp"))
    assert cortes == [{"inicio": 610.0, "fim": 640.5, "motivo": "queda de conexão"}]


def test_propor_cortes_aceita_bloco_markdown_ao_redor_do_json():
    resposta = '```json\n[{"inicio": 5.0, "fim": 10.0, "motivo": "x"}]\n```'
    with patch.object(corte_editorial, "invoke_with_fallback",
                       return_value={"status": "success", "output": resposta}):
        cortes = propor_cortes(_segmentos(), cwd=Path("/tmp"))
    assert len(cortes) == 1


def test_propor_cortes_descarta_item_fora_da_duracao_ou_invertido():
    resposta = '[{"inicio": 100, "fim": 50, "motivo": "invertido"}, {"inicio": 9000, "fim": 9001, "motivo": "fora"}, {"inicio": 10, "fim": 20, "motivo": "ok"}]'
    with patch.object(corte_editorial, "invoke_with_fallback",
                       return_value={"status": "success", "output": resposta}):
        cortes = propor_cortes(_segmentos(), cwd=Path("/tmp"))
    assert cortes == [{"inicio": 10.0, "fim": 20.0, "motivo": "ok"}]


def test_propor_cortes_vazio_quando_modelo_diz_nao_cortar_nada():
    with patch.object(corte_editorial, "invoke_with_fallback",
                       return_value={"status": "success", "output": "[]"}):
        cortes = propor_cortes(_segmentos(), cwd=Path("/tmp"))
    assert cortes == []


def test_propor_cortes_levanta_erro_se_status_nao_e_sucesso():
    with patch.object(corte_editorial, "invoke_with_fallback",
                       return_value={"status": "busy", "error": "sem provider"}):
        try:
            propor_cortes(_segmentos(), cwd=Path("/tmp"))
            assert False, "deveria ter levantado"
        except RuntimeError as exc:
            assert "busy" in str(exc)


def test_pagina_de_revisao_lista_os_cortes_e_soma_o_tempo():
    cortes = [{"inicio": 60.0, "fim": 90.0, "motivo": "repetição"}]
    html_gerado = gerar_pagina_revisao(titulo="Live teste", cortes=cortes, duracao_original_s=3600)
    assert "repetição" in html_gerado
    assert "01:00" in html_gerado  # inicio do corte, mm:ss
    assert "<!doctype html>" in html_gerado.lower()


def test_pagina_de_revisao_sem_cortes_nao_quebra():
    html_gerado = gerar_pagina_revisao(titulo="Live teste", cortes=[], duracao_original_s=100)
    assert "Nenhum corte proposto" in html_gerado
