"""Chamada de visão (interpretar imagem) com fallback entre modelos — nunca
ponto único de falha.

Achado em 2026-08-26: o único lugar do workspace que chamava um modelo
multimodal (`ig_reels_full_map.py`, script hand-placed no scheduler, fora do
volume e fora do git — perdido no primeiro restart do container, exatamente
o risco que `.claude/rules/routines.md` já documentava) fazia isso com **um
modelo só, sem fallback nenhum**: se `meta/llama-3.2-11b-vision-instruct`
saísse do ar, `_vision_call` engolia a exceção e devolvia `None` — a análise
daquele frame simplesmente não acontecia, em silêncio. Nenhum sinal de que a
interpretação falhou, só um buraco no dataset.

Este módulo existe para que qualquer rotina futura que precise "olhar" uma
imagem (vídeo, reels, thumbnail, print de tela) tenha uma cadeia de pelo
menos dois modelos multimodais de contas distintas — se um cair, o outro
assume, em vez de devolver uma interpretação vazia como se fosse resposta.

Não reusa `provider_fallback.invoke_with_fallback`: aquele é para o harness
CLI (openclaude/opencode via subprocess), pensado para tarefa de código/texto.
Chamada de visão manda imagem em base64 dentro do corpo JSON de
`/v1/chat/completions` — é HTTP puro, transporte diferente.

A chave e a URL vêm de `config/providers.json` (`omnirouter`), o mesmo
arquivo hot-reloaded a cada chamada que todo o resto do workspace usa — sem
isso, rotacionar a chave do gateway (como aconteceu em 2026-08-26, ver
`omniroute-v1-sem-autenticacao`) exigiria caçar mais um lugar com chave
hardcoded.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

WORKSPACE = Path(__file__).resolve().parent.parent.parent
PROVIDERS_CONFIG = WORKSPACE / "config" / "providers.json"

# Modelos com suporte a imagem confirmados vivos no gateway na auditoria de
# 2026-07-28 (ver PROMPT-OMNIROUTE-CONFIG.md) — o primeiro que responder
# vence. `meta/llama-3.2-11b-vision-instruct` é o único dedicado a visão;
# os Claude entram como fallback porque também aceitam imagem nativamente
# e já são a espinha dorsal do `omnirouter.model_chain`.
VISION_MODEL_CHAIN = [
    "meta/llama-3.2-11b-vision-instruct",
    "claude/claude-sonnet-5",
    "claude/claude-haiku-4-5-20251001",
]

DEFAULT_TIMEOUT = 30


def _usable_secret(value: str | None) -> bool:
    # Mesma regra de dashboard.backend.provider_fallback._usable_secret,
    # duplicada aqui de propósito para não criar um import cruzado só por
    # uma função de 3 linhas: reticências literais (`...`) são o padrão de
    # todo placeholder truncado deste arquivo, nenhuma chave real as contém.
    if not value:
        return False
    value = value.strip()
    if not value or value in {"[REDACTED]", "REDACTED"}:
        return False
    return "..." not in value


def _omniroute_config() -> tuple[str, str] | None:
    """Lê (base_url, api_key) do provider `omnirouter` em config/providers.json.

    Lido do zero a cada chamada — sem cache — para que uma chave rotacionada
    no arquivo (ex.: revogação/reemissão no OmniRoute) valha na próxima
    chamada sem precisar reiniciar nada.
    """
    try:
        data = json.loads(PROVIDERS_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    provider = data.get("providers", {}).get("omnirouter", {})
    base_url = provider.get("default_base_url") or ""
    key = provider.get("env_vars", {}).get("OPENAI_API_KEY")
    if not base_url or not _usable_secret(key):
        return None
    return base_url.rstrip("/"), key


def vision_call(
    prompt: str,
    image_b64: str,
    *,
    models: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    mime: str = "image/jpeg",
) -> str | None:
    """Descreve `image_b64` segundo `prompt`, tentando cada modelo da cadeia
    até um responder. Nunca lança — quem chama decide o que fazer com `None`
    (ex.: reagendar o frame), mas com fallback real em vez de um único
    modelo mudo. Retorna o texto da primeira resposta bem-sucedida.
    """
    cfg = _omniroute_config()
    if cfg is None:
        return None
    base_url, key = cfg

    body_base = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }
        ],
        "max_tokens": 500,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    for model in models or VISION_MODEL_CHAIN:
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={**body_base, "model": model},
                timeout=timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            if content and content.strip():
                return content
        except (requests.RequestException, KeyError, IndexError, ValueError):
            continue
    return None
