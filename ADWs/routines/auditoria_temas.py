#!/usr/bin/env python3
"""Auditoria de temas — acessos por post para orientar a próxima esteira.

Responde três perguntas que a esteira precisava fazer em voz alta:

  1. Quais artigos trouxeram clique?  (`cliques_por_artigo` por slug)
  2. Qual funil está trazendo gente?   (`visitas_funil` por funil)
  3. A fila do próximo ciclo está saturada de um nicho? (% de pautas por funil)

O dado nasce no analytics do site (`daily_growth_metrics` grava todo dia na
série `metricas_crescimento`); aqui a gente apenas cruza com a fila de pautas
e transforma em recomendação concreta para o `weekly_content_research`.

O Ghost não tem stats habilitado (endpoints /stats/* respondem 404 no plano
atual), então "acessos por post" = cliques de CTA atribuídos ao slug do artigo
(UTM) + visitas de funil. Quando o Ghost habilitar analytics, o módulo cresce
por aqui sem mudar a saída.

Uso:
    python ADWs/routines/auditoria_temas.py                # janela 30d, imprime + grava JSON
    python ADWs/routines/auditoria_temas.py --dias 90
    python ADWs/routines/auditoria_temas.py --saida /tmp/x.json

A saída JSON é o contrato que o `weekly_content_research` pode consumir:
`{"funis": {<funil>: {"peso": 0..1, "saturado": bool}}}`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_AQUI = Path(__file__).resolve()
# Roda tanto de ADWs/routines/ (repo) quanto de /tmp (sondagem no container).
REPO = _AQUI.parents[2] if _AQUI.parent.name == "routines" and _AQUI.parent.parent.name == "ADWs" else Path("/workspace")
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

OUT_PADRAO = REPO / "workspace" / "social" / "auditoria_temas.json"

# Acima disto um funil é considerado saturado na fila do próximo ciclo.
LIMIAR_SATURACAO = 0.5


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def load_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        env = REPO / "config" / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def funil_de(keyword: str) -> str:
    """Slug do funil de uma pauta (reusa a classificação da esteira)."""
    from escritor_de_artigo import funil_de as _funil_de
    return _funil_de(keyword)


def coletar_serie(metrica: str, dias: int) -> list[dict]:
    """Série de uma métrica via API (o scheduler não monta o volume do banco)."""
    from sdk_client import evo
    resposta = evo.get("/api/metricas/serie", {"metrica": metrica, "dias": dias}) or {}
    return resposta.get("pontos") or []


def coletar_pautas() -> list[dict]:
    """Fila de pautas do dashboard (ciclo atual + próximos)."""
    from sdk_client import evo
    resposta = evo.get("/api/pautas", {"limit": 200}) or {}
    return resposta.get("pautas") or []


def _acumular(pontos: list[dict]) -> dict[str, float]:
    """Agrega uma série {dia, origem, valor} por origem."""
    total: dict[str, float] = defaultdict(float)
    for p in pontos:
        total[p.get("origem") or "total"] += float(p.get("valor") or 0)
    return dict(total)


def auditar(*, dias: int) -> dict:
    """Monta o relatório de auditoria de temas."""
    pautas = coletar_pautas()

    # Distribuição de funis na fila (o que está agendado/vindo).
    por_funil_fila: dict[str, int] = defaultdict(int)
    for p in pautas:
        por_funil_fila[funil_de(p.get("keyword") or "")] += 1
    total_fila = sum(por_funil_fila.values()) or 0

    # Acessos: cliques de CTA por artigo (slug = utm_campaign) e visitas por funil.
    cliques_artigo = _acumular(coletar_serie("cliques_por_artigo", dias))
    visitas_funil = _acumular(coletar_serie("visitas_funil", dias))

    # Ranking de artigos por clique.
    acessos_por_artigo = sorted(
        ({"artigo": a, "cliques": int(c)} for a, c in cliques_artigo.items()
         if a != "total"),
        key=lambda x: x["cliques"], reverse=True,
    )[:15]

    # Desempenho por funil: visitas + quantas pautas estão na fila.
    desempenho = {}
    for funil in ("whatsapp", "socialjobs", "sistema"):
        visitas = int(visitas_funil.get(funil, 0))
        fila = por_funil_fila.get(funil, 0)
        pct = round(100 * fila / total_fila, 1) if total_fila else 0
        desempenho[funil] = {
            "visitas_funil": visitas,
            "pautas_fila": fila,
            "pct_fila": pct,
            "saturado": pct / 100 >= LIMIAR_SATURACAO,
        }

    # Recomendação para a próxima esteira.
    saturados = [f for f, d in desempenho.items() if d["saturado"]]
    recomendacao = []
    if saturados:
        recomendacao.append(
            f"Funil(ais) saturado(s) na fila: {', '.join(saturados)} "
            f"(>={LIMIAR_SATURACAO:.0%}). Reduzir a cota destes no rodízio "
            "semanal — o alternar_funis já impõe teto por funil."
        )
    for funil in ("whatsapp", "socialjobs", "sistema"):
        d = desempenho[funil]
        if d["pautas_fila"] == 0:
            recomendacao.append(
                f"Funil '{funil}' sem pauta na fila: revisar seeds em "
                "weekly_content_research.SEEDS_POR_FUNIL antes do próximo ciclo."
            )
        elif d["visitas_funil"] == 0 and d["pct_fila"] > 0:
            recomendacao.append(
                f"Funil '{funil}' tem {d['pautas_fila']} pauta(s) mas 0 visitas "
                "medidas: conferir se os artigos já publicados chegam ao site "
                "(UTM presente? analytics coletando?)."
            )
    if not recomendacao:
        recomendacao.append("Distribuição saudável: manter a cota por funil.")

    # Contrato consumível pelo research: peso = sobra da cota igualitária.
    cota = math.ceil(100 / 3)  # 3 funis
    pesos = {}
    for funil, d in desempenho.items():
        pct = d["pct_fila"]
        pesos[funil] = {
            "peso": max(0.0, round(1 - (pct / cota), 2)) if pct else 1.0,
            "saturado": d["saturado"],
        }

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "janela_dias": dias,
        "acessos_por_artigo": acessos_por_artigo,
        "desempenho_funil": desempenho,
        "saturados": saturados,
        "recomendacao": recomendacao,
        "funis": pesos,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dias", type=int, default=30, help="janela da série (default: 30)")
    ap.add_argument("--saida", default=str(OUT_PADRAO), help="caminho do JSON de saída")
    ap.add_argument("--dry-run", action="store_true", help="imprime sem gravar arquivo")
    args = ap.parse_args()

    load_env()
    relatorio = auditar(dias=args.dias)

    print(json.dumps({
        "janela_dias": relatorio["janela_dias"],
        "saturados": relatorio["saturados"],
        "desempenho_funil": relatorio["desempenho_funil"],
        "recomendacao": relatorio["recomendacao"],
        "top_artigos": relatorio["acessos_por_artigo"][:5],
    }, indent=2, ensure_ascii=False))
    print(f"→ {len(relatorio['acessos_por_artigo'])} artigo(s) com clique medido.")

    if args.dry_run:
        return 0

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    log(f"gravado: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
