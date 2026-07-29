"""Transcrição de feedback em áudio — dashboard principal, sem ffmpeg.

Diferente de `transcricao.py` (Fase 1B da esteira de vídeo, que processa
horas de vídeo em blocos), aqui a entrada é um áudio curto gravado no
navegador (segundos, não horas) — Groq aceita o arquivo bruto (webm/ogg/mp3)
sem precisar extrair 16kHz mono antes. Isso evita depender de ffmpeg no
container do dashboard principal, que não o tem instalado (só o media-worker).
"""

from __future__ import annotations

import os
from typing import BinaryIO

import requests

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"


def transcrever_audio(arquivo: BinaryIO, nome: str, *, timeout: int = 60) -> str:
    chave = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not chave:
        raise RuntimeError("GROQ_API_KEY ausente — transcrição não pode rodar")

    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {chave}"},
        files={"file": (nome, arquivo, "application/octet-stream")},
        data={"model": GROQ_MODEL, "response_format": "text"},
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Groq respondeu {r.status_code}: {r.text[:300]}")
    return r.text.strip()
