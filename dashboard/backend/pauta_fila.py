"""A fila de pautas — o que dá continuidade à esteira de conteúdo.

O research semanal já sabia levantar 21 pautas cruzando notícia da semana com
volume de busca. O que faltava era memória: as pautas viravam um markdown e um
ticket de texto, e no dia seguinte nada no sistema sabia responder "o que a
gente escreve hoje?". Sem essa resposta não existe rotina diária, não existe
métrica de funil, e o ciclo depende de alguém reler um arquivo.

Aqui a pauta vira estado. Cada uma nasce `proposta`, o humano aprova em lote,
a rotina diária consome as do dia e a marca `escrita` quando o rascunho existe
no Ghost, `publicada` quando o artigo vai ao ar. Descartar é explícito — pauta
que ninguém quis não fica pendurada fingindo que ainda vale.

O ciclo é semanal e recorrente de propósito: pauta escrita com 30 dias de
antecedência chega velha, e o gancho de notícia — que é o que faz a LLM citar
o artigo — tem validade de dias.
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

# proposta  → o research levantou, ninguém olhou ainda
# aprovada  → o humano liberou; a rotina diária pode escrever
# escrita   → existe rascunho no Ghost, aguardando o gate do artigo
# publicada → o artigo foi ao ar (e as redes derivaram dele)
# descartada→ o humano recusou, ou a pauta venceu sem ser usada
STATUS = ("proposta", "aprovada", "escrita", "publicada", "descartada")

# Uma pauta é do ciclo da semana. Passou dois dias do alvo sem sair, o gancho
# de notícia já morreu — insistir nela é publicar assunto velho.
DIAS_ATE_VENCER = 2

_DDL = """
CREATE TABLE IF NOT EXISTS pautas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ciclo        TEXT NOT NULL,
    prioridade   INTEGER NOT NULL,
    keyword      TEXT NOT NULL,
    titulo       TEXT,
    angulo       TEXT,
    volume       INTEGER,
    kd           REAL,
    data_alvo    TEXT NOT NULL,
    publish_at   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'proposta'
                 CHECK(status IN ('proposta','aprovada','escrita','publicada','descartada')),
    ghost_post_id TEXT,
    ghost_url     TEXT,
    motivo        TEXT,
    criado_em     TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    UNIQUE(ciclo, prioridade)
);
CREATE INDEX IF NOT EXISTS ix_pautas_status_data ON pautas(status, data_alvo);
CREATE INDEX IF NOT EXISTS ix_pautas_ciclo ON pautas(ciclo);

CREATE TABLE IF NOT EXISTS keywords_cache (
    seed          TEXT NOT NULL,
    locale        TEXT NOT NULL DEFAULT '2076/pt',
    linhas        TEXT NOT NULL,
    consultado_em TEXT NOT NULL,
    PRIMARY KEY (seed, locale)
);
"""

# Volume de busca do DataForSEO é média dos últimos 12 meses — não muda de uma
# semana para a outra. Reconsultar a mesma seed a cada rodada é dinheiro
# queimado para receber o mesmo número.
DIAS_DE_CACHE = 30


def keywords_em_cache(seeds: list[str], *, locale: str = "2076/pt",
                      conn: sqlite3.Connection | None = None) -> tuple[dict, list[str]]:
    """Devolve (linhas já conhecidas, seeds que precisam ir à API).

    O research consulta isto antes de falar com o DataForSEO. Cada seed em
    cache é uma chamada paga que não acontece.
    """
    proprio = conn is None
    conn = conn or conectar()
    try:
        limite = (datetime.now(timezone.utc) - timedelta(days=DIAS_DE_CACHE)).isoformat()
        conhecidas: dict[str, dict] = {}
        faltando: list[str] = []
        for seed in seeds:
            linha = conn.execute(
                "SELECT linhas FROM keywords_cache WHERE seed=? AND locale=? AND consultado_em > ?",
                (seed, locale, limite),
            ).fetchone()
            if not linha:
                faltando.append(seed)
                continue
            try:
                for kw in json.loads(linha["linhas"]):
                    conhecidas.setdefault(kw["kw"], kw)
            except (ValueError, TypeError, KeyError):
                faltando.append(seed)  # cache corrompido vale menos que nada
        return conhecidas, faltando
    finally:
        if proprio:
            conn.close()


def guardar_keywords(seed: str, linhas: list[dict], *, locale: str = "2076/pt",
                     conn: sqlite3.Connection | None = None) -> None:
    """Guarda o resultado de uma seed para as próximas rodadas."""
    if not linhas:
        return  # não cachear vazio: mascararia uma falha como resposta legítima
    proprio = conn is None
    conn = conn or conectar()
    try:
        conn.execute(
            "INSERT INTO keywords_cache (seed, locale, linhas, consultado_em) VALUES (?,?,?,?)"
            " ON CONFLICT(seed, locale) DO UPDATE SET"
            "  linhas=excluded.linhas, consultado_em=excluded.consultado_em",
            (seed, locale, json.dumps(linhas, ensure_ascii=False), _agora()),
        )
        conn.commit()
    finally:
        if proprio:
            conn.close()


def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    return conn


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ciclo_de(dia: date) -> str:
    """Rótulo do ciclo semanal a que um dia pertence (segunda que o abre).

    Ancorar na segunda-feira dá um identificador estável: duas execuções do
    research na mesma semana caem no mesmo ciclo e a UNIQUE(ciclo, prioridade)
    faz a segunda substituir a primeira em vez de duplicar a fila.
    """
    return (dia - timedelta(days=dia.weekday())).isoformat()


def _travas_do_ciclo(conn: sqlite3.Connection, ciclo: str) -> dict:
    """Slots e prioridades do ciclo tomados por trabalho já feito."""
    linhas = conn.execute(
        "SELECT prioridade, publish_at FROM pautas"
        " WHERE ciclo=? AND status IN ('escrita','publicada')",
        (ciclo,),
    ).fetchall()
    return {
        "ocupadas": {l["prioridade"] for l in linhas},
        "slots": {l["publish_at"] for l in linhas},
        "proxima": 1,
    }


def gravar_ciclo(pautas: list[dict], *, conn: sqlite3.Connection | None = None) -> dict:
    """Grava (ou regrava) as pautas de um ciclo.

    Quem decide se uma pauta sobrevive é o **slot** (`publish_at`), não a
    prioridade: pauta já `escrita`/`publicada` mantém seu lugar no calendário e
    o research não pode apagar trabalho que já saiu da fila. A prioridade segue
    sendo a chave de regravação — rodar o research duas vezes na mesma semana
    atualiza a fila em vez de duplicá-la.

    A preservação era por prioridade, e isso abria buraco no calendário: em
    26/07/2026 a pauta #1 já estava `escrita` no slot das 18h daquele dia, então
    a pauta nova que ocuparia a prioridade 1 — o post das 09h do dia 27 — foi
    "preservada" e simplesmente não existiu. O dia amanheceu sem post da manhã.
    Agora ela é empurrada para a próxima prioridade livre em vez de sumir.
    """
    proprio = conn is None
    conn = conn or conectar()
    gravadas = preservadas = 0
    travas: dict[str, dict] = {}
    try:
        for p in pautas:
            alvo = p.get("data") or p.get("data_alvo")
            if not alvo or not p.get("keyword"):
                continue
            ciclo = p.get("ciclo") or ciclo_de(date.fromisoformat(alvo))
            trava = travas.setdefault(ciclo, _travas_do_ciclo(conn, ciclo))
            if p["publish_at"] in trava["slots"]:
                preservadas += 1
                continue
            prioridade = p["prioridade"]
            if prioridade in trava["ocupadas"]:
                # A prioridade está tomada por trabalho já feito, mas esta pauta
                # tem slot próprio no calendário e precisa existir. Empurra para
                # a próxima livre — o deslocamento cascateia e a fila fecha sem
                # lacuna, mantendo a ordem relativa que o research definiu.
                while trava["proxima"] in trava["ocupadas"]:
                    trava["proxima"] += 1
                prioridade = trava["proxima"]
            trava["ocupadas"].add(prioridade)
            conn.execute(
                "INSERT INTO pautas (ciclo, prioridade, keyword, titulo, angulo, volume, kd,"
                " data_alvo, publish_at, status, criado_em, atualizado_em)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(ciclo, prioridade) DO UPDATE SET"
                "  keyword=excluded.keyword, titulo=excluded.titulo, angulo=excluded.angulo,"
                "  volume=excluded.volume, kd=excluded.kd, data_alvo=excluded.data_alvo,"
                "  publish_at=excluded.publish_at, atualizado_em=excluded.atualizado_em,"
                # Assunto novo no lugar de um já aprovado volta para `proposta`.
                # O UPDATE não tocava o status, então uma regravação trocava a
                # keyword e herdava a aprovação: o humano tinha liberado
                # "whatsapp business api preço" e a fila passava a carregar
                # "automação de whatsapp" como se ele tivesse visto. Aprovação é
                # sobre um assunto concreto, não sobre uma posição no calendário.
                "  status=CASE WHEN pautas.keyword <> excluded.keyword"
                "              THEN 'proposta' ELSE pautas.status END",
                (ciclo, prioridade, p["keyword"], p.get("titulo") or None,
                 p.get("angulo") or None, p.get("volume"), p.get("kd"),
                 alvo, p["publish_at"], "proposta", _agora(), _agora()),
            )
            gravadas += 1
        conn.commit()
        return {"gravadas": gravadas, "preservadas": preservadas}
    finally:
        if proprio:
            conn.close()


def do_dia(dia: date | None = None, *, status: str = "aprovada",
           conn: sqlite3.Connection | None = None) -> list[dict]:
    """Pautas de um dia, na ordem de prioridade — o que a rotina diária consome."""
    proprio = conn is None
    conn = conn or conectar()
    try:
        linhas = conn.execute(
            "SELECT * FROM pautas WHERE data_alvo=? AND status=? ORDER BY prioridade ASC",
            ((dia or date.today()).isoformat(), status),
        ).fetchall()
        return [dict(l) for l in linhas]
    finally:
        if proprio:
            conn.close()


def mover(pauta_id: int, novo_status: str, *, ghost_post_id: str | None = None,
          ghost_url: str | None = None, titulo: str | None = None,
          motivo: str | None = None, conn: sqlite3.Connection | None = None) -> bool:
    """Move uma pauta de estado, anexando o que aquele estado produziu."""
    if novo_status not in STATUS:
        raise ValueError(f"status inválido: {novo_status!r}")
    proprio = conn is None
    conn = conn or conectar()
    try:
        cur = conn.execute(
            "UPDATE pautas SET status=?, atualizado_em=?,"
            " ghost_post_id=COALESCE(?, ghost_post_id),"
            " ghost_url=COALESCE(?, ghost_url),"
            " titulo=COALESCE(?, titulo),"
            " motivo=COALESCE(?, motivo)"
            " WHERE id=?",
            (novo_status, _agora(), ghost_post_id, ghost_url, titulo, motivo, pauta_id),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        if proprio:
            conn.close()


def aprovar_ciclo(ciclo: str, *, conn: sqlite3.Connection | None = None) -> int:
    """Libera todas as pautas propostas de um ciclo de uma vez.

    Aprovação é em lote porque a decisão é em lote: o humano olha a semana
    inteira e diz sim. Aprovar 21 pautas uma a uma seria trabalho de digitação,
    não de julgamento.
    """
    proprio = conn is None
    conn = conn or conectar()
    try:
        cur = conn.execute(
            "UPDATE pautas SET status='aprovada', atualizado_em=? WHERE ciclo=? AND status='proposta'",
            (_agora(), ciclo),
        )
        conn.commit()
        return cur.rowcount
    finally:
        if proprio:
            conn.close()


def vencer_atrasadas(*, hoje: date | None = None,
                     conn: sqlite3.Connection | None = None) -> int:
    """Descarta pauta aprovada que passou da data sem virar artigo.

    Sem isto a fila acumula pauta velha e a rotina diária começa a publicar
    assunto de duas semanas atrás como se fosse notícia.
    """
    proprio = conn is None
    conn = conn or conectar()
    try:
        limite = (hoje or date.today()) - timedelta(days=DIAS_ATE_VENCER)
        cur = conn.execute(
            "UPDATE pautas SET status='descartada', motivo=?, atualizado_em=?"
            " WHERE status IN ('proposta','aprovada') AND data_alvo < ?",
            (f"venceu — passou de {DIAS_ATE_VENCER} dias da data alvo", _agora(),
             limite.isoformat()),
        )
        conn.commit()
        return cur.rowcount
    finally:
        if proprio:
            conn.close()


def resumo(*, conn: sqlite3.Connection | None = None) -> dict:
    """O funil da esteira, para o painel e para o relatório do Telegram."""
    proprio = conn is None
    conn = conn or conectar()
    try:
        por_status = {s: 0 for s in STATUS}
        for linha in conn.execute("SELECT status, COUNT(*) n FROM pautas GROUP BY status"):
            por_status[linha["status"]] = linha["n"]

        ciclo_atual = ciclo_de(date.today())
        do_ciclo = conn.execute(
            "SELECT status, COUNT(*) n FROM pautas WHERE ciclo=? GROUP BY status",
            (ciclo_atual,),
        ).fetchall()
        ciclo = {s: 0 for s in STATUS}
        for linha in do_ciclo:
            ciclo[linha["status"]] = linha["n"]

        proximas = [dict(l) for l in conn.execute(
            "SELECT id, keyword, titulo, data_alvo, publish_at, status FROM pautas"
            " WHERE status IN ('aprovada','escrita') AND data_alvo >= ?"
            " ORDER BY data_alvo ASC, prioridade ASC LIMIT 5",
            (date.today().isoformat(),),
        )]

        publicadas = por_status["publicada"]
        decididas = publicadas + por_status["descartada"]
        return {
            "por_status": por_status,
            "ciclo_atual": {"ciclo": ciclo_atual, "por_status": ciclo,
                            "total": sum(ciclo.values())},
            "proximas": proximas,
            # Taxa sobre o que já foi decidido — incluir pauta ainda na fila no
            # denominador faria a taxa cair só porque a semana começou.
            "taxa_aproveitamento": round(publicadas / decididas, 3) if decididas else None,
        }
    finally:
        if proprio:
            conn.close()


def listar(*, ciclo: str | None = None, status: str | None = None, limite: int = 100,
           conn: sqlite3.Connection | None = None) -> list[dict]:
    proprio = conn is None
    conn = conn or conectar()
    try:
        sql = "SELECT * FROM pautas WHERE 1=1"
        params: list = []
        if ciclo:
            sql += " AND ciclo=?"
            params.append(ciclo)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY data_alvo ASC, prioridade ASC LIMIT ?"
        params.append(max(1, min(limite, 500)))
        return [dict(l) for l in conn.execute(sql, params)]
    finally:
        if proprio:
            conn.close()
