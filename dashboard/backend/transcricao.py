"""Transcrição de áudio para a Fase 1B da esteira de vídeo (corte editorial).

Determinístico: extrai áudio, quebra em blocos e chama a API de transcrição.
Nenhuma decisão editorial acontece aqui — isso é `corte_editorial.py`, que é
onde o modelo entra (marcar o que cortar é julgamento; transcrever não é).

Groq (whisper-large-v3-turbo) tem teto de tamanho por request — 16kHz mono em
blocos de 600s fica bem abaixo de qualquer limite prático (~19MB por bloco),
e o mesmo tamanho de bloco já usado no denoise (`media_audio.BLOCO_S`) evita
inventar uma segunda constante de particionamento pro mesmo problema.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests

from media_audio import FalhaDeMidia, Progresso, duracao_de

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"
BLOCO_TRANSCRICAO_S = 600


@dataclass
class Segmento:
    inicio: float
    fim: float
    texto: str


@dataclass
class Palavra:
    inicio: float
    fim: float
    texto: str


def extrair_audio_16k(video: Path, destino: Path) -> Path:
    """Deriva o áudio pro Whisper: 16kHz mono, sem denoise nem pre-gain —
    o modelo de transcrição já lida bem com ruído, e essa cadeia é
    independente da cadeia de tratamento (48k estéreo) da Fase 1A.
    """
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video),
         "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(destino)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        cauda = (r.stderr or "").strip().splitlines()[-6:]
        raise FalhaDeMidia("extração de áudio 16k falhou (" + str(r.returncode) + "): " + " | ".join(cauda))
    return destino


def _transcrever_bloco(caminho_wav: Path, *, chave: str, timeout: int = 120) -> str:
    with caminho_wav.open("rb") as f:
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {chave}"},
            files={"file": (caminho_wav.name, f, "audio/wav")},
            data={"model": GROQ_MODEL, "response_format": "text"},
            timeout=timeout,
        )
    if r.status_code != 200:
        raise FalhaDeMidia(f"Groq respondeu {r.status_code}: {r.text[:300]}")
    return r.text.strip()


def _transcrever_bloco_palavras(caminho_wav: Path, *, chave: str, timeout: int = 120) -> list[dict]:
    """Igual a `_transcrever_bloco`, mas pede timestamp por palavra em vez de
    texto corrido — é o que a Fase 1C (cortes virais) precisa pra saber
    exatamente onde uma frase-gancho começa e termina, e pra legendar palavra
    por palavra em vez de bloco de 10 minutos inteiro."""
    with caminho_wav.open("rb") as f:
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {chave}"},
            files={"file": (caminho_wav.name, f, "audio/wav")},
            data={
                "model": GROQ_MODEL,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
            },
            timeout=timeout,
        )
    if r.status_code != 200:
        raise FalhaDeMidia(f"Groq respondeu {r.status_code}: {r.text[:300]}")
    dados = r.json()
    return dados.get("words") or []


def transcrever_palavras(audio_16k: Path, *, trabalho: Path,
                         progresso: Progresso | None = None) -> list[Palavra]:
    """Transcreve com timestamp por palavra, em blocos de `BLOCO_TRANSCRICAO_S`
    (mesmo particionamento de `transcrever`, mesmo motivo: teto de tamanho por
    request do Groq). Cada palavra do bloco ganha o timestamp global somando
    o offset do bloco.
    """
    chave = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not chave:
        raise FalhaDeMidia("GROQ_API_KEY ausente — transcrição não pode rodar")

    duracao = duracao_de(audio_16k)
    total_blocos = max(1, int(duracao // BLOCO_TRANSCRICAO_S) + (1 if duracao % BLOCO_TRANSCRICAO_S else 0))
    trabalho.mkdir(parents=True, exist_ok=True)

    palavras: list[Palavra] = []
    for i in range(total_blocos):
        inicio = i * BLOCO_TRANSCRICAO_S
        duracao_bloco = min(BLOCO_TRANSCRICAO_S, duracao - inicio)
        if progresso:
            progresso("transcrevendo palavras", f"bloco {i + 1} de {total_blocos}")

        bloco_wav = trabalho / f"bloco{i:04d}.wav"
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{inicio:.3f}", "-t", f"{duracao_bloco:.3f}",
             "-i", str(audio_16k), "-c", "copy", str(bloco_wav)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            cauda = (r.stderr or "").strip().splitlines()[-6:]
            raise FalhaDeMidia(f"corte do bloco {i} pra transcrição falhou: " + " | ".join(cauda))

        for w in _transcrever_bloco_palavras(bloco_wav, chave=chave):
            try:
                palavras.append(Palavra(
                    inicio=inicio + float(w["start"]),
                    fim=inicio + float(w["end"]),
                    texto=str(w.get("word") or "").strip(),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        bloco_wav.unlink(missing_ok=True)

    return palavras


def transcrever(audio_16k: Path, *, trabalho: Path, progresso: Progresso | None = None) -> list[Segmento]:
    """Transcreve o áudio inteiro em blocos de `BLOCO_TRANSCRICAO_S`, devolvendo
    segmentos com timestamp global (offset do bloco somado ao timestamp local).

    Cada bloco vira um segmento só (texto corrido) — granularidade de bloco é
    suficiente pra 1B (marcar trechos a cortar); granularidade de palavra é
    problema da 1C (legenda), quando existir.
    """
    chave = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not chave:
        raise FalhaDeMidia("GROQ_API_KEY ausente — transcrição não pode rodar")

    duracao = duracao_de(audio_16k)
    total_blocos = max(1, int(duracao // BLOCO_TRANSCRICAO_S) + (1 if duracao % BLOCO_TRANSCRICAO_S else 0))
    trabalho.mkdir(parents=True, exist_ok=True)

    segmentos: list[Segmento] = []
    for i in range(total_blocos):
        inicio = i * BLOCO_TRANSCRICAO_S
        duracao_bloco = min(BLOCO_TRANSCRICAO_S, duracao - inicio)
        if progresso:
            progresso("transcrevendo", f"bloco {i + 1} de {total_blocos}")

        bloco_wav = trabalho / f"bloco{i:04d}.wav"
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{inicio:.3f}", "-t", f"{duracao_bloco:.3f}",
             "-i", str(audio_16k), "-c", "copy", str(bloco_wav)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            cauda = (r.stderr or "").strip().splitlines()[-6:]
            raise FalhaDeMidia(f"corte do bloco {i} pra transcrição falhou: " + " | ".join(cauda))

        texto = _transcrever_bloco(bloco_wav, chave=chave)
        bloco_wav.unlink(missing_ok=True)
        segmentos.append(Segmento(inicio=inicio, fim=inicio + duracao_bloco, texto=texto))

    return segmentos
