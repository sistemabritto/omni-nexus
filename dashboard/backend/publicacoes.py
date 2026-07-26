"""Registro das publicações agendadas e a confirmação do link quando saem.

Um post aprovado quase nunca vai ao ar na hora: o gate agenda para a próxima
janela da rede, e nesse instante a plataforma ainda não tem endereço nenhum
para devolver — `releaseURL` vem `null` enquanto o post está na fila. O
resultado prático era que o Felipe aprovava, recebia "agendado", e nunca mais
ouvia falar daquilo: se saísse sem imagem, sem link, ou não saísse, ninguém
descobria. Foi assim que três posts ficaram semanas sem imagem.

Este módulo fecha o laço em duas metades:

- `registrar()` guarda os ids do Postiz no momento da aprovação — sem isso não
  há como reencontrar o post depois, porque o id só existe na resposta daquela
  chamada;
- `tick()` roda como heartbeat in-process (`handler: publicacoes.tick`, zero
  Claude) e, quando o agendado vira PUBLISHED, manda o endereço no Telegram.

Fail-closed pelo mesmo princípio do resto do gate: nada aqui afirma que
publicou. Quem afirma é o Postiz, relendo o post pelo id.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"

# Depois disto, para de perguntar. Um agendamento que não virou publicação em
# um dia inteiro não vai virar sozinho — vira aviso e sai da varredura, em vez
# de consultar o Postiz para sempre a cada tick.
HORAS_ATE_DESISTIR = 24

_DDL = """
CREATE TABLE IF NOT EXISTS publicacoes (
    approval_id   INTEGER PRIMARY KEY,
    ticket_id     TEXT,
    rede          TEXT NOT NULL,
    titulo        TEXT,
    post_ids      TEXT NOT NULL,
    agendado_para TEXT,
    imagens       INTEGER NOT NULL DEFAULT 0,
    comentarios   INTEGER NOT NULL DEFAULT 0,
    release_urls  TEXT,
    confirmado_em TEXT,
    criado_em     TEXT NOT NULL
)
"""


def _conectar() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    return conn


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def registrar(approval_id: int, *, ticket_id: str | None, rede: str, titulo: str,
              post_ids: list[str], agendado_para: str = "", imagens: int = 0,
              comentarios: int = 0, release_urls: list[str] | None = None) -> bool:
    """Guarda os ids do Postiz para reencontrar o post quando ele publicar.

    Só registra agendamento ainda sem endereço — post que já saiu com link foi
    confirmado na hora e não precisa de varredura. Best-effort: falhar aqui não
    pode desfazer uma publicação que já aconteceu.
    """
    if not post_ids or release_urls:
        return False
    conn = _conectar()
    if conn is None:
        return False
    try:
        conn.execute(
            "INSERT OR REPLACE INTO publicacoes "
            "(approval_id, ticket_id, rede, titulo, post_ids, agendado_para, "
            " imagens, comentarios, release_urls, confirmado_em, criado_em) "
            "VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?)",
            (approval_id, ticket_id, rede, titulo[:300], json.dumps(post_ids),
             agendado_para or None, imagens, comentarios, _agora()),
        )
        conn.commit()
        return True
    except sqlite3.Error:
        log.exception("falha ao registrar publicação agendada %s", approval_id)
        return False
    finally:
        conn.close()


def _janela(linha: sqlite3.Row) -> tuple[str, str]:
    """Janela de consulta em torno do horário agendado, com folga de um dia."""
    base = datetime.now(timezone.utc)
    if linha["agendado_para"]:
        try:
            base = datetime.fromisoformat(linha["agendado_para"].replace("Z", "+00:00"))
        except ValueError:
            pass
    return ((base - timedelta(days=1)).isoformat(), (base + timedelta(days=1)).isoformat())


def _velho_demais(linha: sqlite3.Row) -> bool:
    referencia = linha["agendado_para"] or linha["criado_em"]
    try:
        quando = datetime.fromisoformat((referencia or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - quando > timedelta(hours=HORAS_ATE_DESISTIR)


def _fechar(conn: sqlite3.Connection, approval_id: int, urls: list[str]) -> None:
    conn.execute(
        "UPDATE publicacoes SET release_urls=?, confirmado_em=? WHERE approval_id=?",
        (json.dumps(urls), _agora(), approval_id),
    )
    conn.commit()


def tick() -> dict:
    """Confirma agendamentos que já publicaram e avisa com o endereço do post.

    Handler de heartbeat in-process: puro SQL + Postiz + Telegram, sem invocar
    Claude. Idempotente — cada linha é fechada assim que vira notificação, e
    linha fechada nunca é reconsultada.
    """
    conn = _conectar()
    if conn is None:
        return {"erro": "banco não encontrado", "confirmados": 0, "pendentes": 0}

    try:
        from notifications import notify_publicacao
        from postiz_client import PostizClient, PostizError

        pendentes = conn.execute(
            "SELECT * FROM publicacoes WHERE confirmado_em IS NULL ORDER BY criado_em ASC LIMIT 40"
        ).fetchall()
        if not pendentes:
            return {"confirmados": 0, "pendentes": 0, "desistidos": 0}

        client = PostizClient.from_env()
        if client is None:
            return {"erro": "Postiz não configurado", "confirmados": 0,
                    "pendentes": len(pendentes)}

        confirmados = desistidos = 0
        for linha in pendentes:
            try:
                ids = json.loads(linha["post_ids"])
            except (ValueError, TypeError):
                _fechar(conn, linha["approval_id"], [])
                continue

            try:
                posts = client.list_posts(_janela(linha))
            except PostizError as exc:
                log.warning("Postiz indisponível ao confirmar %s: %s", linha["approval_id"], exc)
                continue  # tenta de novo no próximo tick; nada é afirmado

            estados = {
                item.get("id"): (item.get("state") or "").upper()
                for item in posts if item.get("id") in ids
            }
            com_erro = [i for i in ids if estados.get(i) == "ERROR"]
            # Todos, não algum: um post cujo comentário ainda não saiu está
            # meio publicado, e avisar "está no ar" nesse momento manda o
            # Felipe conferir um post que ainda vai mudar.
            todos_no_ar = bool(ids) and all(estados.get(i) == "PUBLISHED" for i in ids)

            if todos_no_ar and not com_erro:
                urls = client.release_urls_de(posts, ids)
                notify_publicacao(
                    linha["rede"], linha["titulo"] or "", links=urls,
                    imagens=linha["imagens"], comentarios=linha["comentarios"],
                )
                _fechar(conn, linha["approval_id"], urls)
                confirmados += 1
                continue

            if com_erro:
                notify_publicacao(
                    linha["rede"], f"❌ falhou: {linha['titulo'] or ''}", links=[],
                    imagens=linha["imagens"], comentarios=linha["comentarios"],
                )
                _fechar(conn, linha["approval_id"], [])
                desistidos += 1
                continue

            if _velho_demais(linha):
                # Nem publicou nem falhou em 24h — o silêncio é o problema, e
                # ficar consultando não o resolve. Avisa uma vez e encerra.
                notify_publicacao(
                    linha["rede"],
                    f"⏳ segue na fila do Postiz sem publicar: {linha['titulo'] or ''}",
                    links=[], imagens=linha["imagens"], comentarios=linha["comentarios"],
                )
                _fechar(conn, linha["approval_id"], [])
                desistidos += 1

        restantes = conn.execute(
            "SELECT COUNT(*) FROM publicacoes WHERE confirmado_em IS NULL"
        ).fetchone()[0]
        log.info("publicacoes.tick: confirmados=%d desistidos=%d pendentes=%d",
                 confirmados, desistidos, restantes)
        return {"confirmados": confirmados, "desistidos": desistidos, "pendentes": restantes}
    finally:
        conn.close()
