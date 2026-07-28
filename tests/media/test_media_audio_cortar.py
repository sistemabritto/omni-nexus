"""cortar() em lotes — Fase 1A da esteira de vídeo.

Uma expressão `select` só com todos os `between()` de uma live de 3h28
(~2800 trechos) derruba o ffmpeg ("Cannot allocate memory" no parser de
expressão do libavfilter) — ver o comentário de LOTE_TRECHOS em
dashboard/backend/media_audio.py. Estes testes cobrem o loteamento sem
depender de um ffmpeg real: `_rodar` é mockado e a asserção é sobre quantas
vezes e com que argumentos ele foi chamado.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import media_audio  # noqa: E402
from media_audio import Trecho, cortar, FalhaDeMidia  # noqa: E402


def _trechos(n: int) -> list[Trecho]:
    return [Trecho(float(i * 2), float(i * 2 + 1)) for i in range(n)]


def test_cortar_lote_unico_nao_concatena(tmp_path):
    destino = tmp_path / "saida.mp4"
    with patch.object(media_audio, "_rodar", return_value="") as mock_rodar:
        cortar(tmp_path / "in.mp4", _trechos(5), destino)
    # um lote só -> um único ffmpeg de corte, sem concat
    assert mock_rodar.call_count == 1
    assert mock_rodar.call_args.kwargs["o_que"] == "corte de lote"


def test_cortar_muitos_trechos_faz_lotes_e_concatena(tmp_path, monkeypatch):
    monkeypatch.setattr(media_audio, "LOTE_TRECHOS", 150)
    destino = tmp_path / "saida.mp4"
    n = 320  # 3 lotes: 150 + 150 + 20

    chamadas = []

    def fake_rodar(cmd, *, o_que, timeout=21600):
        chamadas.append(o_que)
        if o_que == "corte de lote":
            # a etapa real criaria o arquivo de saída do lote (último
            # argumento do comando); simula isso para o passo de concat
            # encontrar os arquivos na lista.
            saida = Path(cmd[-1])
            saida.parent.mkdir(parents=True, exist_ok=True)
            saida.touch()
        return ""

    with patch.object(media_audio, "_rodar", side_effect=fake_rodar):
        cortar(tmp_path / "in.mp4", _trechos(n), destino)

    assert chamadas.count("corte de lote") == 3
    assert chamadas.count("concatenação dos lotes") == 1
    # o diretório de lotes é limpo depois, sucesso ou falha
    assert not (destino.parent / f"{destino.stem}_lotes").exists()


def test_cortar_sem_trechos_falha(tmp_path):
    with patch.object(media_audio, "_rodar") as mock_rodar:
        try:
            cortar(tmp_path / "in.mp4", [], tmp_path / "saida.mp4")
            assert False, "deveria ter levantado FalhaDeMidia"
        except FalhaDeMidia:
            pass
    mock_rodar.assert_not_called()


def test_cortar_limpa_lotes_mesmo_se_concat_falhar(tmp_path, monkeypatch):
    monkeypatch.setattr(media_audio, "LOTE_TRECHOS", 150)
    destino = tmp_path / "saida.mp4"
    n = 200

    def fake_rodar(cmd, *, o_que, timeout=21600):
        if o_que == "corte de lote":
            return ""
        raise FalhaDeMidia("concatenação dos lotes falhou (1): boom")

    with patch.object(media_audio, "_rodar", side_effect=fake_rodar):
        try:
            cortar(tmp_path / "in.mp4", _trechos(n), destino)
            assert False, "deveria ter propagado a falha do concat"
        except FalhaDeMidia:
            pass

    assert not (destino.parent / f"{destino.stem}_lotes").exists()
