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

# Poses de referência. O banco tem mais fotos, mas só entram aqui as que o
# modelo consegue usar sem errar a pessoa: nada de foto com outra gente no
# quadro (o `/v1/images/edits` pode escolher o rosto errado) e nada de arte de
# marca, que não é rosto.
POSES = (
    {"arquivo": FACE_BANK / "front" / "fsbritto-corporate-arms-crossed-sistema-britto-2026-06-14.jpg",
     "pose": "de pé com os braços cruzados, postura de autoridade tranquila",
     "cenario": "escritório escuro ao fundo, camiseta preta da marca"},
    {"arquivo": FACE_BANK / "front" / "fsbritto-front-selfie-headset-notebook-2026-06-14.jpg",
     "pose": "recostado na cadeira com headset no pescoço, ângulo de bastidor",
     "cenario": "mesa de trabalho com notebook, clima de quem está operando agora"},
    {"arquivo": FACE_BANK / "gestures" / "fsbritto-front-smile-fist-car-stronger-than-ever-2026-06-14.jpg",
     "pose": "punho fechado erguido na altura do ombro, gesto de conquista",
     "cenario": "camiseta preta, energia de quem acabou de resolver algo"},
    {"arquivo": FACE_BANK / "expressions" / "fsbritto-front-smile-foco-2026-06-14.jpg",
     "pose": "cabeça levemente inclinada, rosto próximo da câmera",
     "cenario": "camiseta preta, fundo limpo, foco total no rosto"},
)

# Registro emocional da capa. Rotaciona junto com a pose para que duas capas
# seguidas nunca cheguem com a mesma cara — a queixa que originou isto foi
# "todas as thumbs com a mesma cara e pose". Metade contraria o texto de
# propósito: capa que confirma o título é a que o olho já aprendeu a ignorar.
REGISTROS = (
    "expressão CONGRUENTE com o texto, intensidade alta",
    "expressão INCONGRUENTE com o texto — se o texto alarma, o rosto está "
    "tranquilo e debochado; se o texto promete, o rosto duvida",
    "descrença: uma sobrancelha erguida, canto da boca torto, olhar de lado",
    "espanto genuíno: olhos arregalados, boca entreaberta, sobrancelhas no alto",
    "seriedade quase parada, sem sorriso, olhar fixo e direto na câmera",
    "riso aberto e solto, cabeça levemente jogada para trás",
)

LADOS = ("DIREITO", "ESQUERDO")
ENQUADRAMENTOS = ("close do peito para cima", "plano médio, da cintura para cima")

# Compatibilidade: quem só quer "uma foto boa" continua pedindo esta.
ROSTO_PADRAO = POSES[0]["arquivo"]

# Traços que ancoram a identidade. Sem eles o modelo tende a "melhorar" o rosto
# até virar outra pessoa, que é o erro que este módulo existe para evitar.
DESCRICAO_ROSTO = ("mesmo rosto da referência, barba cheia escura com bigode, "
                   "cabelo curto escuro, sem óculos, camiseta preta")

TAMANHO = "1536x1024"  # 16:9 suportado pela API


def _chave() -> str:
    return (os.environ.get("AI_IMG_CREATOR_OPENAI_KEY")
            or os.environ.get("OPENAI_API_KEY") or "").strip()


def variacao_de(n: int) -> dict:
    """A combinação visual da enésima capa: pose, lado, enquadramento, registro.

    Determinística de propósito — regerar a capa da mesma pauta devolve a mesma
    arte, o que faz retry e feedback funcionarem. Pose (4) e registro (6) andam
    em passos diferentes, então capas vizinhas nunca coincidem em nenhum dos
    dois, e a combinação inteira só se repete a cada 48 — mais de duas semanas
    de esteira sem uma capa igual à outra.
    """
    n = int(n)
    return {
        "pose": POSES[n % len(POSES)],
        "lado": LADOS[(n // len(POSES)) % len(LADOS)],
        "enquadramento": ENQUADRAMENTOS[(n // (len(POSES) * len(LADOS))) % len(ENQUADRAMENTOS)],
        "registro": REGISTROS[n % len(REGISTROS)],
    }


def montar_prompt(headline: str, hook: str, expressao: str = "",
                  badge: str = "", variacao: int = 0) -> str:
    """Prompt no formato do primer: rosto num terço, texto black do outro lado."""
    var = variacao_de(variacao)
    pose, lado = var["pose"], var["lado"]
    oposto = "esquerdo" if lado == "DIREITO" else "direito"
    # A expressão do briefing já foi escrita a partir deste mesmo registro, e
    # é mais concreta (olhos, sobrancelha, boca). Somar as duas só produziria
    # contradição — "espanto genuíno, olhos semicerrados" — quando o modelo do
    # briefing não obedecer. O registro fica como rede, para quando ele falhar.
    rosto = expressao or var["registro"]
    linhas = [
        "Thumbnail 16:9 para YouTube/blog no nicho de IA e automação, em português do Brasil.",
        f"PESSOA: mantenha EXATAMENTE o mesmo homem da imagem de referência — {DESCRICAO_ROSTO}.",
        f"EXPRESSÃO: {rosto}. Olhando para a câmera.",
        f"POSE: {pose['pose']}. {pose['cenario']}.",
        f"ENQUADRAMENTO: {var['enquadramento']}, ocupando o terço {lado} do quadro, "
        f"recorte limpo com rim light verde-limão.",
        f"HOOK VISUAL do lado {oposto}: {hook}",
        f"TEXTO GRANDE no lado {oposto}, exatamente estas palavras: {headline}",
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
