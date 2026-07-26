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

# Artigo do blog vai para X, LinkedIn e Threads — as três redes onde texto com
# link tem para onde levar.
#
# Instagram, TikTok e YouTube NÃO pertencem a esta ponte (decisão do Felipe,
# 25/07/2026): são a trilha de vídeo vertical, com produção própria, e serão
# desenhados à parte. Lá o link nem é clicável no feed, então republicar artigo
# viraria post que não converte ocupando o espaço do que funciona. O suporte a
# essas plataformas segue existindo e testado no gate de publicação — só não é
# alimentado a partir do blog.
REDES = ("x", "linkedin", "threads")

LIMITES = {"x": 280, "linkedin": 3000, "threads": 500, "instagram": 2200}

# Espaçamento entre redes: o mesmo texto saindo simultaneamente em três lugares
# parece bot e performa pior.
OFFSET_MIN = {"x": 0, "linkedin": 20, "threads": 40, "instagram": 60}

# Funis reais da Sistema Britto — o CTA aponta para um destes, nunca para
# "Evolution/Evo AI", que é produto open source e não funil comercial.
FUNIS = {
    "whatsapp": "https://sistemabritto.com.br/whatsapp",
    "socialjobs": "https://sistemabritto.com.br/socialjobs",
    "sistema": "https://sistemabritto.com.br/sistema",
}

# Horários (BRT) em que o público — dono de empresa, não adolescente — está de
# fato olhando a rede. "Publicar duas horas depois do artigo" era conta de
# relógio, não de audiência: um artigo publicado às 23h caía às 1h da manhã,
# quando o post morre sem ser visto e queima a pauta.
#
# LinkedIn concentra no começo do expediente e no fim; X aguenta o meio do dia;
# Threads é mais noturno, quando a leitura é mais solta. Números de janela, não
# de minuto: o objetivo é não cair na madrugada, não fingir precisão que a
# plataforma não entrega.
JANELAS = {
    "x": (8, 12, 18),
    "linkedin": (8, 12, 17),
    "threads": (12, 19, 21),
    "instagram": (11, 18, 20),
}
TZ_PUBLICACAO = os.environ.get("WORKSPACE_TIMEZONE") or "America/Sao_Paulo"

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
    # Threads é "post recompensa": o link não vai no post. O texto entrega
    # valor sozinho e fecha pedindo um comentário com uma palavra-chave para
    # receber o artigo. Duas razões — a rede pune link no corpo com alcance, e
    # cada comentário é um lead que se identificou sozinho, que é o que o
    # formato existe para produzir.
    "threads": "Máx 500 caracteres. Conversacional, mais solto que o LinkedIn. "
               "No máximo 1 hashtag. NÃO coloque link nenhum no texto. "
               "Feche pedindo que comentem uma palavra-chave curta e óbvia "
               "(uma só palavra, ligada ao tema) para receber o artigo no direct.",
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
# "gancho" entrou depois de ver o modelo devolver "**Gancho:** IA open source
# não é sobre..." numa validação real — a instrução de formato do LinkedIn fala
# em gancho, e ele repetiu o rótulo como se fosse estrutura do post. Sem isto o
# texto sairia publicado com "**Gancho:**" na primeira linha.
_ROTULO = r"(?:texto|post|versão|versao|legenda|caption|gancho|abertura|corpo)"
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

    # Correções que o Felipe já pediu entram como regra, não como sugestão. É o
    # que faz o padrão convergir sem ninguém reescrever briefing: pedir três
    # vezes "corta hashtag no LinkedIn" faz a quarta geração já nascer sem.
    try:
        from approval_feedback import diretrizes

        aprendido = diretrizes(rede)
    except Exception:  # noqa: BLE001 — ledger indisponível não pode travar a geração
        aprendido = ""

    if key:
        prompt = (f"{BRIEFING}\n\n{aprendido}\n\nRede: {rede}. {FORMATO[rede]}\n\n"
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
    if rede == "linkedin":
        base += "\n\nLink no primeiro comentário."
    elif rede == "threads":
        # Sem link, como no caminho do modelo — a regra do formato não pode
        # depender de a chave do x.ai estar configurada.
        base += "\n\nComenta ARTIGO que eu te mando no direct."
    elif link:
        base += f"\n\n{link}"
    return limpar(base, LIMITES[rede])


# ── aprovações ───────────────────────────────────────────────────────────

def _zona():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(TZ_PUBLICACAO)
    except Exception:  # noqa: BLE001 — tzdata ausente não pode quebrar o agendamento
        return timezone.utc


def proximo_horario(rede: str, a_partir_de: datetime) -> datetime:
    """Primeiro horário útil da rede a partir de `a_partir_de`, em UTC.

    Avança até cair numa das janelas da rede no fuso do público. Nunca anda
    para trás: se já passou da última janela do dia, vai para a primeira do dia
    seguinte. Um post agendado para o passado o Postiz recusa, e o gate
    fail-closed transformaria isso numa aprovação que morre na hora de publicar.
    """
    janelas = JANELAS.get(rede)
    if not janelas:
        return a_partir_de
    zona = _zona()
    local = a_partir_de.astimezone(zona)
    for _ in range(8):  # hoje + 7 dias é folga de sobra; o laço nunca é infinito
        for hora in sorted(janelas):
            candidato = local.replace(hour=hora, minute=0, second=0, microsecond=0)
            if candidato >= local:
                return candidato.astimezone(timezone.utc)
        local = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return a_partir_de


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

        # A janela decide o horário; o offset só desempata quando duas redes
        # caem na mesma janela, para o mesmo texto não sair simultâneo em três
        # lugares — o que parece bot e performa pior.
        agendado = proximo_horario(rede, quando) + timedelta(minutes=OFFSET_MIN[rede])
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
            # O id é o que permite REFAZER: pedir ajuste precisa voltar ao
            # artigo de origem para gerar outra versão. Sem ele o feedback fica
            # registrado e o texto não é regenerado.
            "source_id": post.get("id"),
        }
        if dry_run:
            resultado["redes"][rede] = {"dry_run": True, "publish_at": outcome["publish_at"],
                                        "preview": texto, "midia": outcome["publish_media"]}
            continue
        try:
            from sdk_client import evo

            # O gate de publicação é ancorado num ticket: é dele que sai a
            # chave de idempotência (publish:<ticket>:<tentativa>) e é ele que
            # muda de estado quando o humano aprova. Sem ticket_id a API
            # devolve 400 e a aprovação nunca chega ao Telegram — o trabalho
            # todo morre no último passo, em silêncio.
            #
            # Ancorar num ticket também é o que faz o post aparecer no Kanban:
            # o trabalho fica visível antes, durante e depois da aprovação, em
            # vez de existir só como uma notificação que passou.
            ticket = evo.post("/api/tickets", {
                "title": f"Publicar em {rede}: {post.get('title')}",
                "description": f"Distribuição automática do artigo {post.get('url') or ''}".strip(),
                "assignee_agent": "pixel-social-media",
                "priority": "medium",
                "status": "review",
            })
            ticket_id = (ticket or {}).get("id") or (ticket or {}).get("ticket", {}).get("id")
            if not ticket_id:
                raise RuntimeError(f"POST /api/tickets não devolveu id: {ticket!r}")

            evo.post("/api/approvals", {
                "gate_type": "publish",
                "ticket_id": ticket_id,
                "agent": "pixel-social-media",
                "payload": {"title": f"Publicar em {rede}: {post.get('title')}",
                            "body": texto[:800], "outcome": outcome},
            })
            resultado["redes"][rede] = {"aprovacao": "aberta", "ticket": ticket_id,
                                        "publish_at": outcome["publish_at"]}
        except Exception as exc:  # noqa: BLE001
            resultado["redes"][rede] = {"erro": str(exc)}
            resultado["ok"] = False
    return resultado


# Teto de refações automáticas por ticket. Sem limite, um feedback que o modelo
# não consegue satisfazer vira laço infinito de geração — caro e irritante.
# Estourado o teto, o trabalho volta para a fila humana em vez de insistir.
MAX_REFACOES = int(os.environ.get("MAX_REFACOES_AUTOMATICAS", "3"))


def refazer(outcome_anterior: dict, feedback: str, ticket_id: str,
            *, tentativa: int = 1) -> dict:
    """Gera outra versão do post com a crítica e reabre a aprovação.

    Fecha o laço que o Felipe pediu: pedir ajuste não devolve o trabalho para
    uma fila que ninguém puxa — o texto é refeito na hora e volta ao Telegram
    para nova decisão, até aprovar ou bater o teto.

    Só vale para post de rede. Artigo de blog (`publish_target="blog"`) não é
    refeito aqui de propósito: reescrever o corpo inteiro é trabalho de agente,
    não de um request, e fazer isso em silêncio produziria artigo que ninguém
    escreveu de fato.
    """
    rede = outcome_anterior.get("publish_target")
    if rede not in REDES:
        return {"ok": False, "erro": f"refação automática não se aplica a {rede!r}"}
    if tentativa > MAX_REFACOES:
        return {"ok": False, "erro": f"teto de {MAX_REFACOES} refações atingido; "
                                     "o ticket fica na fila para revisão humana"}

    post_id = outcome_anterior.get("source_id")
    if not post_id:
        return {"ok": False, "erro": "outcome sem source_id: não dá para voltar ao artigo"}
    post = buscar_post(post_id)
    if not post:
        return {"ok": False, "erro": f"artigo {post_id} não encontrado no Ghost"}

    # `adaptar` já lê o ledger de feedback; a crítica desta rodada entra
    # explícita por cima, porque é a mais recente e a mais específica.
    texto = adaptar(post, rede)
    if not texto:
        return {"ok": False, "erro": "geração devolveu texto vazio"}

    novo = dict(outcome_anterior)
    novo["publish_content"] = texto
    novo["result"] = (f"Versão {tentativa + 1} de {rede} do artigo "
                      f"'{post.get('title')}' (após ajuste pedido)")

    try:
        from sdk_client import evo

        evo.post("/api/approvals", {
            "gate_type": "publish",
            "ticket_id": ticket_id,
            "agent": "pixel-social-media",
            "payload": {"title": f"[v{tentativa + 1}] Publicar em {rede}: {post.get('title')}",
                        "body": f"Refeito com a crítica: {feedback[:300]}",
                        "outcome": novo},
        })
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": str(exc)}
    return {"ok": True, "tentativa": tentativa + 1, "rede": rede, "preview": texto}


def refazer_artigo(outcome_anterior: dict, feedback: str, ticket_id: str,
                   *, tentativa: int = 1) -> dict:
    """Aplica a crítica no artigo e reabre o gate — texto, capa, ou os dois.

    Antes, pedir ajuste num artigo só registrava o feedback e devolvia o ticket
    para uma fila que ninguém puxava. Na prática o humano criticava e não
    acontecia nada, que é pior que não ter o botão.

    O que refazer depende do que foi criticado. Crítica só sobre a capa não
    reescreve o texto: trocar um texto que o humano já aprovou por outro que ele
    não pediu é regressão disfarçada de melhoria.
    """
    import tempfile

    from ghost_publisher import (_e_sobre_imagem, _e_sobre_texto, atualizar,
                                 briefing_de_capa, buscar, revisar_texto, subir_imagem)

    if tentativa > MAX_REFACOES:
        return {"ok": False, "erro": f"teto de {MAX_REFACOES} refações atingido; "
                                     "o ticket fica na fila para revisão humana"}

    post_id = outcome_anterior.get("publish_ref")
    if not post_id:
        return {"ok": False, "erro": "outcome sem publish_ref"}
    post = buscar(post_id)
    if not post:
        return {"ok": False, "erro": f"artigo {post_id} não encontrado"}

    feito: list[str] = []

    if _e_sobre_texto(feedback):
        novo_html = revisar_texto(post, feedback)
        if novo_html:
            erro = atualizar(post_id, html=novo_html)
            feito.append("texto" if not erro else f"texto falhou ({erro})")

    if _e_sobre_imagem(feedback) or not (post.get("feature_image") or "").strip():
        from thumbnail_maker import gerar, montar_prompt

        brief = briefing_de_capa(post, feedback)
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "capa.png"
            erro = gerar(montar_prompt(brief["headline"], brief["hook"],
                                       brief["expressao"], brief["badge"]), destino)
            if erro:
                feito.append(f"capa falhou ({erro})")
            else:
                url, erro_upload = subir_imagem(destino)
                if erro_upload:
                    feito.append(f"upload da capa falhou ({erro_upload})")
                else:
                    atualizar(post_id, feature_image=url)
                    feito.append("capa")

    if not any(p in ("texto", "capa") for p in feito):
        return {"ok": False, "erro": f"nada foi refeito: {feito or 'sem ação aplicável'}"}

    atualizado = buscar(post_id) or post
    from ghost_publisher import resumo_para_aprovacao

    resumo = resumo_para_aprovacao(atualizado)
    capa = (atualizado.get("feature_image") or "").strip()
    novo = dict(outcome_anterior)
    novo["publish_content"] = resumo
    novo["publish_media"] = [capa] if capa else []
    novo["result"] = f"Versão {tentativa + 1} do artigo '{atualizado.get('title')}'"

    try:
        from sdk_client import evo

        evo.post("/api/approvals", {
            "gate_type": "publish",
            "ticket_id": ticket_id,
            "agent": "pixel-social-media",
            "payload": {"title": f"[v{tentativa + 1}] Publicar no blog: {atualizado.get('title')}",
                        "body": f"Refeito ({', '.join(feito)}) com a crítica: {feedback[:250]}\n\n{resumo[:500]}",
                        "outcome": novo},
        })
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": str(exc)}
    return {"ok": True, "tentativa": tentativa + 1, "refeito": feito}


def aprovar_artigo(post_id: str, *, publicar_em: str | None = None,
                   dry_run: bool = False) -> dict:
    """Abre o gate do artigo — estágio 1, antes de qualquer rede.

    O humano lê o resumo, confere os CTAs e vê a capa; aprovar publica (ou
    agenda) no Ghost, o que dispara o webhook e só então deriva as redes, cada
    uma com seu próprio gate. Reprovar encerra ali: nenhum post de rede nasce
    de artigo que ninguém liberou.

    `publicar_em` em ISO-8601 UTC agenda; ausente publica ao aprovar.
    """
    from ghost_publisher import buscar, resumo_para_aprovacao

    post = buscar(post_id)
    if not post:
        return {"ok": False, "erro": f"post {post_id} não encontrado no Ghost"}
    if post.get("status") == "published":
        return {"ok": True, "ignorado": "artigo já está publicado"}

    resumo = resumo_para_aprovacao(post)
    capa = (post.get("feature_image") or "").strip()
    outcome = {
        "action": "work",
        "result": f"Publicar artigo '{post.get('title')}'",
        "publish_intent": True,
        "publish_target": "blog",
        # O id do artigo é o que será publicado. O texto abaixo é só o que o
        # humano lê para decidir — nunca vira conteúdo publicado.
        "publish_ref": post.get("id"),
        "publish_content": resumo,
        "publish_media": [capa] if capa else [],
        "publish_at": publicar_em,
        "source_url": post.get("url"),
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "outcome": outcome}

    try:
        from sdk_client import evo

        ticket = evo.post("/api/tickets", {
            "title": f"Publicar no blog: {post.get('title')}",
            "description": f"Revisão do artigo antes de publicar. Preview: {post.get('url') or ''}".strip(),
            "assignee_agent": "pixel-social-media",
            "priority": "high",
            "status": "review",
        })
        ticket_id = (ticket or {}).get("id")
        if not ticket_id:
            raise RuntimeError(f"POST /api/tickets não devolveu id: {ticket!r}")

        evo.post("/api/approvals", {
            "gate_type": "publish",
            "ticket_id": ticket_id,
            "agent": "pixel-social-media",
            "payload": {"title": f"Publicar no blog: {post.get('title')}",
                        "body": resumo[:800], "outcome": outcome},
        })
        return {"ok": True, "aprovacao": "aberta", "ticket": ticket_id,
                "publish_at": publicar_em, "preview": post.get("url")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": str(exc)}


def distribuir_do_webhook(payload: dict, **kwargs) -> dict:
    """Entrada do trigger: extrai o id do evento post.published do Ghost."""
    post = (payload or {}).get("post") or {}
    atual = post.get("current") or {}
    post_id = atual.get("id") or post.get("id")
    if not post_id:
        return {"ok": False, "erro": "payload do Ghost sem post.current.id"}
    return distribuir(post_id, **kwargs)
