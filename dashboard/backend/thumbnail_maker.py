"""Geração de thumbnail no padrão do THUMBNAIL-PRIMER, com o rosto certo.

Duas armadilhas que este módulo existe para não repetir, ambas encontradas em
produção (25/07/2026):

1. **Rosto errado.** `assets/thumbnail-refs/ref-01-br-felipe.jpg` é captura do
   canal de OUTRO criador, guardada como referência de ESTILO. O nome do
   arquivo e a redação antiga do primer sugeriam o contrário, e a capa saiu com
   a cara de outra pessoa. As fotos reais moram em `FACE_BANK` abaixo.

2. **`-r` recusado.** A skill `ai-image-creator` chama
   `/v1/images/generations`, que não aceita imagem de entrada, e por isso
   rejeita referência de rosto no provider openai. `/v1/images/edits` aceita —
   é o que permite usar gpt-image-2 E manter o rosto.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent

FACE_BANK = WORKSPACE / "workspace" / "social" / "brands" / "evolution-foundation" / \
    "library" / "images" / "faces"
# Melhor referência: bem iluminada, camiseta da marca, rosto nítido de frente.
ROSTO_PADRAO = FACE_BANK / "front" / "fsbritto-corporate-arms-crossed-sistema-britto-2026-06-14.jpg"

# Traços que ancoram a identidade. Sem eles o modelo tende a "melhorar" o rosto
# até virar outra pessoa, que é o erro que este módulo existe para evitar.
DESCRICAO_ROSTO = ("mesmo rosto da referência, barba cheia escura com bigode, "
                   "cabelo curto escuro, sem óculos, camiseta preta")

TAMANHO = "1536x1024"  # 16:9 suportado pela API


def _chave() -> str:
    return (os.environ.get("AI_IMG_CREATOR_OPENAI_KEY")
            or os.environ.get("OPENAI_API_KEY") or "").strip()


def montar_prompt(headline: str, hook: str, expressao: str = "sorriso confiante",
                  badge: str = "") -> str:
    """Prompt no formato do primer: rosto num terço, texto black do outro lado."""
    linhas = [
        "Thumbnail 16:9 para YouTube/blog no nicho de IA e automação, em português do Brasil.",
        f"PESSOA: mantenha EXATAMENTE o mesmo homem da imagem de referência — {DESCRICAO_ROSTO}. "
        f"{expressao}, olhando para a câmera, ocupando o terço DIREITO do quadro, "
        f"recorte limpo com rim light verde-limão.",
        f"HOOK VISUAL à esquerda: {hook}",
        f"TEXTO GRANDE no lado esquerdo, exatamente estas palavras: {headline}",
        "Fonte black bem pesada, letras maiúsculas, branca com contorno preto grosso, "
        "altíssimo contraste, ocupando bastante espaço.",
    ]
    if badge:
        linhas.append(f"BADGE pequeno em vermelho no canto: {badge}")
    linhas += [
        "FUNDO escuro com glow verde-limão (#A3E635) da marca e tons de cinza metálico.",
        "Composição limpa, um único foco visual, legível em miniatura, sem poluição.",
        "Não escreva nenhum outro texto além do indicado.",
    ]
    return "\n".join(linhas)


def gerar(prompt: str, destino: Path, referencia: Path | None = None) -> str | None:
    """Gera a imagem via /v1/images/edits. Devolve o erro, ou None se deu certo."""
    chave = _chave()
    if not chave:
        return "AI_IMG_CREATOR_OPENAI_KEY/OPENAI_API_KEY não configurada"
    ref = referencia or ROSTO_PADRAO
    if not ref.is_file():
        return f"foto de referência ausente: {ref}"

    limite = "----thumb" + uuid.uuid4().hex
    partes: list[bytes] = []

    def campo(nome: str, valor: str) -> None:
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; '
                      f'name="{nome}"\r\n\r\n{valor}\r\n'.encode())

    partes.append(
        f'--{limite}\r\nContent-Disposition: form-data; name="image"; '
        f'filename="{ref.name}"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
        + ref.read_bytes() + b"\r\n")
    campo("model", os.environ.get("THUMBNAIL_MODEL", "gpt-image-2"))
    campo("prompt", prompt)
    campo("size", TAMANHO)
    campo("n", "1")
    partes.append(f"--{limite}--\r\n".encode())

    req = urllib.request.Request(
        "https://api.openai.com/v1/images/edits", data=b"".join(partes), method="POST",
        headers={"Authorization": f"Bearer {chave}",
                 "Content-Type": f"multipart/form-data; boundary={limite}"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=300).read())
    except urllib.error.HTTPError as exc:
        return f"{exc.code}: {exc.read()[:300].decode(errors='replace')}"
    except Exception as exc:  # noqa: BLE001
        return str(exc)

    dado = (resp.get("data") or [{}])[0]
    destino.parent.mkdir(parents=True, exist_ok=True)
    if dado.get("b64_json"):
        destino.write_bytes(base64.b64decode(dado["b64_json"]))
    elif dado.get("url"):
        destino.write_bytes(urllib.request.urlopen(dado["url"], timeout=180).read())
    else:
        return f"resposta sem imagem: {str(resp)[:200]}"
    return None
