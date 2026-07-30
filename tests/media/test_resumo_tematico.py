"""Fase 1D: resumo temático — mesma regra das Fases 1B/1C (modelo só onde há
julgamento). Mocka invoke_with_fallback e cortar() — não bate em provider
nem ffmpeg reais.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import resumo_tematico  # noqa: E402
from resumo_tematico import (  # noqa: E402
    propor_resumo_tematico,
    montar_resumo_tematico,
    formatar_para_selecao,
)
from transcricao import Palavra  # noqa: E402


def _palavra(inicio, fim, texto):
    return Palavra(inicio=inicio, fim=fim, texto=texto)


def _resultado_modelo(payload: str):
    return {"status": "success", "output": payload}


def test_formatar_para_selecao_agrupa_por_janela():
    palavras = [_palavra(0.0, 1.0, "a"), _palavra(1.0, 2.0, "b"), _palavra(10.0, 11.0, "c")]
    texto = formatar_para_selecao(palavras)
    assert "[0-2] a b" in texto
    assert "[10-11] c" in texto


def test_propor_resumo_usa_force_provider_opencode():
    palavras = [_palavra(0.0, 100.0, "x")]
    with patch.object(resumo_tematico, "invoke_with_fallback",
                       return_value=_resultado_modelo("[]")) as mock_invoke:
        propor_resumo_tematico(palavras, "Sistema Britto", cwd=Path("."))
    assert mock_invoke.call_args.kwargs["force_provider"] == "opencode"


def test_propor_resumo_aceita_trechos_de_qualquer_duracao():
    """Diferente de cortes_virais, aqui não há limite de duração — um
    trecho sobre o tema pode durar segundos ou vários minutos."""
    palavras = [_palavra(0.0, 1000.0, "x")]
    payload = '[{"inicio": 10, "fim": 15, "assunto": "curto"}, {"inicio": 100, "fim": 700, "assunto": "longo"}]'
    with patch.object(resumo_tematico, "invoke_with_fallback", return_value=_resultado_modelo(payload)):
        trechos = propor_resumo_tematico(palavras, "tema", cwd=Path("."))
    assert len(trechos) == 2
    assert trechos[1]["fim"] - trechos[1]["inicio"] == 600


def test_propor_resumo_remove_sobreposicao_e_ordena():
    palavras = [_palavra(0.0, 1000.0, "x")]
    payload = (
        '[{"inicio": 200, "fim": 300, "assunto": "segundo"},'
        ' {"inicio": 0, "fim": 250, "assunto": "primeiro"}]'
    )
    with patch.object(resumo_tematico, "invoke_with_fallback", return_value=_resultado_modelo(payload)):
        trechos = propor_resumo_tematico(palavras, "tema", cwd=Path("."))
    assert len(trechos) == 1
    assert trechos[0]["assunto"] == "primeiro"


def test_propor_resumo_aceita_aspas_simples_e_escape_extra():
    palavras = [_palavra(0.0, 100.0, "x")]
    payload = "[{'inicio': 5, 'fim': 20, 'assunto': 'ok'}]"
    with patch.object(resumo_tematico, "invoke_with_fallback", return_value=_resultado_modelo(payload)):
        trechos = propor_resumo_tematico(palavras, "tema", cwd=Path("."))
    assert trechos == [{"inicio": 5.0, "fim": 20.0, "assunto": "ok"}]


def test_propor_resumo_status_de_erro_propaga():
    with patch.object(resumo_tematico, "invoke_with_fallback", return_value={"status": "fail", "error": "x"}):
        try:
            propor_resumo_tematico([_palavra(0, 10, "x")], "tema", cwd=Path("."))
            assert False, "deveria ter levantado"
        except RuntimeError as e:
            assert "fail" in str(e)


def test_montar_resumo_tematico_chama_cortar_com_trechos_a_manter(tmp_path):
    video = tmp_path / "in.mp4"
    saida = tmp_path / "out.mp4"
    trechos = [{"inicio": 5.0, "fim": 20.0}, {"inicio": 100.0, "fim": 130.0}]

    with patch.object(resumo_tematico, "cortar") as mock_cortar:
        resultado = montar_resumo_tematico(video, trechos, saida)

    manter_passado = mock_cortar.call_args.args[1]
    assert [(t.inicio, t.fim) for t in manter_passado] == [(5.0, 20.0), (100.0, 130.0)]
    assert resultado["trechos_incluidos"] == 2
    assert resultado["duracao_final_s"] == 45.0
