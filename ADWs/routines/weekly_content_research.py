#!/usr/bin/env python3
"""Research semanal de pauta — roda todo domingo e abastece os 21 posts da semana.

Objetivo 4 (2026-07-25), no modelo que o Felipe pediu: em vez de planejar 5
semanas à frente, o ciclo é curto e recorrente. Todo domingo esta rotina:

  1. levanta o que aconteceu na semana (Grok/x.ai com web+X, só fato com fonte)
  2. cruza com dados reais de keyword (DataForSEO via OpenSEO MCP, mercado BR)
  3. propõe 21 pautas priorizadas — 3 por dia, segunda a domingo
  4. abre UM ticket de aprovação; nada vai pro ar sem o humano dizer sim

Por que curto: o tema muda toda semana. Uma pauta escrita com 30 dias de
antecedência chega velha, e o gancho de notícia — que é o que faz a LLM citar —
tem validade de dias, não de mês.

Ordem deliberada das etapas: a notícia entra ANTES da keyword. Keyword sozinha
dá volume mas não dá ângulo; notícia sozinha dá ângulo mas não dá tráfego. O
cruzamento é o que produz pauta que ranqueia E é citável.

Uso:
    python ADWs/routines/weekly_content_research.py            # ciclo completo
    python ADWs/routines/weekly_content_research.py --dry-run  # não cria ticket
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

OUT_DIR = REPO / "workspace" / "social" / "research"
XAI_URL = "https://api.x.ai/v1/responses"
XAI_MODEL = os.environ.get("XAI_MODEL", "grok-4.20-non-reasoning")
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = os.environ.get("PERPLEXITY_MODEL", "sonar-pro")

# Projeto BR no OpenSEO (mercado 2076/pt). Trocar aqui se o projeto for recriado.
OPENSEO_PROJECT = os.environ.get("OPENSEO_PROJECT_ID", "894ccc15-bc71-48e3-adcb-c05789b5d4fd")
OPENSEO_URL = os.environ.get("OPENSEO_MCP_URL", "http://openseo:3001/mcp")

POSTS_POR_DIA = 3
DIAS = 7


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


# ── 1. notícia da semana (com fonte, senão não entra) ────────────────────

def pesquisar_noticias(inicio: date, fim: date) -> str:
    import requests

    key = os.environ.get("XAI_API_KEY", "").strip()

    prompt = f"""Pesquise (web + X) o que aconteceu em INTELIGÊNCIA ARTIFICIAL entre {inicio:%d/%m/%Y} e {fim:%d/%m/%Y}.
Responda em português do Brasil.

Contexto: Sistema Britto vende automação de conteúdo multi-rede operada por agentes de IA
(produto SocialJobs) para donos de negócio digital brasileiros que querem tráfego qualificado
para vendas online. O público NÃO é desenvolvedor.

Liste até 10 fatos da semana que sirvam de gancho para pauta de blog. Para cada um:
- FATO: o que aconteceu, com data
- FONTE: URL
- GANCHO: como conecta com dono de negócio digital
- SATURACAO_PTBR: alta/media/baixa

REGRA ABSOLUTA: se não encontrou na busca, NÃO inclua. Não complete com conhecimento prévio.
Prefiro 3 fatos verificados a 10 inventados. Priorize saturação baixa em português."""

    txt = ""
    if key:
        try:
            r = requests.post(
                XAI_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": XAI_MODEL, "input": [{"role": "user", "content": prompt}],
                      "tools": [{"type": "web_search"}, {"type": "x_search"}]},
                timeout=900,
            )
            if r.status_code == 200:
                for item in r.json().get("output", []):
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "output_text":
                                txt += c.get("text", "")
            else:
                log(f"x.ai respondeu {r.status_code}; tentando Perplexity.")
        except Exception as exc:  # noqa: BLE001
            log(f"x.ai falhou ({exc}); tentando Perplexity.")

    if not txt.strip():
        perplexity_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
        if not perplexity_key:
            log("XAI_API_KEY/ PERPLEXITY_API_KEY ausentes — etapa de notícia pulada.")
            return ""
        try:
            r = requests.post(
                PERPLEXITY_URL,
                headers={"Authorization": f"Bearer {perplexity_key}", "Content-Type": "application/json"},
                json={"model": PERPLEXITY_MODEL,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=900,
            )
            if r.status_code == 200:
                txt = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                log(f"Perplexity respondeu {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            log(f"Perplexity falhou: {exc}")
    fatos = len(re.findall(r"(?im)^\s*\*{0,2}\d+\.", txt))
    log(f"notícia: {fatos} fato(s) com fonte, {len(txt)} chars")
    return txt


# ── 2. keywords reais (DataForSEO via OpenSEO MCP) ───────────────────────

def _mcp(payload: dict, timeout: int = 480) -> dict | None:
    """Chama o MCP do OpenSEO. Em Swarm o host é o alias `openseo` na overlay.

    O Host header vai explícito porque o OpenSEO roda atrás do Vite, que só
    aceita o host listado em `ALLOWED_HOST` (o domínio público). Chamando pelo
    alias da overlay, o header sai como `openseo` e o Vite responde 403
    "This host is not allowed" — a rotina abortava sem keyword nenhuma.
    Mandar o Host esperado resolve sem sair da rede interna e sem precisar
    reconfigurar um serviço de terceiro.
    """
    import requests

    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    host_esperado = (os.environ.get("OPENSEO_ALLOWED_HOST") or "seo.workflowapi.com.br").strip()
    # Só quando falamos com o alias interno; chamando o domínio público
    # direto, o Host já é o certo e forçá-lo seria redundante.
    if host_esperado and host_esperado not in OPENSEO_URL:
        headers["Host"] = host_esperado

    try:
        r = requests.post(OPENSEO_URL, json=payload, timeout=timeout, headers=headers)
        if r.status_code != 200:
            log(f"OpenSEO MCP {r.status_code}: {r.text[:160]}")
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        log(f"OpenSEO MCP indisponível: {exc}")
        return None


RUIDO = re.compile(
    r"(vaga|salario|salário|concurso|prf|aeroporto|sinônim|sinonim|o que faz um|estágio|estagio|"
    r"conteudo 18|adulto|enem|academic|acadêmic|escolar|estudar|curricul|slides|powerpoint|"
    r"apresenta|redação|monografia|tcc|baixar|download|crack|apk|\bgb\b|clonar|espionar|hack|"
    r"bom dia|boa noite|boa tarde|mensagem de|frases|figurinha|papel de parede|png|emoji|"
    # Ampliado em 2026-07-26 depois que a primeira fila de verdade veio com
    # "japinha do cv instagram" (14.800/mês), "analista de sistemas jr",
    # "caixa ferramenta plastica" e "salvador digital cadastro único". Volume
    # alto não é sinal de pauta boa quando a busca vem de outro público.
    r"curso|faculdade|graduação|graduacao|técnico em|tecnico em|\bead\b|senai|senac|"
    r"analista|\bjr\b|júnior|junior|pleno|sênior|senior|cbo|piso salarial|quanto ganha|"
    r"cad ?cam|autocad|solidworks|torno|usinagem|caixa|plastic|maleta|"
    r"cadastro único|cadastro unico|\bsus\b|prefeitura|inss|detran|cnh|"
    r"letra|musica|música|novela|jogo|futebol|receita|significado|sonho|signo)", re.I)
COMPRA = re.compile(
    r"(automat|automaç|chatbot|\bbot\b|agendar|agendamento|disparo|para empresas|empresarial|"
    r"business|crm|funil|lead|prospec|tráfego|trafego|conversão|conversao|ferramenta|plataforma|"
    # \b em "api": sem ele o regex casa dentro de "japinha", e "japinha do cv
    # instagram" (14.800/mês) entrou como a pauta nº 1 da primeira fila real.
    r"software|sistema|como (criar|fazer|automatizar|usar|integrar)|\bapi\b|integra|agente de ia|"
    r"marketing digital|gestão de redes|postar)", re.I)

# A trava que faltava. `COMPRA` casa palavras genéricas — "sistema",
# "ferramenta", "agendamento" — que aparecem em buscas de curso técnico,
# serviço público e caixa de plástico. Exigir também um termo do NOSSO domínio
# é o que separa "api whatsapp business" de "sistemas cad cam".
DOMINIO = re.compile(
    r"(whatsapp|instagram|tiktok|youtube|linkedin|facebook|threads|"
    r"\bia\b|inteligência artificial|inteligencia artificial|\bgpt\b|chatbot|agente|"
    r"marketing|vendas|lead|funil|tráfego|trafego|conversão|conversao|"
    r"\bcrm\b|automaç|automat|postar|post\b|conteúdo|conteudo|seguidor|engajamento|"
    r"atendimento|disparo|mensagem em massa|\bapi\b|integraç|n8n|zapier|webhook)", re.I)


# Seeds por funil. Cinco seeds vizinhas produziam 35 keywords que, depois do
# dedupe, viravam 13 pautas — abaixo das 21 que o ciclo precisa. O gargalo do
# ciclo semanal não é volume de busca, é DIVERSIDADE de assunto: keyword
# parecida vira pauta descartada, e pauta descartada é slot vazio na semana.
#
# Cada grupo aponta para um funil real, o que também alimenta a escolha de CTA
# em escritor_de_artigo — pauta sem funil claro é tráfego sem destino.
SEEDS_POR_FUNIL = {
    "whatsapp": [
        "chatbot whatsapp para empresas", "resposta automatica whatsapp",
        "whatsapp business api", "disparo em massa whatsapp",
        "atendimento automatizado whatsapp", "crm integrado ao whatsapp",
        "recuperar carrinho abandonado whatsapp", "agente de ia no whatsapp",
    ],
    "socialjobs": [
        "agendar post instagram", "automatizar redes sociais com ia",
        "criar conteudo com inteligencia artificial", "crescer no instagram organicamente",
        "ferramenta de agendamento de posts", "roteiro para reels",
        "youtube shorts para empresas", "calendario editorial redes sociais",
    ],
    "sistema": [
        "gerar leads com inteligencia artificial", "trafego qualificado",
        "automatizar processos da empresa com ia", "agentes de ia para negocios",
        "integrar sistemas com api", "reduzir custo operacional com automacao",
        "dashboard de metricas do negocio", "funil de vendas automatizado",
    ],
}

# Todas as seeds de cada funil, toda rodada.
#
# Com 3 por funil o afunilamento matava a semana: 1089 keywords brutas viravam
# 97 comerciais, o dedupe derrubava 77 (quase tudo era variação de "api
# whatsapp") e o julgamento de ICP deixava 11 para 21 slots. Amplitude na
# entrada é o que sustenta o volume na saída, e o cache absorve o custo — a
# segunda rodada da mesma janela não paga nada.
SEEDS_POR_RODADA = 8


def seeds_da_semana(hoje: date) -> list[str]:
    """Seeds desta rodada: um recorte rotativo de cada funil.

    A rotação usa o número da semana, então duas execuções na mesma semana
    pedem as mesmas seeds (previsível) e semanas seguidas pedem seeds
    diferentes (variedade).
    """
    semana = hoje.isocalendar().week
    escolhidas = []
    for grupo in SEEDS_POR_FUNIL.values():
        inicio = (semana * SEEDS_POR_RODADA) % len(grupo)
        girado = grupo[inicio:] + grupo[:inicio]
        escolhidas += girado[:SEEDS_POR_RODADA]
    return escolhidas


# Teto do research_keywords do OpenSEO. Seis seeds numa chamada devolvem
# "Input validation error" com 200 e zero linhas — o erro vem dentro do corpo,
# não no status, então mandar mais que isto falha em silêncio.
SEEDS_POR_CHAMADA = 5


def pesquisar_keywords(seeds: list[str]) -> list[dict]:
    """Consulta o OpenSEO em lotes e junta o resultado.

    Em lotes porque o MCP recusa mais de cinco seeds por chamada, e uma rodada
    precisa de nove para dar diversidade suficiente ao dedupe.
    """
    linhas: dict[str, dict] = {}

    # Cache primeiro. Cada seed já consultada nos últimos 30 dias é uma
    # chamada paga ao DataForSEO que não precisa acontecer de novo — o volume
    # que ele devolve é média de 12 meses e não muda de uma semana para outra.
    novas = list(seeds)
    try:
        from sdk_client import evo

        resposta = evo.post("/api/pautas/keywords", {"seeds": seeds}) or {}
        for kw in resposta.get("linhas", []):
            linhas.setdefault(kw["kw"], kw)
        novas = resposta.get("faltando", seeds)
        if resposta.get("em_cache"):
            log(f"cache: {resposta['em_cache']}/{len(seeds)} seeds reaproveitadas "
                f"({len(linhas)} keywords sem custo)")
    except Exception as exc:  # noqa: BLE001 — sem cache o pior caso é pagar de novo
        log(f"cache de keywords indisponível ({exc}); consultando tudo")

    if not novas:
        log("todas as seeds vieram do cache — nenhuma chamada à API")

    lotes = [novas[i:i + SEEDS_POR_CHAMADA] for i in range(0, len(novas), SEEDS_POR_CHAMADA)]
    for n, lote in enumerate(lotes, 1):
        payload = {"jsonrpc": "2.0", "id": n, "method": "tools/call", "params": {
            "name": "research_keywords",
            "arguments": {"projectId": OPENSEO_PROJECT, "resultLimit": 150,
                          "seeds": [{"seed": s, "locationCode": 2076, "languageCode": "pt"}
                                    for s in lote]}}}
        d = _mcp(payload)
        if not d:
            log(f"lote {n}/{len(lotes)} falhou — seguindo com o que já veio")
            continue
        grupos = d.get("result", {}).get("structuredContent", {}).get("results", [])
        if not grupos:
            # O OpenSEO devolve erro de validação com HTTP 200 e o motivo
            # enterrado no content. Sem este log, um lote inválido some.
            conteudo = str(d.get("result", {}).get("content", ""))[:160]
            log(f"lote {n}/{len(lotes)} sem resultados: {conteudo}")
            continue
        # Guardado por seed, não em bloco: assim uma rodada futura que reusa só
        # três das nove seeds aproveita exatamente essas três.
        para_guardar: dict[str, list[dict]] = {}
        for i, res in enumerate(grupos):
            seed = res.get("seed") or res.get("keyword") or (lote[i] if i < len(lote) else "")
            desta_seed = []
            for row in res.get("rows", []):
                kw = (row.get("keyword") or "").strip()
                if not kw:
                    continue
                dado = {"kw": kw, "vol": row.get("searchVolume") or 0,
                        "kd": row.get("keywordDifficulty"), "cpc": row.get("cpc")}
                desta_seed.append(dado)
                linhas.setdefault(kw, dado)
            if seed and desta_seed:
                para_guardar[seed] = desta_seed
        if para_guardar:
            try:
                from sdk_client import evo

                evo.post("/api/pautas/keywords", {"guardar": para_guardar})
            except Exception as exc:  # noqa: BLE001 — as keywords já estão em mãos
                log(f"não consegui cachear o lote {n} ({exc}); a próxima rodada repagará")
    cand = [r for r in linhas.values()
            if 40 <= r["vol"] <= 20000 and len(r["kw"].split()) >= 3
            and COMPRA.search(r["kw"]) and DOMINIO.search(r["kw"])
            and not RUIDO.search(r["kw"])]
    # ordena por retorno esperado: volume alto e dificuldade baixa primeiro
    cand.sort(key=lambda r: (-(r["vol"] / (1 + (r["kd"] or 0))), -r["vol"]))
    log(f"keywords: {len(linhas)} brutas -> {len(cand)} comerciais de cauda longa")
    return cand


# ── 3. não repetir o que o blog já cobre ─────────────────────────────────

# Palavras que não distinguem um assunto do outro. Sem removê-las, "resposta
# automática whatsapp" e "plano whatsapp business" pareceriam parentes só por
# compartilharem "whatsapp", e o filtro descartaria pauta boa.
_VAZIAS = {"de", "da", "do", "para", "por", "com", "sem", "em", "no", "na", "o", "a",
           "os", "as", "um", "uma", "e", "ou", "que", "como", "seu", "sua", "meu"}


def _nucleo(texto: str) -> set[str]:
    """Palavras que carregam o assunto, sem plural nem acento decidindo nada."""
    import unicodedata

    limpo = unicodedata.normalize("NFKD", (texto or "").lower())
    limpo = "".join(c for c in limpo if not unicodedata.combining(c))
    palavras = re.findall(r"[a-z0-9]+", limpo)
    # Corta o "s" final: "respostas automaticas" e "resposta automatica" são o
    # mesmo assunto, e foi exatamente esse par que apareceu duplicado na fila.
    return {p.rstrip("s") for p in palavras if p not in _VAZIAS and len(p) > 2}


def titulos_publicados() -> list[str]:
    """Títulos e keywords que o blog já cobre — para não canibalizar."""
    ja = []
    try:
        import requests
        from ghost_publisher import _config, _headers

        cfg = _config()
        if cfg:
            url, key = cfg
            r = requests.get(f"{url}/ghost/api/admin/posts/?limit=100&fields=title,status",
                             headers=_headers(key), timeout=45)
            if r.status_code < 300:
                ja += [p.get("title", "") for p in r.json().get("posts", [])]
    except Exception as exc:  # noqa: BLE001 — sem a lista o pior caso é repetir
        log(f"não consegui ler o blog para deduplicar ({exc})")
    try:
        from sdk_client import evo

        for p in (evo.get("/api/pautas", {"limit": 200}) or {}).get("pautas", []):
            if p.get("status") in ("escrita", "publicada"):
                ja.append(p.get("titulo") or p.get("keyword") or "")
    except Exception as exc:  # noqa: BLE001
        log(f"não consegui ler a fila para deduplicar ({exc})")
    return [t for t in ja if t]


def descartar_repetidas(keywords: list[dict], ja_cobertos: list[str]) -> list[dict]:
    """Tira keyword que repete assunto já publicado — ou outra da própria lista.

    Duas pautas quase idênticas na mesma semana disputam a mesma busca entre
    si (canibalização) e gastam dois dos 21 slots com um assunto só. Na
    primeira execução real, "respostas automaticas whatsapp" e "resposta
    automatica whatsapp" saíram juntas — e o blog já tinha publicado o tema
    naquele mesmo dia.
    """
    nucleos_cobertos = [_nucleo(t) for t in ja_cobertos]
    escolhidas: list[dict] = []
    nucleos_escolhidos: list[set] = []
    for kw in keywords:
        n = _nucleo(kw["kw"])
        if not n:
            continue
        # 60% das palavras em comum é o mesmo assunto dito de outro jeito.
        colide = any(len(n & outro) / len(n) >= 0.6
                     for outro in nucleos_cobertos + nucleos_escolhidos if outro)
        if colide:
            continue
        escolhidas.append(kw)
        nucleos_escolhidos.append(n)
    descartadas = len(keywords) - len(escolhidas)
    if descartadas:
        log(f"dedupe: {descartadas} keyword(s) repetiam assunto já coberto")
    return escolhidas


def alternar_funis(keywords: list[dict], alvo: int) -> list[dict]:
    """Rodízio entre os três funis, na ordem de retorno esperado dentro de cada.

    Sem isto a seleção é puramente por volume/dificuldade, e o WhatsApp — que
    tem volume de busca muito acima dos outros dois — leva a semana inteira. No
    ciclo de 27/07/2026 foi exatamente o que aconteceu: 18 das 21 pautas eram
    variação de "whatsapp alguma coisa", e os três posts de um mesmo dia
    falavam do mesmo assunto. O dedupe não pega isso, porque "bot para
    whatsapp" e "crm integrado ao whatsapp" são de fato pautas diferentes.

    O rodízio também resolve o efeito no leitor, e não só no total: como as
    pautas saem intercaladas e os dias são fatiados em blocos de três, cada dia
    nasce com um assunto de cada funil.

    **Cota por funil** (`ceil(alvo / nº de funis)`): sem teto o WhatsApp
    continuava estourando a semana mesmo intercalado — o rodízio só ordena,
    não limita, e um ciclo como o de 03/08/2026 nasceu com 7 de 8 pautas sobre
    WhatsApp. Com a cota, o WhatsApp fica limitado à sua fatia igualitária e o
    que sobrar de slot vago volta para `pautas_do_x` no main(), que é a fonte
    que devolve diversidade de verdade. Funil que esgota não segura os outros:
    se nenhum funil tiver mais keywords, a lista simplesmente fica curta e o X
    cobre.
    """
    from escritor_de_artigo import FUNIS, funil_de

    filas: dict[str, list[dict]] = {}
    for kw in keywords:
        filas.setdefault(funil_de(kw["kw"]), []).append(kw)

    ordem = [f for f in FUNIS if filas.get(f)]
    # Cota por funil sobre os funis PRESENTES: com os três na fila, cada um leva
    # no máximo ceil(alvo/3); com só dois, ceil(alvo/2). Um funil único não é
    # cortado — não há o que equilibrar, e o corte aí só mutilaria a semana.
    cota = max(1, math.ceil(alvo / max(1, len(ordem)))) if ordem else alvo
    usados = {f: 0 for f in ordem}
    saida: list[dict] = []

    # Primeira passada: round-robin com teto por funil. Cada um entra com no
    # máximo `cota` pautas, na ordem de retorno esperado.
    while len(saida) < alvo and any(filas.values()):
        progrediu = False
        for f in ordem:
            if filas[f] and usados[f] < cota:
                saida.append(filas[f].pop(0))
                usados[f] += 1
                progrediu = True
                if len(saida) >= alvo:
                    break
        if not progrediu:
            break

    # Segunda passada: algum funil esgotou abaixo da cota? NÃO é preenchido
    # pelo que sobrou de outro — aí o WhatsApp voltaria a estourar. O slot
    # vago volta para o main(), que chama pautas_do_x para fechar a semana.
    if keywords:
        distribuicao = ", ".join(f"{f}:{sum(1 for k in saida if funil_de(k['kw']) == f)}"
                                 for f in ordem)
        log(f"rodízio de funis — {distribuicao} (cota {cota})")
    return saida


# ── 3b. o X quando o SEO não dá o bastante ───────────────────────────────

def pautas_do_x(quantas: int, ja_escolhidas: list[str], noticias: str = "") -> list[dict]:
    """Completa a semana com o que está sendo discutido no X agora.

    O DataForSEO responde sobre o passado: volume é média de 12 meses, então
    assunto que estourou esta semana ainda não tem número — e é exatamente a
    pauta que a concorrência não escreveu. Quando o funil de keyword não fecha
    os 21 slots, o X preenche a diferença.

    Volume vem como 0 de propósito: fingir um número que ninguém mediu seria
    pior que admitir que esta pauta veio de outra fonte.
    """
    import requests

    chave = (os.environ.get("XAI_API_KEY") or "").strip()
    if not chave or quantas <= 0:
        return []

    evitar = "\n".join(f"- {k}" for k in ja_escolhidas[:40])
    prompt = (
        "Você acha pauta de blog vasculhando o que está sendo discutido AGORA no X "
        "e na web, em português do Brasil.\n\n"
        "NEGÓCIO: Sistema Britto vende automação com IA para dono de empresa — "
        "WhatsApp que qualifica e vende sozinho, conteúdo diário nas redes, e "
        "sistemas sob medida. O leitor é dono de negócio, não desenvolvedor nem "
        "estudante.\n\n"
        f"Proponha {quantas} pautas sobre o que está em alta nesta semana e que um "
        "dono de empresa procuraria. Cada uma precisa de um gancho real e "
        "verificável — se não achou na busca, não invente.\n\n"
        + (f"CONTEXTO DA SEMANA:\n{noticias[:2000]}\n\n" if noticias else "")
        + (f"JÁ ESCOLHIDAS (não repita assunto):\n{evitar}\n\n" if evitar else "")
        + 'Responda APENAS um JSON: {"pautas": [{"keyword": "<termo de busca que '
          'alguém digitaria>", "porque": "<o gancho, até 12 palavras>"}]}'
    )

    try:
        r = requests.post(
            XAI_URL,
            headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
            json={"model": XAI_MODEL, "input": [{"role": "user", "content": prompt}],
                  "tools": [{"type": "web_search"}, {"type": "x_search"}]},
            timeout=600)
    except Exception as exc:  # noqa: BLE001 — a semana segue com o que o SEO deu
        log(f"X indisponível para completar a pauta: {exc}")
        return []
    if r.status_code != 200:
        log(f"x.ai respondeu {r.status_code} ao buscar trending")
        return []

    texto = ""
    for item in r.json().get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    texto += c.get("text", "")

    try:
        dados = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip()))
    except (json.JSONDecodeError, ValueError):
        m = re.search(r"\{.*\}", texto, re.S)
        try:
            dados = json.loads(m.group(0)) if m else {}
        except (json.JSONDecodeError, ValueError):
            dados = {}

    achadas = []
    for p in (dados.get("pautas") or [])[:quantas]:
        termo = (p.get("keyword") or "").strip()
        if not termo or RUIDO.search(termo):
            continue
        achadas.append({"kw": termo, "vol": 0, "kd": None,
                        "origem": "x-trending", "porque": (p.get("porque") or "")[:80]})
    # Mesmo vindo de outra fonte, não pode repetir o que o blog já cobre.
    return descartar_repetidas(achadas, ja_escolhidas + titulos_publicados())


# ── 4. montar as 21 pautas ───────────────────────────────────────────────

def montar_pautas(keywords: list[dict], inicio: date) -> list[dict]:
    slots = [("09:00", "12:00"), ("13:00", "16:00"), ("18:00", "21:00")]
    pautas = []
    for i, kw in enumerate(keywords[: POSTS_POR_DIA * DIAS]):
        d = inicio + timedelta(days=i // POSTS_POR_DIA)
        brt, utc = slots[i % POSTS_POR_DIA]
        pautas.append({
            "prioridade": i + 1, "data": d.isoformat(), "slot": f"{brt} BRT",
            "publish_at": f"{d.isoformat()}T{utc}:00Z",
            "keyword": kw["kw"], "volume": kw["vol"], "kd": kw["kd"],
            "titulo": "", "status": "proposto",
        })
    return pautas


# ── 4. gate de aprovação humana ──────────────────────────────────────────

def gravar_na_fila(pautas: list[dict], dry_run: bool) -> str | None:
    """Persiste as pautas na fila — sem isto o ciclo não continua sozinho.

    O markdown serve para o humano ler; a fila serve para a rotina diária
    perguntar "o que a gente escreve hoje?". Enquanto a pauta só existia no
    arquivo, ninguém conseguia responder isso, e cada dia dependia de alguém
    reabrir o research da semana.
    """
    if dry_run:
        log("dry-run — fila não tocada.")
        return None
    try:
        from sdk_client import evo

        primeiro = date.fromisoformat(pautas[0]["data"])
        ciclo = (primeiro - timedelta(days=primeiro.weekday())).isoformat()
        # Pela API, não por sqlite direto: o container do scheduler NÃO monta
        # o volume evonexus_dashboard_data, então escrever no arquivo criaria
        # um banco fantasma na camada efêmera do container — as pautas
        # "gravadas" sumiriam no próximo redeploy e o dashboard nunca as veria.
        resultado = evo.post("/api/pautas", {"pautas": pautas})
        log(f"fila do ciclo {ciclo}: {resultado.get('gravadas')} gravadas, "
            f"{resultado.get('preservadas')} preservadas (já escritas/publicadas)")
        return ciclo
    except Exception as exc:  # noqa: BLE001 — o markdown já está salvo
        log(f"não consegui gravar na fila ({exc}); as pautas seguem no arquivo")
        return None


def abrir_aprovacao(pautas: list[dict], noticias: str, arquivo: Path, dry_run: bool,
                    ciclo: str | None = None) -> None:
    linhas = [f"{p['prioridade']:>2}. {p['data']} {p['slot']} — {p['keyword']} "
              f"(vol {p['volume']}, KD {p['kd']})" for p in pautas[:10]]
    corpo = (f"Research semanal: {len(pautas)} pautas propostas.\n\n"
             + "\n".join(linhas)
             + (f"\n\n(+{len(pautas)-10} restantes)" if len(pautas) > 10 else "")
             + f"\n\nDetalhe completo: {arquivo}")
    if ciclo:
        # A aprovação é em lote e tem um endereço concreto: quem aprovar
        # precisa saber qual ciclo liberar, senão o ticket vira só um aviso.
        corpo += (f"\n\nAprovar a semana inteira:\n"
                  f"  POST /api/pautas/ciclo/{ciclo}/aprovar\n"
                  f"Fila: GET /api/pautas?ciclo={ciclo}")
    if dry_run:
        log("dry-run — ticket não criado. Prévia:")
        print(corpo)
        return
    try:
        from sdk_client import evo

        # Um ticket por ciclo, não por execução. Rodar o research duas vezes na
        # mesma semana — o que acontece a cada ajuste de seed ou de filtro —
        # empilhava um ticket idêntico a cada vez: sete deles apareceram num
        # único dia de testes. O inbox do agente é o que dispara o heartbeat,
        # então lixo ali vira trabalho repetido de verdade.
        titulo = f"[RESEARCH] Aprovar pautas do ciclo {ciclo}" if ciclo else \
                 f"[RESEARCH] Aprovar {len(pautas)} pautas da semana"
        abertos = (evo.get("/api/tickets", {"assignee_agent": "pixel-social-media",
                                            "status": "open"}) or {})
        existente = next((t for t in (abertos.get("tickets") or abertos if isinstance(abertos, list) else [])
                          if isinstance(t, dict) and t.get("title") == titulo), None)
        if existente:
            evo.patch(f"/api/tickets/{existente['id']}", {"description": corpo})
            log(f"ticket do ciclo já existia ({existente['id']}) — atualizado em vez de duplicado")
            return

        t = evo.post("/api/tickets", {
            "title": titulo,
            "description": corpo,
            "assignee_agent": "pixel-social-media",
            "priority": "high",
        })
        log(f"ticket criado: {t.get('id')} — revisão por IA e aprovação humana antes de publicar")
    except Exception as exc:  # noqa: BLE001
        log(f"não consegui criar o ticket ({exc}); as pautas estão em {arquivo}")


def abrir_gate_no_telegram(pautas: list[dict], ciclo: str | None, dry_run: bool) -> None:
    """O card que pede a aprovação da semana — sem ele o ciclo trava calado.

    Até 03/08/2026 esta rotina gravava 21 pautas em `proposta` e terminava em
    silêncio: a única forma de liberá-las era alguém lembrar de abrir a tela
    `/pautas` e clicar. O ticket que `abrir_aprovacao` cria vai para o inbox do
    @pixel, não para o Felipe. Resultado: 01/08 e 03/08 amanheceram com a fila
    cheia, a esteira das 06:00 não achou nada `aprovada`, e nenhum artigo saiu
    — sem erro em lugar nenhum, porque não havia erro. Havia um gate que nunca
    pedia nada.

    Um card por ciclo (`idempotency_key = pauta:{ciclo}`), então rodar o
    research duas vezes na mesma semana não abre um segundo.
    """
    if not ciclo:
        log("sem ciclo — gate do Telegram não aberto (as pautas seguem na fila)")
        return
    if dry_run:
        log(f"dry-run — gate do Telegram não aberto (ciclo {ciclo})")
        return
    try:
        from escritor_de_artigo import funil_de
    except Exception:  # noqa: BLE001 — o funil é contexto, não requisito
        funil_de = None  # type: ignore[assignment]

    itens = []
    for p in pautas:
        item = {"keyword": p["keyword"], "data_alvo": p["data"], "volume": p.get("volume")}
        if funil_de:
            try:
                item["funil"] = funil_de(p["keyword"])
            except Exception:  # noqa: BLE001
                pass
        itens.append(item)

    try:
        from sdk_client import evo

        evo.post("/api/approvals", {
            "gate_type": "pauta_ciclo",
            "agent": "pixel-social-media",
            "payload": {
                "ciclo": ciclo,
                "title": f"Pautas da semana de {ciclo}",
                "body": (f"O research fechou {len(pautas)} pautas para a semana. "
                         f"Aprovar libera a fila e a esteira das 06:00 passa a escrever; "
                         f"sem isso o dia sai em branco.\n"
                         f"Para trocar alguma antes de liberar, o editor está em /pautas."),
                "pautas": itens,
            },
        })
        log(f"gate aberto no Telegram para o ciclo {ciclo}")
    except Exception as exc:  # noqa: BLE001 — a fila e o markdown já estão salvos
        log(f"não consegui abrir o gate do ciclo ({exc}); aprove em /pautas")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="não cria ticket de aprovação")
    ap.add_argument("--inicio", help="1º dia da semana a abastecer (default: amanhã)")
    args = ap.parse_args()

    load_env()
    hoje = date.today()
    inicio = date.fromisoformat(args.inicio) if args.inicio else hoje + timedelta(days=1)
    log(f"research semanal — abastecendo {inicio} + {DIAS-1} dias ({POSTS_POR_DIA}/dia)")

    noticias = pesquisar_noticias(hoje - timedelta(days=7), hoje)
    keywords = pesquisar_keywords(seeds_da_semana(hoje))
    if not keywords:
        log("sem keywords — abortando para não propor pauta sem dado.")
        return 1

    keywords = descartar_repetidas(keywords, titulos_publicados())

    # O regex separa lixo óbvio, mas não julga público: deixava passar
    # "mercado pago api" (negócio de outro) e "como postar story pelo pc"
    # (consumidor final). Quem julga isso precisa conhecer o que a Sistema
    # Britto vende e para quem — uma chamada por semana sobre ~100 candidatas.
    try:
        from avaliador_de_pauta import avaliar

        antes = len(keywords)
        keywords = avaliar(keywords)
        log(f"relevância: {antes} candidatas -> {len(keywords)} alinhadas ao ICP")
        for k in keywords[:5]:
            if "nota" in k:
                log(f"   {k['nota']:.0f}/10 {k['kw'][:44]} — {k.get('porque', '')}")
    except Exception as exc:  # noqa: BLE001 — o filtro por regex já rodou
        log(f"avaliador indisponível ({exc}); seguindo com o filtro por regex")

    # Faltou pauta? O X sabe o que está sendo discutido agora, e o que está
    # em alta hoje não tem histórico de volume no DataForSEO — é justamente a
    # pauta que a concorrência ainda não escreveu.
    alvo = POSTS_POR_DIA * DIAS

    # Equilibra a semana entre os funis ANTES de contar o que falta: sem isto o
    # WhatsApp preenche os 21 slots sozinho e o X nunca é chamado, mesmo com os
    # outros dois funis sem nenhuma pauta.
    keywords = alternar_funis(keywords, alvo)

    if len(keywords) < alvo:
        faltam = alvo - len(keywords)
        log(f"faltam {faltam} pauta(s) para fechar a semana — buscando no X")
        extras = pautas_do_x(faltam, [k["kw"] for k in keywords], noticias)
        if extras:
            keywords += extras
            log(f"X completou com {len(extras)}: "
                + ", ".join(k["kw"][:34] for k in extras[:3]))

    if len(keywords) < POSTS_POR_DIA:
        log(f"só {len(keywords)} keyword(s) inédita(s) — nem o SEO nem o X deram "
            "material suficiente. Amplie as seeds antes de rodar de novo.")
        return 1

    pautas = montar_pautas(keywords, inicio)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = OUT_DIR / f"[C]research-{hoje.isoformat()}.md"
    arquivo.write_text(
        f"# Research semanal — {hoje.isoformat()}\n\n"
        f"Abastece {inicio} a {inicio + timedelta(days=DIAS-1)} ({len(pautas)} pautas, "
        f"{POSTS_POR_DIA}/dia).\n\n## Notícias da semana (só fato com fonte)\n\n"
        f"{noticias or '_x.ai indisponível nesta execução._'}\n\n"
        f"## Pautas propostas\n\n```json\n{json.dumps(pautas, indent=2, ensure_ascii=False)}\n```\n",
        encoding="utf-8")
    log(f"gravado: {arquivo}")

    ciclo = gravar_na_fila(pautas, args.dry_run)
    abrir_aprovacao(pautas, noticias, arquivo, args.dry_run, ciclo)
    abrir_gate_no_telegram(pautas, ciclo, args.dry_run)
    log("fim — nada publicado; aguarda revisão e aprovação humana.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
