"""Publicação do artigo no Ghost, atrás do mesmo gate humano das redes.

Primeiro estágio do fluxo de conteúdo (decisão do Felipe, 25/07/2026):

    draft no Ghost
      -> gate 1: humano lê o texto, confere os CTAs e vê a capa
      -> aprovado: o artigo é publicado/agendado no Ghost
      -> webhook post.published dispara a ponte
      -> gate 2..4: uma aprovação por rede (X, LinkedIn, Threads)

A ordem é o ponto: derivar post de rede a partir de artigo não aprovado é
gastar aprovação humana em cima de conteúdo que talvez nem devesse existir, e
pior, correr o risco de o post da rede sair antes de alguém ter lido o artigo.
Aprovar a fonte primeiro é o que torna o resto seguro.

Este módulo só sabe duas coisas: extrair o que o humano precisa ver para
decidir, e efetivar a decisão no Ghost. Quem abre o gate é `ghost_social_bridge`;
quem executa a aprovação é `heartbeat_outcome._run_publish_action`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

WORKSPACE = Path(__file__).resolve().parent.parent.parent

# O blog está atrás do Cloudflare, que devolve 403 "error code: 1010" para
# User-Agent de biblioteca HTTP. Ver ghost_social_bridge.UA_NAVEGADOR.
UA_NAVEGADOR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Funis comerciais da Sistema Britto. Um artigo sem link para nenhum deles não
# tem CTA — é conteúdo que informa e não converte, e o humano precisa ver isso
# ANTES de publicar, quando ainda dá para corrigir.
FUNIS = ("sistemabritto.com.br/whatsapp",
         "sistemabritto.com.br/socialjobs",
         "sistemabritto.com.br/sistema",
         "wa.me/")

_LINK = re.compile(r'href=["\'](https?://[^"\']+)["\']', re.I)


def _jwt(admin_key: str) -> str:
    kid, secret = admin_key.split(":")
    b = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()  # noqa: E731
    header = b(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid},
                          separators=(",", ":")).encode())
    agora = int(time.time())
    payload = b(json.dumps({"iat": agora, "exp": agora + 300, "aud": "/admin/"},
                           separators=(",", ":")).encode())
    assinado = f"{header}.{payload}"
    sig = hmac.new(bytes.fromhex(secret), assinado.encode(), hashlib.sha256).digest()
    return f"{assinado}.{b(sig)}"


def _config() -> tuple[str, str] | None:
    url = (os.environ.get("GHOST_URL") or "").strip().rstrip("/")
    key = (os.environ.get("GHOST_ADMIN_API_KEY") or "").strip()
    return (url, key) if url and key else None


def _headers(key: str) -> dict:
    return {"Authorization": f"Ghost {_jwt(key)}", "User-Agent": UA_NAVEGADOR,
            "Content-Type": "application/json"}


def buscar(post_id: str) -> dict | None:
    cfg = _config()
    if not cfg:
        return None
    url, key = cfg
    r = requests.get(
        f"{url}/ghost/api/admin/posts/{post_id}/?formats=html,plaintext&include=tags",
        headers=_headers(key), timeout=45)
    if r.status_code >= 300:
        return None
    posts = r.json().get("posts") or []
    return posts[0] if posts else None


def ctas_do_artigo(post: dict) -> dict:
    """Links do corpo, separando o que é CTA de funil do que é referência.

    Devolve as duas listas porque elas respondem perguntas diferentes na hora
    de aprovar: "esse artigo vende alguma coisa?" e "para onde mais ele manda o
    leitor?". Um artigo que só linka para fora é vazamento de tráfego.
    """
    html = post.get("html") or ""
    vistos: list[str] = []
    for m in _LINK.finditer(html):
        link = m.group(1)
        if link not in vistos:
            vistos.append(link)

    proprio = (urlparse(os.environ.get("GHOST_URL") or "").hostname or "").lower()
    funis, externos, internos = [], [], []
    for link in vistos:
        if any(f in link for f in FUNIS):
            funis.append(link)
        elif proprio and proprio in link:
            internos.append(link)
        else:
            externos.append(link)
    return {"funis": funis, "internos": internos, "externos": externos}


def resumo_para_aprovacao(post: dict) -> str:
    """O que o humano lê no card antes de liberar a publicação.

    Não é o artigo inteiro — é o suficiente para decidir: do que trata, para
    onde manda o leitor, e o que está faltando. Os avisos são a parte que
    importa: sem capa e sem CTA são exatamente os dois erros que só aparecem
    depois de publicado, quando corrigir já custa caro.
    """
    ctas = ctas_do_artigo(post)
    texto = (post.get("plaintext") or "").strip()
    linhas = [
        f"Título: {post.get('title') or '(sem título)'}",
        f"Status atual: {post.get('status')}",
    ]
    resumo = post.get("custom_excerpt") or post.get("excerpt") or texto[:300]
    if resumo:
        linhas += ["", resumo.strip()[:400]]

    linhas.append("")
    if ctas["funis"]:
        linhas.append(f"CTA de funil ({len(ctas['funis'])}):")
        linhas += [f"  → {u}" for u in ctas["funis"][:4]]
    else:
        linhas.append("⚠ NENHUM CTA de funil — o artigo informa e não converte.")
    if ctas["externos"]:
        linhas.append(f"Links externos: {len(ctas['externos'])}")
    if not (post.get("feature_image") or "").strip():
        linhas.append("⚠ SEM imagem de capa — o compartilhamento sai sem thumbnail.")

    palavras = len(texto.split())
    linhas.append(f"Tamanho: {palavras} palavras")
    return "\n".join(linhas)


def _pedir_ao_modelo(prompt: str, timeout: int = 300) -> str:
    """Chamada ao x.ai. Devolve string vazia em qualquer falha."""
    chave = (os.environ.get("XAI_API_KEY") or "").strip()
    if not chave:
        return ""
    try:
        r = requests.post(
            (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/") + "/responses",
            headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
            json={"model": os.environ.get("XAI_MODEL", "grok-4.20-non-reasoning"),
                  "input": [{"role": "user", "content": prompt}]},
            timeout=timeout)
        if r.status_code != 200:
            return ""
        texto = ""
        for item in r.json().get("output", []):
            if item.get("type") == "message":
                for parte in item.get("content", []):
                    if parte.get("type") == "output_text":
                        texto += parte.get("text", "")
        return texto.strip()
    except Exception:  # noqa: BLE001
        return ""


def _e_sobre_imagem(feedback: str) -> bool:
    """O feedback fala da capa? Decide se vale gastar uma geração de imagem."""
    baixo = feedback.lower()
    return any(p in baixo for p in (
        "thumb", "imagem", "foto", "capa", "arte", "visual", "banner", "rosto"))


def _e_sobre_texto(feedback: str) -> bool:
    """Feedback exclusivamente sobre a capa não deve reescrever o artigo — seria
    trocar um texto aprovado por outro que o humano não pediu."""
    baixo = feedback.lower()
    if not _e_sobre_imagem(feedback):
        return True
    return any(p in baixo for p in (
        "texto", "artigo", "conteúdo", "conteudo", "escrit", "parágrafo", "paragrafo",
        "título", "titulo", "cta", "humaniz", "tom", "linguagem", "palavra"))


def revisar_texto(post: dict, feedback: str) -> str:
    """Nova versão do corpo, incorporando a crítica. Vazio = manter o atual."""
    briefing = ""
    primer = WORKSPACE / ".claude" / "skills" / "mkt-quality-gate" / "experts" / "humanizer.md"
    if primer.is_file():
        briefing = primer.read_text(encoding="utf-8", errors="replace")[:6000]

    prompt = (
        "Você reescreve um artigo de blog em português do Brasil a partir de uma crítica "
        "concreta do autor. Devolva APENAS o HTML do corpo, sem preâmbulo, sem cercas de "
        "código, sem comentário.\n\n"
        f"CRÍTICA DO AUTOR (é ordem, não sugestão):\n{feedback}\n\n"
        "REGRAS QUE NÃO MUDAM:\n"
        "- Não invente número, data ou fato. Todo dado precisa manter o link de fonte que "
        "já está no HTML.\n"
        "- Preserve os <h2>/<h3> e seus atributos id, e mantenha o link de CTA do final.\n"
        "- Responda a pergunta do título nos dois primeiros parágrafos.\n"
        "- Cada <h2> começa com uma resposta curta e direta logo abaixo.\n\n"
        f"GUIA ANTI-ESCRITA-DE-IA (evite estes padrões):\n{briefing}\n\n"
        f"TÍTULO: {post.get('title')}\n\nHTML ATUAL:\n{post.get('html') or ''}"
    )
    novo = _pedir_ao_modelo(prompt)
    if not novo:
        return ""
    novo = re.sub(r"^```(?:html)?\s*|\s*```$", "", novo.strip())
    # Guarda contra resposta truncada: metade do original já é regressão, não revisão.
    if len(novo) < len(post.get("html") or "") * 0.5:
        return ""
    return novo


def briefing_de_capa(post: dict, feedback: str = "") -> dict:
    """Headline e hook para a thumbnail, derivados do próprio artigo."""
    prompt = (
        "Você define a arte da thumbnail de um artigo, no padrão de YouTube brasileiro do "
        "nicho de IA e automação. Devolva APENAS um JSON com as chaves headline, hook, "
        "expressao e badge.\n"
        "- headline: 2 a 5 PALAVRAS em maiúsculas, sem acento, que provoquem clique sem "
        "prometer o que o artigo não cumpre.\n"
        "- hook: descrição curta de UM objeto-símbolo em 3D glossy para o lado oposto ao rosto.\n"
        "- expressao: expressão facial coerente com a pauta.\n"
        "- badge: número ou palavra curta para um selo vermelho, ou string vazia.\n\n"
        f"TÍTULO: {post.get('title')}\nRESUMO: {post.get('custom_excerpt') or ''}\n"
        + (f"\nCRÍTICA DO AUTOR SOBRE A CAPA ANTERIOR (obedeça):\n{feedback}\n" if feedback else "")
    )
    bruto = _pedir_ao_modelo(prompt, timeout=180)
    try:
        dados = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", bruto.strip()))
    except (json.JSONDecodeError, ValueError):
        dados = {}
    titulo = (post.get("title") or "ARTIGO").upper()
    return {
        "headline": (dados.get("headline") or titulo.split(":")[0])[:60],
        "hook": dados.get("hook") or "um celular flutuando com a tela de conversa, ícone 3D glossy",
        "expressao": dados.get("expressao") or "sorriso confiante",
        "badge": dados.get("badge") or "",
    }


def subir_imagem(caminho: Path) -> tuple[str, str]:
    """Envia a imagem ao Ghost. Devolve (url, erro)."""
    cfg = _config()
    if not cfg:
        return "", "GHOST_URL/GHOST_ADMIN_API_KEY não configurados."
    url, key = cfg
    try:
        with caminho.open("rb") as fh:
            r = requests.post(
                f"{url}/ghost/api/admin/images/upload/",
                headers={"Authorization": f"Ghost {ghost_jwt(key)}", "User-Agent": UA_NAVEGADOR},
                files={"file": (caminho.name, fh, "image/png")},
                data={"purpose": "image"}, timeout=180)
    except Exception as exc:  # noqa: BLE001
        return "", str(exc)
    if r.status_code >= 300:
        return "", f"{r.status_code}: {r.text[:200]}"
    devolvida = (r.json().get("images") or [{}])[0].get("url") or ""
    if devolvida.startswith("/"):
        devolvida = url + devolvida
    return devolvida, ""


def atualizar(post_id: str, *, html: str | None = None,
              feature_image: str | None = None) -> str:
    """PUT no draft. `?source=html` é obrigatório para o campo html ser aceito —
    sem ele o Ghost devolve 200 e ignora o corpo em silêncio."""
    cfg = _config()
    if not cfg:
        return "GHOST_URL/GHOST_ADMIN_API_KEY não configurados."
    url, key = cfg
    atual = buscar(post_id)
    if not atual:
        return f"post {post_id} não encontrado"
    corpo: dict = {"updated_at": atual.get("updated_at")}
    if html:
        corpo["html"] = html
    if feature_image:
        corpo["feature_image"] = feature_image
    if len(corpo) == 1:
        return ""
    r = requests.put(f"{url}/ghost/api/admin/posts/{post_id}/?source=html",
                     headers=_headers(key), json={"posts": [corpo]}, timeout=90)
    return "" if r.status_code < 300 else f"{r.status_code}: {r.text[:200]}"


def publicar(post_id: str, quando_utc: str | None = None) -> dict:
    """Publica (ou agenda) o artigo. Só roda depois do humano aprovar.

    `quando_utc` no futuro agenda; ausente publica na hora. O Ghost exige
    `updated_at` do post atual no PUT — é o controle de concorrência dele, e
    mandar sem isso devolve 409. Buscamos imediatamente antes justamente para
    que uma edição feita entre a aprovação e a publicação seja respeitada em
    vez de sobrescrita.
    """
    cfg = _config()
    if not cfg:
        return {"published": False, "detail": "GHOST_URL/GHOST_ADMIN_API_KEY não configurados."}
    url, key = cfg

    atual = buscar(post_id)
    if not atual:
        return {"published": False, "detail": f"post {post_id} não encontrado no Ghost."}
    if atual.get("status") == "published":
        # Idempotência: reaprovar não pode republicar nem mexer na data.
        return {"published": True, "detail": "já estava publicado.",
                "url": atual.get("url")}

    corpo: dict = {"updated_at": atual.get("updated_at")}
    if quando_utc:
        quando = datetime.fromisoformat(quando_utc.replace("Z", "+00:00"))
        if quando > datetime.now(timezone.utc):
            corpo["status"] = "scheduled"
            corpo["published_at"] = quando.isoformat().replace("+00:00", "Z")
        else:
            corpo["status"] = "published"
    else:
        corpo["status"] = "published"

    r = requests.put(f"{url}/ghost/api/admin/posts/{post_id}/",
                     headers=_headers(key), json={"posts": [corpo]}, timeout=60)
    if r.status_code >= 300:
        return {"published": False,
                "detail": f"Ghost recusou a publicação ({r.status_code}): {r.text[:300]}"}

    depois = (r.json().get("posts") or [{}])[0]
    estado = depois.get("status")
    # Fail-closed: só confirmamos o que o Ghost confirmou. "scheduled" é efeito
    # real e confirmado, mesmo não estando no ar ainda.
    if estado not in ("published", "scheduled"):
        return {"published": False, "detail": f"Ghost devolveu status inesperado: {estado!r}"}
    return {
        "published": True,
        "detail": ("agendado para " + str(depois.get("published_at"))
                   if estado == "scheduled" else "publicado."),
        "url": depois.get("url"),
        "status": estado,
    }
