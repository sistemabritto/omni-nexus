"""
tests/heartbeats/test_publish_gate_reachable.py

Objetivo 7 (2026-07-25) — o impasse que travou o autopilot por dias.

Sequência observada em produção (Telegram, 24-25/07):

    Pixel prepara o post, marca new_status='review' com publish_intent=true
      -> revisor automático lê "aguardando aprovação humana para publicar"
      -> conclui FAIL, porque nada foi publicado
      -> bounce para in_progress
      -> agente refaz, mesmo resultado
      -> review_exhausted

O gate humano (_maybe_park_for_publish) só era alcançável DEPOIS de um
verdict='pass'. Como o revisor reprovava exatamente por não ter havido
publicação, e a publicação só acontece depois do gate, o ticket nunca chegava
ao Telegram. Impasse fechado: reprovado por não ter passado pelo gate que a
reprovação impedia de alcançar.

Correção: conteúdo público com publish_intent=true vai direto ao gate, sem
passar pelo revisor automático. O gate do Telegram JÁ É a revisão do conteúdo
público — um humano lê o texto exato e a data antes de qualquer coisa sair.

Run:
    pytest tests/heartbeats/test_publish_gate_reachable.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND))

import heartbeat_outcome as ho  # noqa: E402


@pytest.fixture
def espiao(monkeypatch):
    """Registra quem foi chamado: o gate humano ou o revisor automático."""
    chamadas = {"gate": 0, "revisor": 0, "bounces": 0}

    def fake_gate(ticket_id, agent, outcome, title, conn):
        chamadas["gate"] += 1
        return {"kind": "result", "agent": agent, "ticket_title": title,
                "new_status": "blocked", "summary": "Aguardando aprovação humana."}

    def fake_verdict(*a, **k):
        chamadas["revisor"] += 1
        # é exatamente isto que o revisor concluía na produção
        return {"verdict": "fail", "critique": "Ainda aguarda aprovação humana; não publicado."}

    def fake_apply_verdict(ticket_id, agent, verdict_obj, conn):
        chamadas["bounces"] += 1
        return {"verdict": "fail", "critique": "", "exhausted": False, "bounce": 1}

    monkeypatch.setattr(ho, "_maybe_park_for_publish", fake_gate)
    monkeypatch.setattr(ho, "verdict_via_nvidia", fake_verdict)
    monkeypatch.setattr(ho, "parse_verdict", lambda *a, **k: None)
    monkeypatch.setattr(ho, "_apply_review_verdict", fake_apply_verdict)
    monkeypatch.setattr(ho, "_move_ticket", lambda *a, **k: None)
    monkeypatch.setattr(ho, "_ticket_title", lambda *a, **k: "Post de teste")
    return chamadas


def _run(outcome: dict) -> dict:
    """apply_outcome espera o envelope do runner: status + output cru."""
    return {"status": "success", "output": outcome}


def _outcome(**extra):
    return {"action": "work", "ticket_id": "tkt-1", "result": "Post pronto",
            "new_status": "review", "publish_intent": True,
            "publish_target": "linkedin", "publish_content": "texto exato",
            "publish_media": [], **extra}


def test_publicacao_vai_direto_ao_gate_sem_passar_pelo_revisor(espiao):
    ho.apply_outcome("hb-1", "pixel-social-media", _run(_outcome()), conn=None)
    assert espiao["gate"] == 1, "o gate humano tem que ser alcançado"
    assert espiao["revisor"] == 0, "revisor automático não deve rodar antes do gate humano"
    assert espiao["bounces"] == 0, "nenhum bounce — era o que criava o loop"


@pytest.mark.parametrize("status", ["review", "resolved", "closed"])
def test_gate_alcancado_em_qualquer_status_terminal(espiao, status):
    ho.apply_outcome("hb-1", "pixel-social-media",
                     _run(_outcome(new_status=status)), conn=None)
    assert espiao["gate"] == 1


def test_trabalho_interno_continua_passando_pelo_revisor(espiao):
    """publish_intent=False é trabalho normal — a revisão automática continua valendo."""
    ho.apply_outcome("hb-1", "pixel-social-media",
                     _run(_outcome(publish_intent=False)), conn=None)
    assert espiao["gate"] == 0
    assert espiao["revisor"] == 1


def test_agente_nao_publicador_continua_passando_pelo_revisor(espiao):
    ho.apply_outcome("hb-1", "bolt-executor", _run(_outcome()), conn=None)
    assert espiao["gate"] == 0
    assert espiao["revisor"] == 1


def test_publish_intent_ausente_nao_pula_a_revisao(espiao):
    """Fail-closed do gate é sobre publicar; pular revisão exige True explícito."""
    o = _outcome()
    del o["publish_intent"]
    ho.apply_outcome("hb-1", "pixel-social-media", _run(o), conn=None)
    assert espiao["revisor"] == 1


# ── colunas de ticket_activity ───────────────────────────────────────────

def test_heartbeat_runner_usa_as_colunas_reais_de_ticket_activity():
    """O runner inseria em (ticket_id, event, actor, metadata) — colunas que não
    existem no modelo — e omitia id/created_at, ambos NOT NULL. No checkout a
    exceção subia e matava o run inteiro: era o 'table ticket_activity has no
    column' que derrubou o autopilot por dias."""
    import models

    reais = {c.name for c in models.TicketActivity.__table__.columns}
    assert {"id", "ticket_id", "actor", "action", "payload", "created_at"} <= reais
    assert "event" not in reais and "metadata" not in reais

    fonte = (BACKEND / "heartbeat_runner.py").read_text(encoding="utf-8")
    for trecho in fonte.split("INSERT INTO ticket_activity")[1:]:
        cabecalho = trecho.split(")")[0]
        assert "event" not in cabecalho, "coluna 'event' não existe na tabela"
        assert "metadata" not in cabecalho, "coluna 'metadata' não existe na tabela"
        for obrigatoria in ("id", "ticket_id", "actor", "action", "created_at"):
            assert obrigatoria in cabecalho, f"INSERT sem coluna NOT NULL '{obrigatoria}'"
