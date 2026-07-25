#!/usr/bin/env python3
"""Ghost publicou -> gera versões por rede -> aprovação no Telegram -> Postiz.

Objetivo 5 (2026-07-25). Fecha o loop que o Felipe pediu: quando um post sai no
blog, as versões sociais nascem sozinhas, mas **nada vai ao ar sem o OK dele no
Telegram**.

Fluxo:
    Ghost (post.published)
      -> POST /api/triggers/webhook/<id>        (trigger registry)
      -> este script
         1. lê o post publicado (título, excerpt, url, tags)
         2. adapta para X, LinkedIn, Threads e Instagram seguindo as regras de
            cada rede e o briefing de marca (tom direto, sem buzzword, dado real)
         3. abre UMA aprovação por rede em pending_approvals (gate_type=publish)
      -> Telegram mostra o texto EXATO + a data de agendamento
      -> "aprovar" -> heartbeat_outcome._run_publish_action -> Postiz agenda

Por que uma aprovação por rede e não uma só: o gate publica o que foi aprovado,
e cada rede tem texto próprio. Uma aprovação agregada faria o humano aprovar um
resumo — exatamente o problema de confiança que o gate existe para evitar.

Uso:
    python scripts/ghost_published_to_social.py --post-id <id>
    python scripts/ghost_published_to_social.py --payload <arquivo.json>   # webhook
    python scripts/ghost_published_to_social.py --post-id <id> --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

# Ordem de publicação: X primeiro (ciclo mais curto), Instagram por último
# (exige mídia, então é o mais provável de faltar coisa).
REDES = ["x", "linkedin", "threads", "instagram"]

LIMITES = {"x": 280, "linkedin": 3000, "threads": 500, "instagram": 2200}

# Espaçamento entre redes para não publicar tudo no mesmo minuto — o mesmo
# texto saindo simultaneamente em 4 lugares parece bot e performa pior.
OFFSET_MIN = {"x": 0, "linkedin": 20, "threads": 40, "instagram": 60}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def load_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ── Ghost ────────────────────────────────────────────────────────────────

def ghost_headers() -> dict:
    import jwt as pyjwt

    admin = os.environ["GHOST_ADMIN_API_KEY"]
    kid, secret = admin.split(":")
    iat = int(time.time())
    tok = pyjwt.encode({"iat": iat, "exp": iat + 300, "aud": "/admin/"},
                       bytes.fromhex(secret), algorithm="HS256",
                       headers={"kid": kid, "alg": "HS256"})
    return {"Authorization": f"Ghost {tok}", "Content-Type": "application/json"}


def buscar_post(post_id: str) -> dict | None:
    import requests

    url = os.environ["GHOST_URL"].rstrip("/")
    r = requests.get(f"{url}/ghost/api/admin/posts/{post_id}/?formats=plaintext&include=tags",
                     headers=ghost_headers(), timeout=45)
    if r.status_code >= 300:
        log(f"Ghost {r.status_code}: {r.text[:180]}")
        return None
    posts = r.json().get("posts") or []
    return posts[0] if posts else None


# ── adaptação por rede ───────────────────────────────────────────────────

BRIEFING = """Regras de marca do Sistema Britto (obrigatórias):
- Tom direto, sem firula. Escreva como quem construiu, não como quem vende.
- PROIBIDO: "juntos vamos", "revolucionar", "transformação digital", "disruptivo",
  "garanta já", "últimas vagas", promessa de resultado sem dado.
- Nunca invente número ou métrica. Só use dado que está no artigo.
- Emoji com parcimônia e propósito. Nada de emoji decorativo em cada linha.
- Humor seco quando couber; nunca meme forçado."""

FORMATO = {
    "x": "Máx 280 caracteres. Sem hashtag ou no máximo 1. Gancho na primeira linha. "
         "O link entra no fim.",
    "linkedin": "Máx 3000 caracteres, mas prefira 800-1200. Primeira linha é o gancho "
                "(aparece antes do 'ver mais'). Linha em branco a cada 1-2 frases. "
                "3-5 hashtags no fim. NÃO coloque link no corpo — diga que está no comentário.",
    "threads": "Máx 500 caracteres. Tom conversacional, mais solto que o LinkedIn. "
               "No máximo 1 hashtag. Link no fim.",
    "instagram": "Máx 2200 caracteres. Primeira linha é o gancho. Quebras curtas. "
                 "CTA claro no fim + 'link na bio'. 5-8 hashtags no fim.",
}


    # O `**` de markdown pode vir antes do rótulo e/ou depois dos dois-pontos
    # ("**Texto final para Threads:**"), então o fecho aceita qualquer mistura
    # de espaço, dois-pontos e asterisco.
_PREAMBULO = re.compile(
    r"^\s*(\*{0,2}\s*(texto|post|versão|versao|legenda)\s+(final\s+)?(para|do|de)\s+[\w/]+[\s:*]*"
    # `[^\n:]` (e não `[^\n]`) para o rótulo parar no primeiro dois-pontos —
    # senão "Aqui está o post para LinkedIn: Texto." consome o texto inteiro.
    r"|\*{0,2}\s*(aqui está|aqui vai|segue)[^\n:]{0,60}:[\s*]*)", re.I)


def limpar(texto: str, limite: int) -> str:
    """Tira preâmbulo do modelo e corta em fronteira de frase/palavra.

    O modelo às vezes desobedece o "sem preâmbulo" e devolve
    '**Texto final para Threads:** ...'. E corte cru no limite de caracteres
    parte palavra no meio — o que num post publicado parece erro, não estilo.
    """
    texto = texto.strip().strip('"').strip()
    prev = None
    while prev != texto:                      # pode vir preâmbulo empilhado
        prev = texto
        texto = _PREAMBULO.sub("", texto).strip()
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    # 1ª escolha: última frase completa; 2ª: última palavra completa
    fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "), corte.rfind("\n"))
    if fim > limite * 0.5:
        return corte[: fim + 1].strip()
    espaco = corte.rfind(" ")
    return (corte[:espaco] if espaco > 0 else corte).rstrip(" ,;:-") + "…"


def adaptar(post: dict, rede: str) -> str | None:
    """Gera a versão da rede via x.ai; sem chave, cai num fallback determinístico."""
    import requests

    titulo = post.get("title", "")
    resumo = post.get("custom_excerpt") or post.get("excerpt") or ""
    corpo = (post.get("plaintext") or "")[:6000]
    link = post.get("url", "")

    key = os.environ.get("XAI_API_KEY", "").strip()
    if key:
        prompt = (f"{BRIEFING}\n\nRede: {rede}. {FORMATO[rede]}\n\n"
                  f"Artigo publicado:\nTítulo: {titulo}\nResumo: {resumo}\nLink: {link}\n\n"
                  f"Conteúdo:\n{corpo}\n\n"
                  f"Escreva APENAS o texto final do post para {rede}, em português do Brasil. "
                  f"Sem preâmbulo, sem aspas em volta, sem explicação. Só o texto que vai ao ar.")
        try:
            r = requests.post(
                "https://api.x.ai/v1/responses",
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
            else:
                log(f"x.ai {r.status_code} para {rede}: {r.text[:140]}")
        except Exception as exc:  # noqa: BLE001
            log(f"x.ai falhou para {rede}: {exc}")

    # Fallback determinístico: nunca inventa nada, só recorta o que já existe.
    base = f"{titulo}\n\n{resumo}"
    if rede == "linkedin":
        base += "\n\nLink no primeiro comentário."
    elif link:
        base += f"\n\n{link}"
    return limpar(base, LIMITES[rede])


# ── aprovação (mesmo gate do Telegram) ───────────────────────────────────

def abrir_aprovacoes(post: dict, versoes: dict[str, str], quando: datetime, dry_run: bool) -> int:
    titulo = post.get("title", "")
    criadas = 0
    for rede, texto in versoes.items():
        if not texto:
            continue
        agendado = quando + timedelta(minutes=OFFSET_MIN[rede])
        outcome = {
            "action": "work",
            "result": f"Versão de {rede} do artigo '{titulo}'",
            "publish_intent": True,
            "publish_target": rede,
            "publish_content": texto,
            "publish_media": [],
            "publish_at": agendado.isoformat().replace("+00:00", "Z"),
        }
        if rede == "instagram":
            # O gate recusa Instagram sem mídia — é regra da plataforma, não
            # nossa. Sinalizamos em vez de mandar uma aprovação que vai falhar.
            log(f"  {rede}: precisa de imagem (publish_media) — pulado. "
                f"Gere a mídia e reenvie, ou publique manualmente.")
            continue
        if dry_run:
            print(f"\n--- {rede} | agendado para {agendado:%d/%m %H:%M} UTC ---\n{texto}\n")
            criadas += 1
            continue
        try:
            from sdk_client import evo

            evo.post("/api/approvals", {
                "gate_type": "publish",
                "agent": "pixel-social-media",
                "payload": {"title": f"Publicar em {rede}: {titulo}",
                            "body": texto[:800], "outcome": outcome},
            })
            log(f"  {rede}: aprovação aberta (agendado {agendado:%d/%m %H:%M} UTC)")
            criadas += 1
        except Exception as exc:  # noqa: BLE001
            log(f"  {rede}: falhou ao abrir aprovação — {exc}")
    return criadas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--post-id", help="id do post no Ghost")
    ap.add_argument("--payload", help="arquivo JSON do webhook do Ghost")
    ap.add_argument("--em-horas", type=float, default=2.0,
                    help="daqui a quantas horas agendar a 1ª rede (default 2)")
    ap.add_argument("--dry-run", action="store_true", help="mostra os textos, não abre aprovação")
    args = ap.parse_args()

    load_env()

    post_id = args.post_id
    if args.payload:
        data = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        post_id = (data.get("post", {}).get("current", {}) or {}).get("id") or post_id
    if not post_id:
        log("informe --post-id ou --payload com o evento do Ghost.")
        return 1

    post = buscar_post(post_id)
    if not post:
        return 1
    if post.get("status") != "published":
        log(f"post está '{post.get('status')}', não 'published' — nada a distribuir.")
        return 0

    log(f"post: {post.get('title')}")
    versoes = {}
    for rede in REDES:
        log(f"  adaptando para {rede}…")
        versoes[rede] = adaptar(post, rede)

    quando = datetime.now(timezone.utc) + timedelta(hours=args.em_horas)
    n = abrir_aprovacoes(post, versoes, quando, args.dry_run)
    log(f"{n} aprovação(ões) — aguardando seu OK no Telegram. Nada foi publicado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
