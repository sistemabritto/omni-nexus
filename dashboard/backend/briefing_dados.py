"""Dossiê do dia — tudo que o briefing precisa e que não exige julgamento.

O briefing matinal custava US$ 0,16 por execução e acertava 76% das vezes. O
motivo dos dois números é o mesmo: `prod-good-morning` é uma skill escrita para
conversa, não para cron. Ela manda o agente ler CLAUDE.md, os três últimos
logs, o overview de cada projeto ativo, consultar três integrações, montar um
HTML e **perguntar ao usuário se ele quer entrar num projeto** — pergunta que
às 07:00 ninguém responde. São dezenas de turnos de navegação para produzir uma
lista que, na maior parte, já existe pronta em banco e em API.

Este módulo coleta a parte determinística uma vez, em Python, e entrega pronta.
O que sobra para o modelo é o que só ele faz: ler o conjunto e dizer no que
prestar atenção hoje.

**Fronteira honesta:** Gmail e Agenda continuam fora daqui. O acesso a eles é
via MCP, com o OAuth do Claude Code; em Python não há credencial, e inventar
uma seção vazia de "e-mails" seria pior que admitir que a coleta não é nossa.
Quem junta as duas metades é a skill.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo")


def _agora_brt() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(os.environ.get("WORKSPACE_TIMEZONE")
                                     or "America/Sao_Paulo"))
    except Exception:  # noqa: BLE001 — sem tzdata, UTC-3 resolve o suficiente
        return datetime.now(timezone.utc) - timedelta(hours=3)


# ── Todoist ──────────────────────────────────────────────────────────────

def tarefas_de_hoje() -> list[dict]:
    """Tarefas vencidas ou para hoje. Lista vazia se não houver token.

    O filtro `today | overdue` é da própria API — pedir tudo e filtrar aqui
    traria as de daqui a três meses só para descartá-las.
    """
    token = (os.environ.get("TODOIST_API_TOKEN") or "").strip()
    if not token:
        return []
    try:
        import requests

        r = requests.get("https://api.todoist.com/rest/v2/tasks",
                         params={"filter": "today | overdue"},
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if r.status_code >= 300:
            return []
        return [{"titulo": t.get("content", ""),
                 "prioridade": t.get("priority", 1),
                 "vencida": bool((t.get("due") or {}).get("date", "")
                                 < _agora_brt().date().isoformat()),
                 "url": t.get("url", "")}
                for t in r.json()]
    except Exception:  # noqa: BLE001 — integração fora do ar não derruba o briefing
        return []


# ── Nexus (via API, nunca SQLite direto) ─────────────────────────────────

def _evo():
    from sdk_client import evo

    return evo


def gates_pendentes() -> list[dict]:
    """Aprovações esperando decisão. É o que trava a esteira.

    Primeiro item do briefing por um motivo: enquanto um gate não é decidido,
    o artigo não publica e os posts não saem. Nenhuma outra pendência do dia
    tem um relógio correndo desse jeito.
    """
    try:
        r = _evo().get("/api/approvals", {"status": "pending"}) or {}
    except Exception:  # noqa: BLE001
        return []
    saida = []
    for a in (r.get("approvals") or []):
        pub = a.get("publish") or {}
        saida.append({"titulo": a.get("title") or "", "alvo": pub.get("target") or "",
                      "criado": a.get("created_at") or ""})
    return saida


def tickets_abertos(limite: int = 6) -> list[dict]:
    try:
        r = _evo().get("/api/tickets", {"status": "open"}) or {}
    except Exception:  # noqa: BLE001
        return []
    itens = r.get("tickets") if isinstance(r, dict) else r
    ordem = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    itens = sorted(itens or [], key=lambda t: ordem.get(t.get("priority"), 9))
    return [{"titulo": t.get("title", ""), "prioridade": t.get("priority", ""),
             "responsavel": t.get("assignee_agent", "")} for t in itens[:limite]]


def rotinas_que_falharam(horas: int = 24) -> list[dict]:
    """Rotina que falhou desde ontem. Silêncio aqui é o normal.

    A esteira AI News passou três dias falhando às 19:00 sem ninguém notar. O
    briefing é onde esse tipo de coisa tem de aparecer — de manhã, uma vez, e
    só quando existe.
    """
    try:
        r = _evo().get("/api/routines") or {}
    except Exception:  # noqa: BLE001
        return []
    corte = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    falhas = []
    for nome, m in (r.get("metrics") or {}).items():
        if not isinstance(m, dict) or m.get("last_success") is not False:
            continue
        ultima = (m.get("last_run") or "").replace("Z", "+00:00")
        if ultima and ultima < corte:
            continue
        falhas.append({"rotina": m.get("name") or nome, "quando": m.get("last_run") or ""})
    return falhas


def pauta_do_dia() -> list[dict]:
    """O que a esteira tem para escrever hoje.

    `/api/pautas/hoje`, e não `/api/pautas`: o segundo ignora o parâmetro de
    dia e devolve a fila inteira. Listar as 24 pautas da semana num briefing
    matinal esconde as três de hoje no meio do resto.
    """
    saida = []
    # Três estados, porque às 07:00 a esteira das 06:00 já rodou: o que ela
    # escreveu está em `escrita` esperando o gate, o que ainda não virou artigo
    # segue em `aprovada`, e o que ninguém liberou está em `proposta`. Pedir só
    # o padrão da API mostraria a fatia que já não exige nada de ninguém.
    #
    # `proposta` entrou em 03/08/2026: sem ela o briefing dizia "pauta de hoje:
    # nada" com 11 pautas paradas esperando aprovação, que é exatamente o
    # estado em que o dia sai em branco. O único lugar que podia avisar estava
    # olhando para o lado errado.
    for status in ("escrita", "aprovada", "proposta"):
        try:
            r = _evo().get("/api/pautas/hoje", {"status": status}) or {}
        except Exception:  # noqa: BLE001
            continue
        itens = r.get("pautas") if isinstance(r, dict) else r
        saida.extend({"keyword": p.get("keyword", ""), "status": status,
                      "funil": p.get("funil") or p.get("funnel") or ""}
                     for p in (itens or []))
    return saida


# ── o dossiê ─────────────────────────────────────────────────────────────

def coletar() -> dict:
    agora = _agora_brt()
    return {
        "data": agora.strftime("%d/%m/%Y"),
        "dia_semana": DIAS[agora.weekday()],
        "hora": agora.strftime("%H:%M"),
        "gates_pendentes": gates_pendentes(),
        "tarefas": tarefas_de_hoje(),
        "tickets": tickets_abertos(),
        "rotinas_falhando": rotinas_que_falharam(),
        "pauta_do_dia": pauta_do_dia(),
    }


def em_markdown(dossie: dict | None = None) -> str:
    """O dossiê como texto, para entrar direto no prompt da skill.

    Markdown e não JSON porque o destino é um prompt: chaves e aspas gastam
    token e não acrescentam nada que a leitura precise.
    """
    d = dossie or coletar()
    linhas = [f"# Dossiê de {d['dia_semana']}, {d['data']} ({d['hora']})", ""]

    def secao(titulo: str, itens: list, formatar) -> None:
        linhas.append(f"## {titulo}")
        if not itens:
            linhas.append("_nada_")
        else:
            linhas.extend(f"- {formatar(i)}" for i in itens)
        linhas.append("")

    secao("Aprovações esperando decisão", d["gates_pendentes"],
          lambda g: f"{g['titulo']}" + (f" ({g['alvo']})" if g["alvo"] else ""))
    secao("Rotinas que falharam nas últimas 24h", d["rotinas_falhando"],
          lambda f: f"{f['rotina']} — {f['quando'][:16]}")
    secao("Tarefas de hoje (Todoist)", d["tarefas"],
          lambda t: ("⚠ ATRASADA " if t["vencida"] else "") + t["titulo"])
    secao("Tickets abertos", d["tickets"],
          lambda t: f"[{t['prioridade']}] {t['titulo']}"
                    + (f" — @{t['responsavel']}" if t["responsavel"] else ""))
    secao("Pauta da esteira para hoje", d["pauta_do_dia"],
          lambda p: f"{p['keyword']} ({p['status']}, funil {p['funil']})")

    return "\n".join(linhas)


# ── fim do dia ───────────────────────────────────────────────────────────

def _workspace():
    from pathlib import Path

    return Path(os.environ.get("WORKSPACE_DIR") or
                Path(__file__).resolve().parents[2])


def _git(*args: str) -> str:
    """Saída do git, ou vazio. Nunca levanta.

    O fim do dia não pode falhar porque o repositório está num estado que o
    git não gostou — o resto da consolidação continua valendo.
    """
    import subprocess

    try:
        r = subprocess.run(["git", *args], cwd=str(_workspace()), text=True,
                           capture_output=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def trabalho_do_dia() -> dict:
    """O que mudou no repositório hoje, quando há repositório de verdade.

    Só reporta se o git tiver um remote. Dentro do container o `/workspace` é
    um volume com um repositório próprio, criado no build da imagem, cujo
    único commit se chama "baseline (image build)" — listar aquilo como
    "commits de hoje" seria informar uma coisa que não aconteceu. Sem remote,
    a seção não existe, e o dossiê não perde nada: as rotinas do dia e os
    arquivos escritos já contam o que houve.
    """
    if not _git("remote"):
        return {"commits": [], "alterado": [], "sem_repo": True}
    desde = _agora_brt().strftime("%Y-%m-%d 00:00")
    return {
        "commits": [l for l in _git("log", "--oneline", f"--since={desde}").splitlines() if l],
        "alterado": _git("diff", "--stat").splitlines()[-1:] or [],
        "sem_repo": False,
    }


def rotinas_do_dia() -> list[dict]:
    """Rotinas que rodaram hoje, com o desfecho de cada uma."""
    import json

    log = _workspace() / "ADWs" / "logs" / f"{_agora_brt().date().isoformat()}.jsonl"
    if not log.is_file():
        return []
    saida = []
    for linha in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(linha)
        except ValueError:
            continue
        # O campo é `run`. `log_name` é como o runner chama o parâmetro na
        # assinatura, não como ele grava no JSONL — e a diferença fazia o
        # dossiê listar seis rotinas chamadas "?".
        saida.append({"rotina": e.get("run") or "?",
                      "ok": e.get("returncode", e.get("return_code", 1)) == 0,
                      "segundos": e.get("duration") or e.get("duration_seconds")})
    return saida


def arquivos_tocados_hoje(limite: int = 12) -> list[str]:
    """Memória de agente e reunião escritas hoje — onde mora o aprendizado.

    Devolve caminho, não conteúdo: quem decide o que importa ali é quem lê, e
    despejar arquivo inteiro no prompt é justamente o gasto que se quer evitar.
    """
    from pathlib import Path

    base = _workspace()
    hoje = _agora_brt().date()
    achados = []
    for pasta in (".claude/agent-memory", "workspace/meetings", "memory"):
        raiz = base / pasta
        if not raiz.is_dir():
            continue
        for f in raiz.rglob("*.md"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime).date() == hoje:
                    achados.append(str(f.relative_to(base)))
            except OSError:
                continue
    return sorted(achados)[:limite]


def coletar_fim_do_dia() -> dict:
    agora = _agora_brt()
    return {
        "data": agora.strftime("%d/%m/%Y"),
        "dia_semana": DIAS[agora.weekday()],
        "trabalho": trabalho_do_dia(),
        "rotinas": rotinas_do_dia(),
        "arquivos_tocados": arquivos_tocados_hoje(),
        "tarefas_abertas": tarefas_de_hoje(),
        "gates_pendentes": gates_pendentes(),
        "tickets": tickets_abertos(),
    }


def fim_do_dia_em_markdown(dossie: dict | None = None) -> str:
    d = dossie or coletar_fim_do_dia()
    linhas = [f"# Dossiê do fim de {d['dia_semana']}, {d['data']}", ""]

    def secao(titulo: str, itens: list, formatar=str) -> None:
        linhas.append(f"## {titulo}")
        linhas.extend([f"- {formatar(i)}" for i in itens] if itens else ["_nada_"])
        linhas.append("")

    if not d["trabalho"].get("sem_repo"):
        secao("Commits de hoje", d["trabalho"]["commits"])
        secao("Working tree", d["trabalho"]["alterado"])
    falhas = [r for r in d["rotinas"] if not r["ok"]]
    secao(f"Rotinas que rodaram ({len(d['rotinas'])}, {len(falhas)} falharam)",
          d["rotinas"],
          lambda r: f"{'✓' if r['ok'] else '✗'} {r['rotina']}")
    secao("Arquivos de memória/reunião escritos hoje", d["arquivos_tocados"])
    secao("Tarefas ainda abertas", d["tarefas_abertas"],
          lambda t: ("⚠ ATRASADA " if t["vencida"] else "") + t["titulo"])
    secao("Aprovações ainda pendentes", d["gates_pendentes"], lambda g: g["titulo"])
    secao("Tickets abertos", d["tickets"],
          lambda t: f"[{t['prioridade']}] {t['titulo']}")

    return "\n".join(linhas)


if __name__ == "__main__":  # `python briefing_dados.py [--eod]` confere a coleta
    import sys as _sys

    print(fim_do_dia_em_markdown() if "--eod" in _sys.argv else em_markdown())
