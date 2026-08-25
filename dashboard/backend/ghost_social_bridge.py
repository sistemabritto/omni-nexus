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

# Margem que separa o limite nominal da plataforma do teto que a esteira mira.
#
# Entre 28/07 e 02/08/2026, DEZ derivações do X (e uma do Threads) foram
# aprovadas no Telegram e nunca saíram: o Postiz devolveu
# `400 {"provider":"x","message":"post is too long, please fix it"}` e a
# aprovação parou em `approved`, sem virar `published`. O humano aprovava e o
# post simplesmente não existia.
#
# A causa não é o corte estar errado — é ele estar CERTO DEMAIS. `garantir_link`
# calculava a sobra para o texto final medir exatamente `LIMITES[rede]`, então
# todo post do X saía entre 270 e 280 caracteres, colado no teto. Aí a régua do
# validador que está no caminho diverge da nossa por alguns caracteres e o post
# inteiro cai.
#
# Os dados das 20 derivações registradas mostram onde a régua deles está, e é em
# BYTES, não em caracteres (ver `medida`):
#
#     X        publicou com até 272 bytes · recusou a partir de 276
#     Threads  publicou com até 501 bytes · recusou a partir de 502
#
# Note o par que só bytes explica: um post de 271 caracteres foi recusado e um
# de 272 passou — o primeiro tinha quatro acentos (276 bytes), o segundo nenhum.
# Contar `len()` em caracteres é otimista com texto em português exatamente na
# hora em que a margem importa.
#
# 5% de folga põe o teto do X em 266 bytes e o do Threads em 475, ambos dentro
# da faixa comprovadamente aceita. O preço é uma dúzia de caracteres a menos por
# post; o preço de não ter a folga é o post não existir.
MARGEM_DE_SEGURANCA = 0.05


def medida(texto: str) -> int:
    """Tamanho do texto na régua que decide de fato: bytes UTF-8.

    `len()` conta "ç" como 1 e o validador do Postiz conta como 2. A diferença
    é invisível em post curto e decide a publicação em post colado no limite,
    que é justamente o que a esteira produz.
    """
    return len((texto or "").encode("utf-8"))


def teto_de(rede: str) -> int:
    """Orçamento em bytes para a rede, já com a margem descontada."""
    return int(LIMITES.get(rede, 280) * (1 - MARGEM_DE_SEGURANCA))


def _fatiar(texto: str, limite: int) -> str:
    """Maior prefixo de `texto` que cabe em `limite` bytes.

    `decode(errors="ignore")` descarta o caractere multibyte que a fatia
    partiu ao meio — cortar bytes crus num "ã" produziria lixo no post.
    """
    if medida(texto) <= limite:
        return texto
    return texto.encode("utf-8")[:limite].decode("utf-8", "ignore")

# Redes em que o link do artigo tem de estar no corpo do post. No LinkedIn ele
# vai no primeiro comentário e no Threads não vai link nenhum (post recompensa)
# — nessas duas um link no corpo é erro, não esquecimento.
# Threads entrou aqui em 2026-07-26, por decisão do Felipe.
#
# O formato original era "post recompensa": sem link, fechando com pedido de
# comentário. A teoria era não perder alcance. A prática do primeiro post real
# foi outra — o texto estourou os 500 caracteres, o corte comeu o fecho, e o
# post foi ao ar terminando em "Resultado?", sem link e sem chamada nenhuma.
# Um post que não leva a lugar nenhum não preserva alcance, desperdiça.
#
# Com o link em LINK_NO_CORPO, `garantir_link` reserva o espaço dele ANTES de
# cortar o corpo. O link deixa de ser a primeira coisa que o truncamento come
# e passa a ser a última que sobra.
LINK_NO_CORPO = ("x", "threads")

# Redes em que o link sai num comentário do próprio post. O texto do LinkedIn
# fecha com "está no primeiro comentário" — promessa que o sistema precisa
# cumprir, senão o post manda o leitor para um comentário que não existe.
LINK_NO_COMENTARIO = ("linkedin",)

# O link custa o que ele mede, em toda rede.
#
# A regra do X é que toda URL conta 23 caracteres (o t.co encurta), e a primeira
# versão disto reservava 23 para não comer um terço do post à toa. Só que quem
# recusa o post não é o X — é o Postiz, que valida o texto ANTES de enviar e
# mede o comprimento bruto: um post de 293 caracteres reais levou
# `400 {"provider":"x","message":"post is too long, please fix it"}`. Vale a
# regra do validador que está no caminho, não a da plataforma no fim dele.
CUSTO_DO_LINK: dict[str, int] = {}

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
- NUNCA use travessão (— ou –). Reescreva com vírgula, ponto ou dois-pontos.
  É gramatical em português, mas hoje lê como assinatura de texto de IA.
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
    # Máx 400 e não 500: os ~100 restantes são a reserva do link. Pedir 500 ao
    # modelo garantia que o corte comesse o fecho — foi o que aconteceu no
    # primeiro post real, que terminou em "Resultado?" e não levava a lugar
    # nenhum.
    "threads": "Máx 400 caracteres. Conversacional, mais solto que o LinkedIn. "
               "No máximo 1 hashtag. Entregue uma ideia completa e feche a frase — "
               "não deixe pergunta no ar. O link do artigo é acrescentado depois, "
               "então NÃO escreva o link nem 'link na bio'.",
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


def resolver_url(post: dict) -> str:
    """URL pública do post, nunca a URL de preview /p/<uuid>/.

    O Ghost devolve /p/<uuid>/ para posts em draft — essa URL é a que
    virava o link no post social. Mas /p/ não é pública: quem clica cai
    em 404. Se o post tem slug, usamos a URL canônica; se não (draft
    real), devolve a preview.
    """
    url = post.get("url", "") or ""
    slug = post.get("slug", "") or ""
    base = (os.environ.get("GHOST_URL") or "").strip().rstrip("/")
    if "/p/" in url and slug and base:
        return f"{base}/{slug}/"
    return url


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

    `limite` é orçamento em BYTES (ver `medida`), e o retorno o respeita
    inclusive contando a reticência que o corte acrescenta — ela custa 3 bytes,
    e devolver um texto 2 bytes maior que o pedido é como o post do X chegava
    ao Postiz estourado.
    """
    texto = (texto or "").strip().strip('"').strip()
    prev = None
    while prev != texto:                      # rótulo e régua podem vir empilhados
        prev = texto
        texto = _PREAMBULO.sub("", texto).strip()
        texto = _REGUA.sub("", texto, count=1).strip() if _REGUA.match(texto) else texto
    # Antes do corte, não depois: trocar travessão por vírgula muda o tamanho,
    # e um post de X medido a 280 antes da troca estoura o limite depois.
    from escritor_de_artigo import sem_travessao

    texto = sem_travessao(texto)
    if medida(texto) <= limite:
        return texto
    corte = _fatiar(texto, limite)
    fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "), corte.rfind("\n"))
    # A fronteira de frase vale quando sobra post; na primeira metade do corte
    # ela devolveria um fiapo do texto original.
    if fim > len(corte) * 0.5:
        return corte[: fim + 1].strip()
    espaco = corte.rfind(" ")
    cortado = (corte[:espaco] if espaco > 0 else corte).rstrip(" ,;:-")
    while cortado and medida(cortado + "…") > limite:
        cortado = cortado[:-1].rstrip(" ,;:-")
    return cortado + "…"


def link_com_origem(link: str, rede: str, titulo: str = "") -> str:
    """O link do artigo carregando a rede de onde o clique veio.

    Sem isto o site registra tudo como "direct": em 30 dias, 134 de 141 visitas
    chegaram sem origem, e não havia como saber se o tráfego dos funis vinha do
    blog, do X ou de indicação.
    """
    try:
        from utm import marcar

        return marcar(link, rede, campanha=titulo)
    except Exception:  # noqa: BLE001 — link sem marcação ainda é link
        return link


def comentarios_da_rede(rede: str, link: str, titulo: str = "") -> list[str]:
    """Comentários a encadear no post — hoje, o link que o corpo prometeu.

    Só o LinkedIn usa: o formato manda o link para o primeiro comentário para
    não perder alcance, e o texto aprovado diz isso ao leitor em voz alta.
    """
    if rede not in LINK_NO_COMENTARIO or not link:
        return []
    return [f"Artigo completo: {link_com_origem(link, rede, titulo)}"]


def garantir_link(texto: str, link: str, rede: str, titulo: str = "") -> str:
    """Anexa o link do artigo quando a rede exige e o modelo esqueceu.

    O FORMATO já manda "Link no fim" para o X, mas pedir não é garantir: uma
    derivação real saiu no X com duas frases e nenhum link, virando um
    comentário solto que não leva a lugar nenhum. O fallback sem modelo sempre
    põe o link — o caminho do modelo precisava da mesma garantia.

    Idempotente: link já presente no texto sai intacto, inclusive quando o
    modelo o pôs no meio em vez do fim.
    """
    if rede not in LINK_NO_CORPO or not link or link in texto:
        return texto
    # Marcado com a rede de origem antes de medir: o UTM ocupa espaço real no
    # limite de caracteres, e reservar sem contá-lo estouraria o post do X —
    # que é exatamente como o Postiz devolveu 400 "post is too long".
    marcado = link_com_origem(link, rede, titulo)
    sobra = teto_de(rede) - CUSTO_DO_LINK.get(rede, medida(marcado)) - 2  # 2 = "\n\n"
    if sobra <= 0:
        return texto
    return f"{limpar(texto, sobra)}\n\n{marcado}"


def adaptar(post: dict, rede: str) -> str:
    """Versão da rede via x.ai; sem chave ou em erro, cai num fallback que não inventa nada."""
    titulo = post.get("title", "")
    resumo = post.get("custom_excerpt") or post.get("excerpt") or ""
    link = resolver_url(post)
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
                    return garantir_link(limpar(txt, teto_de(rede)), link, rede, titulo)
        except Exception:  # noqa: BLE001 — fallback abaixo cobre qualquer falha
            pass

    base = f"{titulo}\n\n{resumo}"
    if rede == "linkedin":
        base += "\n\nLink no primeiro comentário."
    # X e Threads recebem o link por `garantir_link` abaixo, que reserva o
    # espaço dele antes de cortar. Anexar aqui à mão duplicaria em uma rede e
    # esqueceria na outra — foi assim que o Threads foi ao ar sem link.
    return garantir_link(limpar(base, teto_de(rede)), link, rede, titulo)


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


def redes_ja_derivadas(post_id: str) -> set[str]:
    """Redes que já têm aprovação aberta para este artigo.

    Chave da idempotência de toda a derivação. Três caminhos independentes
    podem mandar derivar o mesmo artigo — o gate do blog ao publicar na hora, o
    webhook `post.published` do Ghost e o varredor de agendados — e sem esta
    checagem cada um abriria seu próprio trio de aprovações. O Felipe receberia
    o mesmo post três vezes no Telegram, que é exatamente o ruído que
    `aprovar_artigo` já aprendeu a evitar no gate do artigo.

    Olha TODOS os estados, não só `pending`: uma versão já aprovada, rejeitada
    ou publicada também significa que aquela rede já foi trabalhada. Derivar de
    novo o que o humano rejeitou seria insistir num texto que ele recusou.

    Falha para conjunto vazio de propósito. Sem conseguir consultar, o pior
    caso é uma aprovação repetida — que dá para rejeitar; o caso oposto é o
    artigo nunca chegar às redes, que é o problema que estamos corrigindo.
    """
    try:
        from sdk_client import evo

        resposta = evo.get("/api/approvals", {"status": "all", "gate_type": "publish"}) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[ghost_social_bridge] não consegui checar derivações anteriores ({exc})",
              flush=True)
        return set()

    achadas: set[str] = set()
    for a in (resposta.get("approvals") or []):
        pub = a.get("publish") or {}
        # `source_id` é o artigo de origem do post de rede; `publish_ref` é o
        # artigo do gate do blog. Só o primeiro identifica uma derivação.
        if pub.get("source_id") != post_id or pub.get("target") not in REDES:
            continue
        if _de_artigo_nao_publicado(pub.get("source_url")):
            continue
        achadas.add(pub["target"])
    return achadas


def _de_artigo_nao_publicado(source_url: str | None) -> bool:
    """A derivação foi feita quando o artigo ainda não estava no ar?

    Reconhecida pela URL de preview do Ghost (`/p/<uuid>/`), que é a única que
    existe antes de o artigo publicar. Uma derivação assim **não conta como
    feita**: o link dela morre no momento em que o artigo ganha o slug real.

    Sem esta exceção, as oito aprovações inválidas de 05/08/2026 travariam a
    rederivação para sempre — `redes_ja_derivadas` olha TODOS os estados de
    propósito, então rejeitá-las seria o mesmo que apagar aqueles três artigos
    das redes. A regra é estreita a ponto de não poder confundir: artigo
    publicado nunca tem `/p/` na URL.
    """
    return "/p/" in (source_url or "")


def distribuir(post_id: str, *, em_horas: float = 2.0, dry_run: bool = False) -> dict:
    """Gera as versões e abre uma aprovação por rede. Nada é publicado aqui."""
    post = buscar_post(post_id)
    if not post:
        return {"ok": False, "erro": f"post {post_id} não encontrado no Ghost"}
    # SÓ `published`. `scheduled` já esteve aceito aqui, com o argumento de que a
    # URL de preview (`/p/<uuid>/`) serve para revisar antes de o artigo ir ao ar.
    # Não serve, e o custo apareceu inteiro em 05/08/2026: os três artigos do dia
    # estavam agendados para 12h, 16h e 21h, oito aprovações de rede nasceram
    # carregando `blog.sistemabritto.com.br/p/`, e o Felipe clicou e tomou 404 —
    # está escrito no motivo da aprovação 137.
    #
    # O erro é estrutural, não cosmético:
    #   • a URL de preview morre quando o artigo publica com o slug real, então
    #     todo post aprovado sairia com link que deixa de valer;
    #   • `publish_at` da rede é +2h, então o post podia ir ao ar ANTES do
    #     artigo que ele anuncia;
    #   • o texto é gerado a partir de um artigo que ainda pode mudar no gate.
    #
    # Quem cobre o agendado é o varredor de 15 min (`derivar_pendentes`), depois
    # de o Ghost publicar. Esperar 15 minutos custa nada; publicar link quebrado
    # custa o clique que o artigo inteiro existe para conseguir.
    if post.get("status") != "published":
        return {"ok": True, "ignorado": f"post está '{post.get('status')}', não 'published' — "
                                        "o varredor deriva quando ele for ao ar"}

    quando = datetime.now(timezone.utc) + timedelta(hours=em_horas)
    resultado: dict = {"ok": True, "post": post.get("title"), "redes": {}, "pulados": {}}
    # Em dry-run ninguém grava nada, então não há o que duplicar — e consultar
    # a API só para simular tornaria o modo de teste dependente do servidor.
    ja_feitas = set() if dry_run else redes_ja_derivadas(post_id)
    midia, sem_midia = midia_do_post(post)
    if not midia:
        # Post sem imagem ainda vale — só não pode sair calado. Um artigo sem
        # capa, ou com a capa num host fora da allowlist do Postiz, produz três
        # posts sem imagem, e sem esta linha ninguém descobre por quê.
        resultado["aviso_midia"] = sem_midia

    for rede in REDES:
        if rede in ja_feitas:
            resultado["pulados"][rede] = "já derivado (aprovação existente)"
            continue
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
            # A capa do artigo vai em todas as redes. A regra anterior mandava
            # imagem só para o Instagram, com o argumento de que nas outras a
            # capa competiria com o preview do link — e como o Instagram saiu
            # deste gatilho (vídeo é outro esquema), na prática TODO post saía
            # sem imagem nenhuma. O argumento também não se sustenta nas três
            # redes que restaram: no LinkedIn o link vai no primeiro comentário
            # e no Threads não vai link nenhum, então não existe preview para
            # competir; e no X uma imagem própria rende mais que o card de link.
            "publish_media": midia,
            "publish_comments": comentarios_da_rede(rede, resolver_url(post) or "", post.get("title") or ""),
            "publish_at": agendado.isoformat().replace("+00:00", "Z"),
            # Link do artigo, para conferir o texto completo na hora de aprovar.
            # Em draft o Ghost devolve a URL de preview (/p/<uuid>/), que abre
            # sem login — vale tanto para revisar antes quanto depois de publicar.
            "source_url": resolver_url(post),
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
    # A capa é relida do artigo, não herdada do outcome anterior: entre uma
    # versão e outra o gate do blog pode ter trocado a imagem, e republicar a
    # antiga entregaria uma thumb que o Felipe já reprovou.
    novo["publish_media"] = midia_do_post(post)[0]
    novo["publish_comments"] = comentarios_da_rede(rede, resolver_url(post) or "", post.get("title") or "")
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
    from pathlib import Path

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
    # Medida antes de mexer, para o card poder provar que mudou. "Refeito
    # (texto)" é afirmação nossa; "1492 → 1308 palavras" é evidência.
    palavras_antes = len((post.get("plaintext") or "").split())

    if _e_sobre_texto(feedback):
        novo_html = revisar_texto(post, feedback)
        if novo_html:
            erro = atualizar(post_id, html=novo_html)
            feito.append("texto" if not erro else f"texto falhou ({erro})")

    if _e_sobre_imagem(feedback) or not (post.get("feature_image") or "").strip():
        from thumbnail_maker import gerar, montar_prompt, variacao_de

        # A variação sai do par (artigo, feedback): o mesmo feedback repetido
        # devolve a mesma capa — retry é idempotente —, mas um feedback novo
        # cai em outra pose e outro registro facial. Repetir a arte anterior
        # depois de o autor pedir outra é a pior resposta possível ao gate.
        variacao = int(hashlib.sha1(f"{post_id}:{feedback}".encode()).hexdigest()[:8], 16)
        var = variacao_de(variacao)
        brief = briefing_de_capa(post, feedback, registro=var["registro"])
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "capa.png"
            erro = gerar(montar_prompt(brief["headline"], brief["hook"], brief["expressao"],
                                       brief["badge"], variacao=variacao),
                         destino, referencia=var["pose"]["arquivo"])
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

    # A prova de que mudou, em números. Dizer "refeito (texto)" e mostrar um
    # resumo estrutural de cara idêntica é o que fez o Felipe concluir que o
    # sistema tinha devolvido o mesmo artigo — o texto tinha sido reescrito
    # inteiro, mas nada no card dizia isso.
    palavras_depois = len((atualizado.get("plaintext") or "").split())
    mudancas = []
    if "texto" in feito:
        mudancas.append(f"texto reescrito: {palavras_antes} → {palavras_depois} palavras")
    if "capa" in feito:
        mudancas.append("capa refeita")
    for item in feito:
        if "falhou" in item:
            mudancas.append(f"⚠ {item}")
    if not mudancas:
        mudancas.append(", ".join(feito))

    try:
        from sdk_client import evo

        evo.post("/api/approvals", {
            "gate_type": "publish",
            "ticket_id": ticket_id,
            "agent": "pixel-social-media",
            "payload": {"title": f"[v{tentativa + 1}] Publicar no blog: {atualizado.get('title')}",
                        "body": (f"✏️ {' · '.join(mudancas)}\n"
                                 f"Crítica aplicada: {feedback[:220]}\n\n{resumo}"),
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

    # Um gate por artigo, não um por execução.
    #
    # Reprocessar a mesma pauta — o que acontece a cada correção, e vai
    # acontecer sozinho quando a rotina diária reprocessar uma pauta que
    # falhou — abria um gate novo e deixava o anterior pendurado. Em 26/07 o
    # Felipe recebeu três aprovações do MESMO artigo e teve de rejeitar as
    # três. Notificação repetida não é só ruído: ensina a ignorar o canal, e
    # é justamente esse canal que sustenta o human-in-the-loop.
    if not dry_run:
        try:
            from sdk_client import evo

            pendentes = (evo.get("/api/approvals", {"status": "pending"}) or {})
            for a in (pendentes.get("approvals") or []):
                if ((a.get("publish") or {}).get("publish_ref")) == post.get("id"):
                    return {"ok": True, "ignorado": f"já existe gate pendente (#{a.get('id')}) "
                                                    "para este artigo",
                            "aprovacao": a.get("id")}
        except Exception as exc:  # noqa: BLE001 — sem a checagem, o pior caso é o de hoje
            log_aviso = f"não consegui checar gates pendentes ({exc})"
            print(f"[ghost_social_bridge] {log_aviso}", flush=True)

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
        "source_url": resolver_url(post),
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


# Janela do varredor. 26h e não 24 porque o varredor roda a cada 15 minutos e
# o relógio do Ghost não é o nosso: uma folga de duas horas cobre atraso de
# agendamento e diferença de fuso sem alcançar o artigo de anteontem.
JANELA_VARREDURA_HORAS = float(os.environ.get("GHOST_VARREDURA_HORAS", "26"))


def posts_publicados_recentes(horas: float = JANELA_VARREDURA_HORAS,
                              limite: int = 15) -> list[dict]:
    """Artigos que o Ghost publicou na janela, do mais recente para o mais antigo.

    A data é filtrada aqui e não em NQL de propósito: `published_at:>'...'` é
    sintaxe que o Ghost recusa calado quando o formato não bate, e um filtro
    que devolve zero por erro de aspas é indistinguível de "não há artigo novo".
    Ordenar e cortar em Python custa uma lista de 15 itens e não mente.
    """
    url = (os.environ.get("GHOST_URL") or "").strip().rstrip("/")
    key = (os.environ.get("GHOST_ADMIN_API_KEY") or "").strip()
    if not url or not key:
        return []
    # `published` e nada mais. Enquanto `scheduled` entrava aqui, o varredor
    # derivava artigo que ainda não existia no ar — ver o bloco em `distribuir`.
    # Um agendado só some da varredura por um caminho: publicar. Quando publica,
    # `published_at` cai dentro da janela de 26h e o varredor o pega no tick
    # seguinte, no máximo 15 minutos depois.
    r = requests.get(
        f"{url}/ghost/api/admin/posts/"
        f"?filter=status:published&order=published_at%20desc&limit={limite}"
        f"&fields=id,title,status,published_at,url",
        headers={"Authorization": f"Ghost {ghost_jwt(key)}", "User-Agent": UA_NAVEGADOR},
        timeout=45)
    if r.status_code >= 300:
        return []
    corte = datetime.now(timezone.utc) - timedelta(hours=horas)
    recentes = []
    for p in (r.json().get("posts") or []):
        quando = (p.get("published_at") or "").replace("Z", "+00:00")
        try:
            if datetime.fromisoformat(quando) >= corte:
                recentes.append(p)
        except ValueError:
            continue
    return recentes


def derivar_pendentes(horas: float = JANELA_VARREDURA_HORAS,
                      *, dry_run: bool = False) -> dict:
    """Deriva as redes de todo artigo publicado na janela que ainda não derivou.

    A rede de segurança do artigo AGENDADO, e a razão de ela existir:

    O gate do blog aceita `publish_at`. Quando o humano agenda, o Ghost devolve
    `status="scheduled"` e publica sozinho horas depois — sem passar por código
    nosso. `_run_blog_publish` só derivava as redes no caminho da publicação
    imediata, então todo artigo agendado nascia órfão. Em 27/07/2026 os dois
    artigos do dia foram agendados (13h e 18h BRT), o Ghost publicou os dois, e
    nenhum post de X, LinkedIn ou Threads existiu.

    O webhook `post.published` cobriria isso, mas não está cadastrado e não dá
    para cadastrar por aqui: a chave de Admin API devolve 403 NoPermissionError
    no endpoint de integrações, ou seja, criar o webhook exige alguém logado no
    painel do Ghost. Uma etapa manual que ninguém lembra de repetir não é
    garantia; este varredor é.

    Idempotente por `redes_ja_derivadas`, então rodar a cada 15 minutos sobre a
    mesma janela não empilha aprovação. Nada é publicado: cada rede continua
    parando no seu gate.
    """
    resultado: dict = {"ok": True, "janela_horas": horas, "artigos": []}
    for post in posts_publicados_recentes(horas):
        post_id = post.get("id") or ""
        faltando = [r for r in REDES if r not in redes_ja_derivadas(post_id)]
        item = {"id": post_id, "titulo": post.get("title"),
                "published_at": post.get("published_at"), "faltando": faltando}
        if not faltando:
            item["acao"] = "nada a fazer"
        elif dry_run:
            item["acao"] = "derivaria (dry-run)"
        else:
            item["acao"] = "derivado"
            item["resultado"] = distribuir(post_id)
            if not item["resultado"].get("ok"):
                resultado["ok"] = False
        resultado["artigos"].append(item)
    return resultado


def distribuir_do_webhook(payload: dict, **kwargs) -> dict:
    """Entrada do trigger: extrai o id do evento post.published do Ghost."""
    post = (payload or {}).get("post") or {}
    atual = post.get("current") or {}
    post_id = atual.get("id") or post.get("id")
    if not post_id:
        return {"ok": False, "erro": "payload do Ghost sem post.current.id"}
    return distribuir(post_id, **kwargs)
