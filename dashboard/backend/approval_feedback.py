"""Feedback de aprovação — refazer agora e aprender para a próxima.

O gate tinha dois caminhos: aprovar e rejeitar. Faltava o do meio, que é o mais
usado na prática — "está quase, muda isto". Sem ele o humano só tem duas saídas
ruins: aprovar um texto que não gostou, ou rejeitar e escrever ele mesmo.

Este módulo guarda o feedback com duas finalidades distintas:

1. **Refazer agora.** O texto volta ao agente como crítica concreta, e a
   próxima tentativa nasce corrigida.
2. **Não errar de novo.** O feedback acumulado é injetado no prompt das
   gerações seguintes. É o que faz o padrão convergir sem ninguém reescrever
   briefing: se o Felipe pediu três vezes para cortar hashtag no LinkedIn, a
   quarta geração já nasce sem.

Mora em `memory/`, que é volume — feedback perdido no redeploy seria pior que
não ter feedback, porque a pessoa acha que ensinou e não ensinou.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent

# Marca que distingue "pedi ajuste" de "rejeitei" dentro de `reject_reason`. O
# CHECK de `pending_approvals.status` não tem estado de revisão, e reconstruir a
# tabela em produção para acrescentar um custa mais do que vale: pedir ajuste é
# rejeitar esta versão e devolver com instruções, e a tentativa seguinte entra
# como attempt+1 — que a chave de idempotência já suporta.
MARCA_AJUSTE = "[ajuste] "

LEDGER = WORKSPACE / "memory" / "feedback-publicacao.jsonl"
# Quantas diretrizes entram no prompt. Vinte já é mais briefing do que o modelo
# consegue honrar de uma vez; além disso o mais antigo dilui o mais recente.
LIMITE_DIRETRIZES = int(os.environ.get("FEEDBACK_MAX_DIRETRIZES", "12"))

_ESPACOS = re.compile(r"\s+")


def _normalizar(texto: str) -> str:
    return _ESPACOS.sub(" ", (texto or "").strip())


def registrar(*, agente: str, alvo: str, feedback: str,
              titulo: str = "", aprovacao_id: int | None = None,
              autor: str = "humano") -> dict:
    """Grava o feedback no ledger e na memória do agente.

    O ledger é a fonte para injeção em prompt (formato estável, fácil de ler de
    volta). A linha em `agent-memory` existe para o protocolo de recall dos
    agentes, que lê markdown — as duas cópias servem leitores diferentes, não é
    duplicação por descuido.
    """
    feedback = _normalizar(feedback)
    if not feedback:
        return {"ok": False, "erro": "feedback vazio"}

    registro = {
        "quando": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agente": agente or "desconhecido",
        "alvo": alvo or "geral",
        "titulo": _normalizar(titulo)[:160],
        "feedback": feedback[:1000],
        "aprovacao_id": aprovacao_id,
        "autor": autor,
    }

    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except OSError as exc:
        return {"ok": False, "erro": f"não consegui gravar o ledger: {exc}"}

    _anotar_na_memoria_do_agente(registro)
    return {"ok": True, "registro": registro}


def _anotar_na_memoria_do_agente(registro: dict) -> None:
    """Melhor-esforço: falhar aqui não pode derrubar o pedido de ajuste."""
    try:
        destino = WORKSPACE / ".claude" / "agent-memory" / registro["agente"]
        destino.mkdir(parents=True, exist_ok=True)
        arquivo = destino / "learnings.md"
        dia = registro["quando"][:10]
        with arquivo.open("a", encoding="utf-8") as fh:
            fh.write(
                f"\n## {dia} — ajuste pedido em publicação ({registro['alvo']})\n"
                f"**O que aconteceu:** o texto foi para aprovação e o humano pediu ajuste"
                f"{' em ' + repr(registro['titulo']) if registro['titulo'] else ''}.\n"
                f"**Lição:** {registro['feedback']}\n"
                f"**Aplicar quando:** gerar conteúdo para {registro['alvo']}.\n"
            )
    except OSError:
        pass


def historico(alvo: str | None = None, limite: int = LIMITE_DIRETRIZES) -> list[dict]:
    """Feedbacks mais recentes, do mais novo para o mais antigo."""
    if not LEDGER.exists():
        return []
    try:
        linhas = LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    saida: list[dict] = []
    for linha in reversed(linhas):
        linha = linha.strip()
        if not linha:
            continue
        try:
            reg = json.loads(linha)
        except json.JSONDecodeError:
            continue  # linha corrompida não pode cegar o resto do histórico
        if alvo and reg.get("alvo") not in (alvo, "geral"):
            continue
        saida.append(reg)
        if len(saida) >= limite:
            break
    return saida


def diretrizes(alvo: str | None = None, limite: int = LIMITE_DIRETRIZES) -> str:
    """Bloco pronto para entrar no prompt, ou string vazia se não há histórico.

    Ordem cronológica (mais antigo primeiro) de propósito: o modelo tende a dar
    mais peso ao final do bloco, e é o feedback mais recente que deve pesar
    mais. Feedback repetido é deduplicado — três vezes a mesma frase não a torna
    mais verdadeira, só ocupa contexto.
    """
    itens = historico(alvo, limite)
    if not itens:
        return ""
    vistos: set[str] = set()
    linhas: list[str] = []
    for reg in reversed(itens):
        chave = reg["feedback"].lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append(f"- {reg['feedback']}")
    if not linhas:
        return ""
    return ("Correções que o humano já pediu em publicações anteriores — "
            "respeite todas, são regra e não sugestão:\n" + "\n".join(linhas))
