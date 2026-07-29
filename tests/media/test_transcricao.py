"""transcricao.py — determinístico (extrai áudio, quebra em blocos, chama
Groq). Mocka subprocess e requests.post; não bate em ffmpeg real nem na API.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import transcricao  # noqa: E402
from media_audio import FalhaDeMidia  # noqa: E402


def test_transcrever_sem_groq_key_falha(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    try:
        transcricao.transcrever(tmp_path / "audio.wav", trabalho=tmp_path / "work")
        assert False, "deveria ter levantado FalhaDeMidia"
    except FalhaDeMidia:
        pass


def test_transcrever_pagina_em_blocos_com_timestamp_global(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")

    # 1300s de áudio -> 3 blocos de 600s (600, 600, 100)
    with patch.object(transcricao, "duracao_de", return_value=1300.0):
        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"fake-wav")
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            return r

        respostas = iter(["primeiro bloco", "segundo bloco", "terceiro bloco"])

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            r = MagicMock()
            r.status_code = 200
            r.text = next(respostas)
            return r

        with patch.object(transcricao.subprocess, "run", side_effect=fake_run), \
             patch.object(transcricao.requests, "post", side_effect=fake_post):
            segmentos = transcricao.transcrever(audio, trabalho=tmp_path / "work")

    assert len(segmentos) == 3
    assert segmentos[0].inicio == 0 and segmentos[0].fim == 600
    assert segmentos[1].inicio == 600 and segmentos[1].fim == 1200
    assert segmentos[2].inicio == 1200 and segmentos[2].fim == 1300
    assert [s.texto for s in segmentos] == ["primeiro bloco", "segundo bloco", "terceiro bloco"]


def test_transcrever_bloco_com_erro_http_levanta_falha_de_midia(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")

    with patch.object(transcricao, "duracao_de", return_value=60.0):
        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"fake-wav")
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            return r

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            r = MagicMock()
            r.status_code = 429
            r.text = "rate limited"
            return r

        with patch.object(transcricao.subprocess, "run", side_effect=fake_run), \
             patch.object(transcricao.requests, "post", side_effect=fake_post):
            try:
                transcricao.transcrever(audio, trabalho=tmp_path / "work")
                assert False, "deveria ter levantado"
            except FalhaDeMidia as exc:
                assert "429" in str(exc)
