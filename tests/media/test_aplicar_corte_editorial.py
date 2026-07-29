"""Fase 1B, depois da aprovação: inverter cortes aprovados em trechos a
manter, e aplicar (mockando _rodar/duracao_de — sem ffmpeg real).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import media_audio  # noqa: E402
from media_audio import Trecho, trechos_a_manter, aplicar_corte_editorial, FalhaDeMidia  # noqa: E402


def test_trechos_a_manter_inverte_um_corte_no_meio():
    remover = [Trecho(50, 60)]
    manter = trechos_a_manter(remover, duracao=100)
    assert manter == [Trecho(0, 50), Trecho(60, 100)]


def test_trechos_a_manter_varios_cortes_nao_ordenados():
    remover = [Trecho(80, 90), Trecho(10, 20)]
    manter = trechos_a_manter(remover, duracao=100)
    assert manter == [Trecho(0, 10), Trecho(20, 80), Trecho(90, 100)]


def test_trechos_a_manter_cortes_sobrepostos_nao_duplicam():
    remover = [Trecho(10, 30), Trecho(20, 40)]
    manter = trechos_a_manter(remover, duracao=100)
    assert manter == [Trecho(0, 10), Trecho(40, 100)]


def test_trechos_a_manter_sem_cortes_devolve_o_video_inteiro():
    assert trechos_a_manter([], duracao=100) == [Trecho(0, 100)]


def test_trechos_a_manter_corte_do_inicio_ao_fim_nao_sobra_nada():
    assert trechos_a_manter([Trecho(0, 100)], duracao=100) == []


def test_aplicar_corte_editorial_chama_cortar_com_os_trechos_invertidos(tmp_path):
    video = tmp_path / "in.mp4"
    saida = tmp_path / "out.mp4"
    chamadas = {}

    def fake_cortar(midia, trechos, dest, *, progresso=None):
        chamadas["trechos"] = trechos
        dest.touch()
        return dest

    with patch.object(media_audio, "duracao_de", side_effect=[100.0, 90.0]), \
         patch.object(media_audio, "cortar", side_effect=fake_cortar):
        resultado = aplicar_corte_editorial(video, [{"inicio": 50, "fim": 60}], saida)

    assert chamadas["trechos"] == [Trecho(0, 50), Trecho(60, 100)]
    assert resultado["duracao_original_s"] == 100.0
    assert resultado["duracao_final_s"] == 90.0
    assert resultado["cortes_aplicados"] == 1


def test_aplicar_corte_editorial_recusa_remover_o_video_inteiro(tmp_path):
    video = tmp_path / "in.mp4"
    saida = tmp_path / "out.mp4"
    with patch.object(media_audio, "duracao_de", return_value=100.0):
        try:
            aplicar_corte_editorial(video, [{"inicio": 0, "fim": 100}], saida)
            assert False, "deveria ter levantado FalhaDeMidia"
        except FalhaDeMidia:
            pass
