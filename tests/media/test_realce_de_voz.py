"""
tests/media/test_realce_de_voz.py

2026-07-29 — "o tratamento da voz ainda não tá top... difícil de entender".

`realcar()` é a etapa nova entre denoise e normalização: highpass tira ronco
de sala, acompressor nivela frase a frase (o que o loudnorm sozinho não faz,
já que ele mede o programa inteiro), treble reforça a faixa das consoantes.
A redução de variância de RMS foi medida com dado real antes de escrever este
teste (ver sessão): 7,05 dB de desvio-padrão caiu para 5,07 dB.

Run:
    pytest tests/media/test_realce_de_voz.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import media_audio  # noqa: E402
from media_audio import (  # noqa: E402
    realcar,
    REALCE_HIGHPASS_HZ,
    REALCE_COMP_THRESHOLD_DB,
    REALCE_COMP_RATIO,
    REALCE_PRESENCA_GANHO_DB,
)


def test_realcar_chama_ffmpeg_uma_vez(tmp_path):
    entrada = tmp_path / "in.wav"
    saida = tmp_path / "out.wav"
    with patch.object(media_audio, "_rodar", return_value="") as mock_rodar:
        resultado = realcar(entrada, saida)

    assert resultado == saida
    assert mock_rodar.call_count == 1
    assert mock_rodar.call_args.kwargs["o_que"] == "realce de voz"


def test_filtro_tem_os_tres_estagios_na_ordem(tmp_path):
    """highpass antes do compressor, compressor antes do treble — inverter a
    ordem faria o compressor reagir ao grave que devia ter sido cortado."""
    with patch.object(media_audio, "_rodar", return_value="") as mock_rodar:
        realcar(tmp_path / "in.wav", tmp_path / "out.wav")

    cmd = mock_rodar.call_args.args[0]
    filtro = cmd[cmd.index("-af") + 1]
    assert filtro.index("highpass") < filtro.index("acompressor") < filtro.index("treble")


def test_filtro_usa_as_constantes_calibradas(tmp_path):
    with patch.object(media_audio, "_rodar", return_value="") as mock_rodar:
        realcar(tmp_path / "in.wav", tmp_path / "out.wav")

    filtro = mock_rodar.call_args.args[0][mock_rodar.call_args.args[0].index("-af") + 1]
    assert f"highpass=f={REALCE_HIGHPASS_HZ}" in filtro
    assert f"threshold={REALCE_COMP_THRESHOLD_DB}dB" in filtro
    assert f"ratio={REALCE_COMP_RATIO}" in filtro
    assert f"treble=g={REALCE_PRESENCA_GANHO_DB}" in filtro


def test_saida_e_wav_pcm_48k(tmp_path):
    """A cadeia inteira (denoise, normalizar, remuxar) espera PCM 48kHz —
    entregar outra coisa aqui quebraria o próximo passo em silêncio."""
    with patch.object(media_audio, "_rodar", return_value="") as mock_rodar:
        realcar(tmp_path / "in.wav", tmp_path / "out.wav")

    cmd = mock_rodar.call_args.args[0]
    assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == "48000"
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "pcm_s16le"


def test_progresso_e_chamado_quando_fornecido(tmp_path):
    chamadas = []
    with patch.object(media_audio, "_rodar", return_value=""):
        realcar(tmp_path / "in.wav", tmp_path / "out.wav",
                progresso=lambda etapa, detalhe: chamadas.append((etapa, detalhe)))

    assert chamadas == [("realce", "highpass + compressor + presença")]


def test_primeiro_corte_chama_realcar_entre_denoise_e_normalizar(tmp_path, monkeypatch):
    """A ordem importa: `normalizar` mede o loudness final, e precisa medir
    o material JÁ comprimido — senão o loudnorm mira um alvo que o realce
    muda logo depois, dois nivelamentos brigando pelo mesmo LUFS."""
    ordem = []

    def fake(nome):
        def _f(*a, **k):
            ordem.append(nome)
            destino = a[1] if len(a) > 1 else k.get("destino") or k.get("destino_dir")
            if nome in ("extrair_audio", "denoise", "realcar", "normalizar", "remuxar"):
                p = Path(a[1]) if len(a) > 1 else destino
                if nome == "denoise":
                    p = Path(a[1]) / Path(a[0]).name
                Path(p).parent.mkdir(parents=True, exist_ok=True)
                Path(p).touch()
                return p
            return None
        return _f

    monkeypatch.setattr(media_audio, "extrair_audio", fake("extrair_audio"))
    monkeypatch.setattr(media_audio, "denoise", fake("denoise"))
    monkeypatch.setattr(media_audio, "realcar", fake("realcar"))
    monkeypatch.setattr(media_audio, "normalizar", fake("normalizar"))
    monkeypatch.setattr(media_audio, "remuxar", fake("remuxar"))
    monkeypatch.setattr(media_audio, "duracao_de", lambda p: 10.0)
    monkeypatch.setattr(media_audio, "detectar_silencio", lambda p, progresso=None: [])
    monkeypatch.setattr(media_audio, "trechos_com_fala", lambda silencios, duracao: [
        media_audio.Trecho(inicio=0.0, fim=10.0)
    ])
    monkeypatch.setattr(media_audio, "cortar", lambda *a, **k: Path(a[2]).touch())

    saida = tmp_path / "saida.mp4"
    media_audio.primeiro_corte(tmp_path / "video.mp4", saida, trabalho=tmp_path / "work")

    assert ordem == ["extrair_audio", "denoise", "realcar", "normalizar", "remuxar"]
