"""Snapshot das métricas de crescimento — o que a esteira produziu de resultado.

O laço que faltava. A esteira sabia produzir e publicar; não sabia se aquilo
trouxe alguém. O único escritor de progresso no sistema era
`heartbeat_outcome._recompute_goal_from_tickets`, que conta TICKET RESOLVIDO —
então uma Goal de "1000 seguidores" media quantas tarefas foram fechadas, não
quantos seguidores existem. É o mesmo tipo de mentira que deixou
`pipeline-reels-vertical-pronto` marcada como cumprida com zero trabalho feito.

Por que tabela própria e não `goals.current_value`:

1. O recompute por ticket SOBRESCREVE current_value a cada mudança de status.
   Um número de audiência escrito ali seria apagado no próximo ticket
   resolvido, em silêncio.
2. Série histórica. "1000 seguidores" é um número; "de 400 para 1000 em seis
   semanas" é o que diz se a esteira funciona. current_value guarda só o
   último valor.
3. O mesmo desenho serve para clique, lead e, depois, vídeo — sem inventar
   mecanismo novo a cada métrica.

`goals.current_value` segue medindo execução (tickets). Aqui mora o resultado.
O painel mostra os dois lado a lado, que é a leitura honesta: o que foi feito
e o que aconteceu por causa disso.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"

# Uma linha por (dia, métrica, origem). A origem distingue "20 visitas" de
# "20 visitas vindas do X" — sem ela o número existe mas não ensina nada.
_DDL = """
CREATE TABLE IF NOT EXISTS metricas_crescimento (
    dia        TEXT NOT NULL,
    metrica    TEXT NOT NULL,
    origem     TEXT NOT NULL DEFAULT 'total',
    valor      REAL NOT NULL,
    goal_id    INTEGER,
    coletado_em TEXT NOT NULL,
    PRIMARY KEY (dia, metrica, origem)
);
CREATE INDEX IF NOT EXISTS ix_metricas_dia ON metricas_crescimento(dia DESC);
CREATE INDEX IF NOT EXISTS ix_metricas_goal ON metricas_crescimento(goal_id);
"""

# O que sabemos medir hoje. Nome estável: mudar quebra a série histórica, que
# é justamente o que a tabela existe para preservar.
VISITAS = "visitas"
VISITANTES = "visitantes"
CLIQUES_CTA = "cliques_cta"
LEADS = "leads"
LEADS_FECHADOS = "leads_fechados"
VISITAS_FUNIL = "visitas_funil"
# Clique em CTA atribuído ao artigo que trouxe a visita. A `origem` aqui é o
# slug da campanha — que `utm.py` monta a partir do post —, então esta é a
# única métrica que responde "qual artigo converteu", e não apenas "quantos
# cliques houve". É a pergunta que justifica publicar 21 artigos por semana.
CLIQUES_POR_ARTIGO = "cliques_por_artigo"


def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    return conn


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gravar(medicoes: list[dict], *, dia: date | None = None,
           conn: sqlite3.Connection | None = None) -> int:
    """Grava um lote de medições do dia.

    Idempotente por (dia, métrica, origem): rodar o coletor duas vezes no mesmo
    dia atualiza o valor em vez de duplicar a linha. Isso importa porque a
    rotina roda diariamente mas pode ser disparada à mão para conferir — e uma
    série histórica com pontos duplicados mente sobre a tendência.
    """
    proprio = conn is None
    conn = conn or conectar()
    quando = (dia or date.today()).isoformat()
    gravadas = 0
    try:
        for m in medicoes:
            metrica = (m.get("metrica") or "").strip()
            if not metrica or m.get("valor") is None:
                continue
            conn.execute(
                "INSERT INTO metricas_crescimento (dia, metrica, origem, valor, goal_id, coletado_em)"
                " VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(dia, metrica, origem) DO UPDATE SET"
                "  valor=excluded.valor, goal_id=COALESCE(excluded.goal_id, goal_id),"
                "  coletado_em=excluded.coletado_em",
                (quando, metrica, (m.get("origem") or "total").strip().lower(),
                 float(m["valor"]), m.get("goal_id"), _agora()),
            )
            gravadas += 1
        conn.commit()
        return gravadas
    finally:
        if proprio:
            conn.close()


def serie(metrica: str, *, origem: str | None = None, dias: int = 30,
          conn: sqlite3.Connection | None = None) -> list[dict]:
    """Evolução de uma métrica no tempo — o que responde 'está crescendo?'."""
    proprio = conn is None
    conn = conn or conectar()
    try:
        desde = (date.today() - timedelta(days=dias)).isoformat()
        sql = ("SELECT dia, origem, valor FROM metricas_crescimento"
               " WHERE metrica=? AND dia >= ?")
        params: list = [metrica, desde]
        if origem:
            sql += " AND origem=?"
            params.append(origem)
        sql += " ORDER BY dia ASC"
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        if proprio:
            conn.close()


def ultimo(metrica: str, *, origem: str = "total",
           conn: sqlite3.Connection | None = None) -> float | None:
    proprio = conn is None
    conn = conn or conectar()
    try:
        r = conn.execute(
            "SELECT valor FROM metricas_crescimento WHERE metrica=? AND origem=?"
            " ORDER BY dia DESC LIMIT 1", (metrica, origem)).fetchone()
        return r["valor"] if r else None
    finally:
        if proprio:
            conn.close()


def variacao(metrica: str, *, dias: int = 7, origem: str = "total",
             conn: sqlite3.Connection | None = None) -> dict | None:
    """Quanto mudou na janela — o número que diz se vale continuar.

    Devolve None quando não há dois pontos para comparar: uma variação
    calculada sobre um ponto só seria invenção.
    """
    proprio = conn is None
    conn = conn or conectar()
    try:
        pontos = conn.execute(
            "SELECT dia, valor FROM metricas_crescimento WHERE metrica=? AND origem=?"
            " AND dia >= ? ORDER BY dia ASC",
            (metrica, origem, (date.today() - timedelta(days=dias)).isoformat()),
        ).fetchall()
        if len(pontos) < 2:
            return None
        primeiro, ultimo_ponto = pontos[0]["valor"], pontos[-1]["valor"]
        delta = ultimo_ponto - primeiro
        return {
            "de": primeiro, "para": ultimo_ponto, "delta": delta,
            "pct": round(100 * delta / primeiro, 1) if primeiro else None,
            "dias": dias, "pontos": len(pontos),
        }
    finally:
        if proprio:
            conn.close()


def resumo(*, conn: sqlite3.Connection | None = None) -> dict:
    """O painel de crescimento: onde estamos e para onde está indo."""
    proprio = conn is None
    conn = conn or conectar()
    try:
        atual = {}
        for m in (VISITAS, VISITANTES, CLIQUES_CTA, LEADS, LEADS_FECHADOS, VISITAS_FUNIL):
            atual[m] = ultimo(m, conn=conn)

        # Origem do tráfego no dia mais recente que temos.
        ultimo_dia = conn.execute(
            "SELECT MAX(dia) d FROM metricas_crescimento WHERE metrica=?", (VISITAS,)
        ).fetchone()
        por_origem = []
        if ultimo_dia and ultimo_dia["d"]:
            por_origem = [dict(r) for r in conn.execute(
                "SELECT origem, valor FROM metricas_crescimento"
                " WHERE metrica=? AND dia=? AND origem<>'total'"
                " ORDER BY valor DESC LIMIT 8", (VISITAS, ultimo_dia["d"]))]

        # Quanto do tráfego ainda chega sem origem. É a métrica que mede se a
        # convenção de UTM está funcionando: começou em 95%.
        total = next((o["valor"] for o in por_origem if o["origem"] == "total"), None)
        direto = next((o["valor"] for o in por_origem if o["origem"] == "direct"), 0)
        soma = sum(o["valor"] for o in por_origem) or (total or 0)
        cego = round(100 * direto / soma, 1) if soma else None

        # Quais artigos converteram. Publicar 21 por semana só faz sentido se
        # der para dizer quais deles trouxeram clique — o total sozinho não
        # distingue um artigo que converte de vinte que não convertem.
        por_artigo = []
        dia_artigo = conn.execute(
            "SELECT MAX(dia) d FROM metricas_crescimento WHERE metrica=?",
            (CLIQUES_POR_ARTIGO,),
        ).fetchone()
        if dia_artigo and dia_artigo["d"]:
            por_artigo = [dict(r) for r in conn.execute(
                "SELECT origem AS artigo, valor FROM metricas_crescimento"
                " WHERE metrica=? AND dia=? AND origem<>'total'"
                " ORDER BY valor DESC LIMIT 10", (CLIQUES_POR_ARTIGO, dia_artigo["d"]))]

        # A taxa que fecha o funil: de quem chegou, quantos clicaram. É o
        # número que dizia zero enquanto nenhum botão do site registrava.
        visitas = atual.get(VISITAS) or 0
        cliques = atual.get(CLIQUES_CTA) or 0
        return {
            "atual": atual,
            "por_origem": por_origem,
            "por_artigo": por_artigo,
            "taxa_clique_pct": round(100 * cliques / visitas, 2) if visitas else None,
            "trafego_sem_origem_pct": cego,
            "variacao_7d": {m: variacao(m, dias=7, conn=conn)
                            for m in (VISITAS, CLIQUES_CTA, LEADS, VISITAS_FUNIL)},
            "ultimo_dia": ultimo_dia["d"] if ultimo_dia else None,
        }
    finally:
        if proprio:
            conn.close()
