"""Ponte Ghost -> redes sociais, com aprovação humana no meio.

Quando um post é publicado no blog, este módulo gera a versão de cada rede e
abre UMA aprovação por rede no gate existente (`pending_approvals`,
gate_type=publish). O Telegram mostra o texto exato e a data; aprovar faz
`heartbeat_outcome._run_publish_action` agendar no Postiz.

Mora em `dashboard/backend/` de propósito, e não em `scripts/`: a imagem do
dashboard copia `dashboard/` mas **não** copia `scripts/`
(Dockerfile.swarm.dashboard), então um trigger apontando para um script solto
falharia em produção com "No such file or directory". `scripts/ghost_published_to_social.py`
é só um wrapper de linha de comando em cima daqui.

Pelo mesmo motivo o JWT do Ghost é montado com a stdlib (`hmac`/`hashlib`) em
vez de PyJWT: PyJWT não está nas dependências da imagem, e o algoritmo é HS256
com um header simples — trazer uma dependência nova para isso seria pior.

Uma aprovação por rede, e não uma agregada: o gate publica exatamente o que foi
aprovado, e cada rede tem texto próprio. Aprovação agregada faria o humano
aprovar um resumo — o problema de confiança que o gate existe para evitar.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

# X primeiro (ciclo mais curto), Instagram por último (exige mídia).
REDES = ("x", "linkedin", "threads", "instagram")

LIMITES = {"x": 280, "linkedin": 3000, "threads": 500, "instagram": 2200}

# Espaçamento entre redes: o mesmo texto saindo simultaneamente em 4 lugares
# parece bot e performa pior.
OFFSET_MIN = {"x": 0, "linkedin": 20, "threads": 40, "instagram": 60}

BRIEFING = """Regras de marca do Sistema Britto (obrigatórias):
- Tom direto, sem firula. Escreva como quem construiu, não como quem vende.
- PROIBIDO: "juntos vamos", "revolucionar", "transformação digital", "disruptivo",
  "garanta já", "últimas vagas", promessa de resultado sem dado.
- Nunca invente número ou métrica. Só use dado que está no artigo.
- Emoji com parcimônia e propósito.
- Humor seco quando couber; nunca meme forçado."""

FORMATO = {
    "x": "Máx 280 caracteres. No máximo 1 hashtag. Gancho na primeira linha. Link no fim.",
    "linkedin": "Prefira 800-1200 caracteres. A primeira linha é o gancho (aparece antes "
                "do 'ver mais'). Linha em branco a cada 1-2 frases. 3-5 hashtags no fim. "
                "NÃO coloque link no corpo — diga que está no primeiro comentário.",
    "threads": "Máx 500 caracteres. Conversacional, mais solto que o LinkedIn. "
               "No máximo 1 hashtag. Link no fim.",
    "instagram": "Máx 2200 caracteres. Primeira linha é o gancho. Quebras curtas. "
                 "CTA no fim + 'link na bio'. 5-8 hashtags no fim.",
}

# Rótulos que o modelo insiste em colocar apesar do "sem preâmbulo":
#   "**Texto final para Threads:**", "**Texto final:**", "Aqui está o post para X:"
# O "para <rede>" é opcional — na prática aparece nas duas formas. `[^\n:]` no
# segundo padrão faz o rótulo parar no primeiro dois-pontos, senão
# "Aqui está o post para LinkedIn: Texto." consumiria o texto inteiro.
# Só "tem dois-pontos" não basta como discriminador: prosa legítima como
# "Post agendado não é post pensado: eis o problema." seria decapitada. Um
# rótulo de verdade tem uma destas três marcas:
#   A) abre com "aqui está/aqui vai/segue"  -> inequívoco
#   B) fecha com ":**" (negrito de markdown) -> "**Legenda:**", "**Texto final:**"
#   C) diz "final" ou nomeia a rede antes do ":" -> "Texto final para X:"
_REDE = r"(?:final|x|twitter|linkedin|threads|instagram|facebook|tiktok|youtube|blog)"
_ROTULO = r"(?:texto|post|versão|versao|legenda|caption)"
_PREAMBULO = re.compile(
    rf"^\s*\*{{0,2}}\s*(?:aqui est[áa]|aqui vai|segue)[^\n:]{{0,50}}:\*{{0,2}}[ \t]*\n?"
    rf"|^\s*\*{{1,2}}\s*{_ROTULO}[^\n:]{{0,40}}:\*{{1,2}}[ \t]*\n?"
    rf"|^\s*\*{{0,2}}\s*{_ROTULO}[^\n:]{{0,30}}\b{_REDE}\b[^\n:]{{0,15}}:\*{{0,2}}[ \t]*\n?",
    re.I)

# Régua horizontal de markdown no começo do texto — decoração, não conteúdo.
_REGUA = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", re.M)


# ── Ghost (JWT em stdlib) ────────────────────────────────────────────────

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def ghost_jwt(admin_key: str) -> str:
    """HS256 no formato que o Ghost Admin API espera (kid no header, aud=/admin/)."""
    kid, secret = admin_key.split(":")
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid},
                             separators=(",", ":")).encode())
    iat = int(time.time())
    payload = _b64(json.dumps({"iat": iat, "exp": iat + 300, "aud": "/admin/"},
                              separators=(",", ":")).encode())
    assinado = f"{header}.{payload}"
    sig = hmac.new(bytes.fromhex(secret), assinado.encode(), hashlib.sha256).digest()
    return f"{assinado}.{_b64(sig)}"


# O blog está atrás do Cloudflare, que devolve 403 "error code: 1010" para
# User-Agent de biblioteca HTTP (python-requests/urllib). O JWT está correto e
# o erro não diz nada sobre bloqueio de bot — parece credencial inválida e leva
# a trocar chave que estava certa. Um UA de navegador resolve.
UA_NAVEGADOR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def buscar_post(post_id: str) -> dict | None:
    url = (os.environ.get("GHOST_URL") or "").strip().rstrip("/")
    key = (os.environ.get("GHOST_ADMIN_API_KEY") or "").strip()
    if not url or not key:
        return None
    r = requests.get(
        f"{url}/ghost/api/admin/posts/{post_id}/?formats=plaintext&include=tags",
        headers={"Authorization": f"Ghost {ghost_jwt(key)}", "User-Agent": UA_NAVEGADOR},
        timeout=45)
    if r.status_code >= 300:
        return None
    posts = r.json().get("posts") or []
    return posts[0] if posts else None


# ── texto ────────────────────────────────────────────────────────────────

def limpar(texto: str, limite: int) -> str:
    """Remove preâmbulo do modelo e corta em fronteira de frase/palavra.

    O modelo às vezes devolve "**Texto final para Threads:** ..." apesar da
    instrução, e cortar cru no limite parte palavra no meio — o que num post
    publicado parece erro, não estilo.
    """
    texto = (texto or "").strip().strip('"').strip()
    prev = None
    while prev != texto:                      # rótulo e régua podem vir empilhados
        prev = texto
        texto = _PREAMBULO.sub("", texto).strip()
        texto = _REGUA.sub("", texto, count=1).strip() if _REGUA.match(texto) else texto
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "), corte.rfind("\n"))
    if fim > limite * 0.5:
        return corte[: fim + 1].strip()
    espaco = corte.rfind(" ")
    return (corte[:espaco] if espaco > 0 else corte).rstrip(" ,;:-") + "…"


def adaptar(post: dict, rede: str) -> str:
    """Versão da rede via x.ai; sem chave ou em erro, cai num fallback que não inventa nada."""
    titulo = post.get("title", "")
    resumo = post.get("custom_excerpt") or post.get("excerpt") or ""
    link = post.get("url", "")
    key = (os.environ.get("XAI_API_KEY") or "").strip()

    if key:
        prompt = (f"{BRIEFING}\n\nRede: {rede}. {FORMATO[rede]}\n\n"
                  f"Artigo publicado:\nTítulo: {titulo}\nResumo: {resumo}\nLink: {link}\n\n"
                  f"Conteúdo:\n{(post.get('plaintext') or '')[:6000]}\n\n"
                  f"Escreva APENAS o texto final do post para {rede}, em português do Brasil. "
                  f"Sem preâmbulo, sem aspas em volta, sem explicação.")
        try:
            r = requests.post(
                (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/") + "/responses",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": os.environ.get("XAI_MODEL", "grok-4.20-non-reasoning"),
                      "input": [{"role": "user", "content": prompt}]},
                timeout=240)
            if r.status_code == 200:
                txt = ""
                for item in r.json().get("output", []):
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "output_text":
                                txt += c.get("text", "")
                if txt.strip():
                    return limpar(txt, LIMITES[rede])
        except Exception:  # noqa: BLE001 — fallback abaixo cobre qualquer falha
            pass

    base = f"{titulo}\n\n{resumo}"
    base += "\n\nLink no primeiro comentário." if rede == "linkedin" else (f"\n\n{link}" if link else "")
    return limpar(base, LIMITES[rede])


# ── aprovações ───────────────────────────────────────────────────────────

def midia_do_post(post: dict) -> tuple[list[str], str]:
    """Mídia utilizável do artigo, ou o motivo de não haver.

    A capa do Ghost (`feature_image`) é a imagem real do artigo — é ela que vai
    para o Instagram, não uma imagem inventada. Duas coisas podem faltar:

    1. o post não tem capa;
    2. a capa está num host fora de POSTIZ_ALLOWED_MEDIA_HOSTS.

    Nos dois casos devolvemos o motivo em vez de uma lista vazia, porque o
    chamador precisa dizer ao humano por que o Instagram ficou de fora — "sem
    imagem" e "imagem num host não permitido" pedem ações diferentes.
    """
    capa = (post.get("feature_image") or "").strip()
    if not capa:
        return [], "artigo sem feature_image (Instagram exige imagem)"
    try:
        from postiz_client import PostizClient

        client = PostizClient.from_env()
    except Exception:  # noqa: BLE001 — sem cliente, não dá para afirmar que é segura
        client = None
    if client is None:
        return [], "POSTIZ_URL/POSTIZ_API_KEY não configurados"
    if not client.is_safe_media_url(capa):
        return [], (f"capa em host não permitido ({capa.split('/')[2] if '/' in capa else capa}); "
                    "acrescente-o a POSTIZ_ALLOWED_MEDIA_HOSTS")
    return [capa], ""


def distribuir(post_id: str, *, em_horas: float = 2.0, dry_run: bool = False) -> dict:
    """Gera as versões e abre uma aprovação por rede. Nada é publicado aqui."""
    post = buscar_post(post_id)
    if not post:
        return {"ok": False, "erro": f"post {post_id} não encontrado no Ghost"}
    if post.get("status") != "published":
        return {"ok": True, "ignorado": f"post está '{post.get('status')}', não 'published'"}

    quando = datetime.now(timezone.utc) + timedelta(hours=em_horas)
    resultado: dict = {"ok": True, "post": post.get("title"), "redes": {}, "pulados": {}}
    midia, sem_midia = midia_do_post(post)

    for rede in REDES:
        texto = adaptar(post, rede)
        if not texto:
            resultado["pulados"][rede] = "texto vazio"
            continue
        if rede == "instagram" and not midia:
            # O Postiz recusa Instagram sem mídia — é regra da plataforma, não
            # nossa. Abrir uma aprovação que vai falhar na publicação é pior que
            # não abrir, então o motivo vai para o relatório e a rede fica fora.
            resultado["pulados"][rede] = sem_midia
            continue

        agendado = quando + timedelta(minutes=OFFSET_MIN[rede])
        outcome = {
            "action": "work",
            "result": f"Versão de {rede} do artigo '{post.get('title')}'",
            "publish_intent": True,
            "publish_target": rede,
            "publish_content": texto,
            # Só o Instagram exige imagem; nas outras redes a capa competiria
            # com o preview do link, que é o que dá clique.
            "publish_media": midia if rede == "instagram" else [],
            "publish_at": agendado.isoformat().replace("+00:00", "Z"),
            # Link do artigo, para conferir o texto completo na hora de aprovar.
            # Em draft o Ghost devolve a URL de preview (/p/<uuid>/), que abre
            # sem login — vale tanto para revisar antes quanto depois de publicar.
            "source_url": post.get("url"),
        }
        if dry_run:
            resultado["redes"][rede] = {"dry_run": True, "publish_at": outcome["publish_at"],
                                        "preview": texto, "midia": outcome["publish_media"]}
            continue
        try:
            from sdk_client import evo

            evo.post("/api/approvals", {
                "gate_type": "publish",
                "agent": "pixel-social-media",
                "payload": {"title": f"Publicar em {rede}: {post.get('title')}",
                            "body": texto[:800], "outcome": outcome},
            })
            resultado["redes"][rede] = {"aprovacao": "aberta", "publish_at": outcome["publish_at"]}
        except Exception as exc:  # noqa: BLE001
            resultado["redes"][rede] = {"erro": str(exc)}
            resultado["ok"] = False
    return resultado


def distribuir_do_webhook(payload: dict, **kwargs) -> dict:
    """Entrada do trigger: extrai o id do evento post.published do Ghost."""
    post = (payload or {}).get("post") or {}
    atual = post.get("current") or {}
    post_id = atual.get("id") or post.get("id")
    if not post_id:
        return {"ok": False, "erro": "payload do Ghost sem post.current.id"}
    return distribuir(post_id, **kwargs)
