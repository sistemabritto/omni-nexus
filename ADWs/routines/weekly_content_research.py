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
    if not key:
        log("XAI_API_KEY ausente — etapa de notícia pulada.")
        return ""

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

    r = requests.post(
        XAI_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": XAI_MODEL, "input": [{"role": "user", "content": prompt}],
              "tools": [{"type": "web_search"}, {"type": "x_search"}]},
        timeout=900,
    )
    if r.status_code != 200:
        log(f"x.ai respondeu {r.status_code}: {r.text[:200]}")
        return ""
    data = r.json()
    txt = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    txt += c.get("text", "")
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
    r"bom dia|boa noite|boa tarde|mensagem de|frases|figurinha|papel de parede|png|emoji)", re.I)
COMPRA = re.compile(
    r"(automat|automaç|chatbot|\bbot\b|agendar|agendamento|disparo|para empresas|empresarial|"
    r"business|crm|funil|lead|prospec|tráfego|trafego|conversão|conversao|ferramenta|plataforma|"
    r"software|sistema|como (criar|fazer|automatizar|usar|integrar)|api|integra|agente de ia|"
    r"marketing digital|gestão de redes|postar)", re.I)


def pesquisar_keywords(seeds: list[str]) -> list[dict]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "research_keywords",
        "arguments": {"projectId": OPENSEO_PROJECT, "resultLimit": 150,
                      "seeds": [{"seed": s, "locationCode": 2076, "languageCode": "pt"}
                                for s in seeds[:5]]}}}
    d = _mcp(payload)
    if not d:
        return []
    linhas: dict[str, dict] = {}
    for res in d.get("result", {}).get("structuredContent", {}).get("results", []):
        for row in res.get("rows", []):
            kw = (row.get("keyword") or "").strip()
            if not kw or kw in linhas:
                continue
            linhas[kw] = {"kw": kw, "vol": row.get("searchVolume") or 0,
                          "kd": row.get("keywordDifficulty"), "cpc": row.get("cpc")}
    cand = [r for r in linhas.values()
            if 40 <= r["vol"] <= 20000 and len(r["kw"].split()) >= 3
            and COMPRA.search(r["kw"]) and not RUIDO.search(r["kw"])]
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

        t = evo.post("/api/tickets", {
            "title": f"[RESEARCH] Aprovar {len(pautas)} pautas da semana",
            "description": corpo,
            "assignee_agent": "pixel-social-media",
            "priority": "high",
        })
        log(f"ticket criado: {t.get('id')} — revisão por IA e aprovação humana antes de publicar")
    except Exception as exc:  # noqa: BLE001
        log(f"não consegui criar o ticket ({exc}); as pautas estão em {arquivo}")


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
    seeds = ["automatizar redes sociais com ia", "chatbot whatsapp para empresas",
             "agendar post instagram", "gerar leads com inteligencia artificial",
             "trafego qualificado"]
    keywords = pesquisar_keywords(seeds)
    if not keywords:
        log("sem keywords — abortando para não propor pauta sem dado.")
        return 1

    keywords = descartar_repetidas(keywords, titulos_publicados())
    if len(keywords) < POSTS_POR_DIA:
        log(f"só {len(keywords)} keyword(s) inédita(s) — o blog já cobre o resto. "
            "Amplie as seeds antes de rodar de novo.")
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
    log("fim — nada publicado; aguarda revisão e aprovação humana.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
