"""
tests/heartbeats/test_formato_de_timestamp.py

2026-07-27 — o re-nudge de aprovação nunca disparou.

`heartbeat_outcome._now_iso` usava `isoformat()`, que produz `+00:00`. As
outras quatro funções `_now` do backend usam `strftime("...%fZ")`. Duas linhas
adjacentes do mesmo INSERT em `pending_approvals` gravavam formatos diferentes:
`created_at` com `+00:00`, `expires_at` com `Z`.

`ticket_janitor._parse_iso` faz `strptime(ts.rstrip("Z"), ...)`, que levanta
`ValueError: unconverted data remains: +00:00`. O erro caía num `continue`, e
os nudges de 2h e 4h nunca aconteceram para nenhuma aprovação criada por
heartbeat — o caminho real. A expiração de 8h funcionava por acidente, porque
lia o campo que estava no outro formato.

Run:
    pytest tests/heartbeats/test_formato_de_timestamp.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import ticket_janitor  # noqa: E402


def _todas_as_fabricas():
    """As funções que carimbam timestamp em coluna de banco."""
    import heartbeat_outcome
    import routes.approvals as approvals
    import routes.goals as goals
    import routes.tickets as tickets

    return {
        "heartbeat_outcome._now_iso": heartbeat_outcome._now_iso,
        "ticket_janitor._now": ticket_janitor._now,
        "routes.goals._now": goals._now,
        "routes.tickets._now": tickets._now,
        "routes.approvals._now": approvals._now,
    }


@pytest.mark.parametrize("nome", list(_todas_as_fabricas()))
def test_todo_timestamp_gravado_e_legivel_pelo_janitor(nome):
    """O parser do janitor é quem consome — ele define o formato válido."""
    valor = _todas_as_fabricas()[nome]()
    ticket_janitor._parse_iso(valor)  # levanta ValueError se divergir


@pytest.mark.parametrize("nome", list(_todas_as_fabricas()))
def test_nenhuma_fabrica_produz_offset_explicito(nome):
    valor = _todas_as_fabricas()[nome]()
    assert not valor.endswith("+00:00"), f"{nome} voltou ao isoformat()"
    assert valor.endswith("Z")


def test_o_parser_continua_recusando_o_formato_errado():
    """Guarda a decisão: o parser NÃO foi afrouxado.

    Tolerar os dois formatos trataria o sintoma e deixaria o banco com duas
    convenções convivendo — o próximo campo novo escolheria uma das duas ao
    acaso e o problema voltaria em outro lugar.
    """
    with pytest.raises(ValueError):
        ticket_janitor._parse_iso("2026-07-27T10:35:18.632802+00:00")


def test_created_at_e_expires_at_da_mesma_aprovacao_batem():
    """Era o par exato que divergia, gravado por linhas adjacentes."""
    from datetime import datetime, timedelta, timezone

    import heartbeat_outcome as ho

    criado = ho._now_iso()
    expira = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert ticket_janitor._parse_iso(expira) > ticket_janitor._parse_iso(criado)
