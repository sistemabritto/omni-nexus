#!/usr/bin/env python3
"""Revisão semanal do funil — acha o maior vazamento e propõe o próximo teste.

Medir não fecha ciclo nenhum. O que fecha é decidir sozinho o que testar em
seguida, e é isso que esta rotina faz: lê o funil da semana, acha a maior
queda percentual entre duas etapas, confere se aquela etapa já foi mexida
antes, e abre um ticket com a hipótese.

A decisão continua humana — o ticket é uma proposta, não uma mudança. E é
justamente o passo humano que torna isto aprendizado: uma hipótese recusada
ensina tanto quanto uma aceita, e fica registrada para a rodada seguinte não
sugerir a mesma coisa.

    domingo 09:00  (uma hora depois do research, com a semana já fechada)
      1. lê o funil dos últimos 7 dias
      2. acha a maior queda entre duas etapas consecutivas
      3. cruza com o histórico: essa etapa já foi mexida? deu no quê?
      4. abre ticket com a hipótese e o teste sugerido
      5. o humano aprova ou descarta — e a decisão vira memória

Uso:
    python ADWs/routines/weekly_funnel_review.py
    python ADWs/routines/weekly_funnel_review.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

# Onde o histórico de hipóteses vive. Fica em agent-memory porque é
# conhecimento do agente entre execuções, não estado da aplicação.
MEMORIA = REPO / ".claude" / "agent-memory" / "funil" / "hipoteses.json"

# Uma queda só vira ticket acima disso. Abaixo, é ruído de amostra pequena —
# e ticket que ninguém age ensina o operador a ignorar tickets.
QUEDA_MINIMA_PCT = 25

# E a etapa de origem precisa ter gente suficiente para a porcentagem
# significar algo. Com 2 visitas e 0 cliques a queda é "100%", e abrir ticket
# com isso é transformar amostra minúscula em conclusão.
BASE_MINIMA = 20

# O funil, na ordem. Cada par consecutivo é uma transição que pode vazar.
ETAPAS = [
    ("visitas", "chegou no site"),
    ("cliques_cta", "clicou em algum CTA"),
    ("leads", "virou lead"),
    ("leads_fechados", "fechou"),
]


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def load_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        return
    for linha in env.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def historico() -> list[dict]:
    """Hipóteses já levantadas, com o que o humano decidiu sobre cada uma."""
    if not MEMORIA.is_file():
        return []
    try:
        return json.loads(MEMORIA.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def gravar_historico(registros: list[dict]) -> None:
    MEMORIA.parent.mkdir(parents=True, exist_ok=True)
    MEMORIA.write_text(json.dumps(registros, indent=2, ensure_ascii=False),
                       encoding="utf-8")


def maior_vazamento(atual: dict) -> tuple[str, str, float] | None:
    """A transição que mais perde gente. Devolve (de, para, queda_pct).

    O critério de desempate é a perda ABSOLUTA, não a percentual. Com 191
    visitas e 1 clique a queda é 99,5%; com 15 leads e 0 fechados, é 100%. O
    percentual elegeria a segunda, mas a primeira perde 190 pessoas contra 15 —
    e é ali que mexer muda o resultado do mês.
    """
    candidatas = []
    for (chave_a, _), (chave_b, _) in zip(ETAPAS, ETAPAS[1:]):
        a = atual.get(chave_a) or 0
        b = atual.get(chave_b) or 0
        if a < BASE_MINIMA:
            continue   # amostra pequena demais para a porcentagem dizer algo
        queda = round(100 * (a - b) / a, 1)
        if queda >= QUEDA_MINIMA_PCT:
            candidatas.append((chave_a, chave_b, queda, a - b))
    if not candidatas:
        return None
    de, para, queda, _ = max(candidatas, key=lambda c: c[3])
    return de, para, queda


def sugerir(de: str, para: str, queda: float, ja_visto: list[dict]) -> dict:
    """Monta a hipótese, considerando o que já foi tentado nessa transição."""
    tentativas = [h for h in ja_visto if h.get("transicao") == f"{de}->{para}"]

    testes = {
        "visitas->cliques_cta":
            "O CTA não está sendo visto ou não promete o suficiente. Testar: "
            "subir o CTA para antes da primeira dobra, ou trocar o rótulo por "
            "um que diga o que a pessoa recebe (não o que ela faz).",
        "cliques_cta->leads":
            "A pessoa clica e desiste no formulário. Testar: reduzir campos, "
            "ou entregar algo antes de pedir o dado — foi o que resolveu o "
            "quiz, que perdia 84% na tela de e-mail.",
        "leads->leads_fechados":
            "O lead chega e não avança. Testar: velocidade da primeira "
            "resposta e qualificação na entrada — lead frio some, não fecha.",
    }
    chave = f"{de}->{para}"
    hipotese = testes.get(chave, "Investigar a transição com os dados brutos.")

    if tentativas:
        anteriores = "; ".join(
            f"{t['data'][:10]} ({t.get('decisao', 'sem decisão')})" for t in tentativas[-3:])
        hipotese += (f"\n\nJá mexemos aqui antes: {anteriores}. "
                     f"Se a queda persiste, o problema provavelmente não é o "
                     f"que já foi testado — vale olhar a etapa anterior.")

    return {
        "data": datetime.now(timezone.utc).isoformat(),
        "transicao": chave,
        "queda_pct": queda,
        "hipotese": hipotese,
        "decisao": None,   # preenchido quando o humano fecha o ticket
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="não cria ticket")
    args = ap.parse_args()

    load_env()
    from sdk_client import evo

    try:
        resumo = (evo.get("/api/metricas/resumo") or {})
    except Exception as exc:  # noqa: BLE001
        log(f"não consegui ler as métricas: {exc}")
        return 1

    atual = resumo.get("atual") or {}
    if not atual:
        log("sem métricas ainda — nada a revisar")
        return 0

    log("funil da semana: " + " · ".join(
        f"{rotulo}={atual.get(chave) or 0:g}" for chave, rotulo in ETAPAS))

    pior = maior_vazamento(atual)
    if not pior:
        log(f"nenhuma queda acima de {QUEDA_MINIMA_PCT}% — o funil está "
            "equilibrado ou a amostra ainda é pequena")
        return 0

    de, para, queda = pior
    ja = historico()
    proposta = sugerir(de, para, queda, ja)
    log(f"maior vazamento: {de} -> {para} ({queda}%)")

    if args.dry_run:
        log("dry-run — ticket não criado")
        print(proposta["hipotese"])
        return 0

    corpo = (
        f"A maior perda da semana está entre **{de}** e **{para}**: "
        f"**{queda}%** das pessoas não avançam.\n\n"
        f"## Hipótese\n\n{proposta['hipotese']}\n\n"
        f"## Funil da semana\n\n"
        + "\n".join(f"- {rotulo}: {atual.get(chave) or 0:g}" for chave, rotulo in ETAPAS)
        + "\n\n---\n\n"
        "Aprovar significa testar a hipótese; recusar também ensina — a decisão "
        "fica registrada e a próxima revisão não sugere a mesma coisa."
    )

    try:
        t = evo.post("/api/tickets", {
            "title": f"Funil: {queda:g}% de perda entre {de} e {para}",
            "description": corpo,
            "assignee_agent": "nex-sales",
            "priority": "high",
        })
        log(f"ticket criado: {t.get('id')}")
    except Exception as exc:  # noqa: BLE001
        log(f"não consegui criar o ticket ({exc}); a hipótese fica na memória")

    ja.append(proposta)
    gravar_historico(ja)
    log(f"histórico: {len(ja)} hipótese(s) registrada(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
