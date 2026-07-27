"""
tests/goals/test_revisao_do_funil.py

2026-07-27 — Sprint 7: o funil que aponta o próprio gargalo.

Medir não fecha ciclo. O que fecha é decidir sozinho o que testar em seguida.
Esta rotina lê o funil da semana, acha o maior vazamento e abre um ticket com
a hipótese — e a decisão humana sobre esse ticket vira memória, para a revisão
seguinte não sugerir a mesma coisa.

Os dois testes que mais importam aqui são sobre o que a rotina NÃO faz: não
abrir ticket com amostra minúscula, e não eleger a transição errada.

Run:
    pytest tests/goals/test_revisao_do_funil.py -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

_spec = importlib.util.spec_from_file_location(
    "weekly_funnel_review", REPO_ROOT / "ADWs" / "routines" / "weekly_funnel_review.py")
rev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rev)


# ── o que NÃO vira ticket ────────────────────────────────────────────────

def test_amostra_minuscula_nao_vira_ticket():
    """Com 2 visitas e 0 cliques a queda é "100%", e isso não significa nada.

    Abrir ticket com amostra assim é transformar ruído em conclusão — e
    ticket que ninguém age ensina o operador a ignorar tickets.
    """
    assert rev.maior_vazamento({"visitas": 2, "cliques_cta": 0,
                                "leads": 0, "leads_fechados": 0}) is None


def test_funil_saudavel_nao_vira_ticket():
    assert rev.maior_vazamento({"visitas": 100, "cliques_cta": 90,
                                "leads": 80, "leads_fechados": 70}) is None


def test_queda_abaixo_do_limite_nao_vira_ticket():
    """20% de perda é operação normal, não gargalo."""
    assert rev.maior_vazamento({"visitas": 100, "cliques_cta": 80,
                                "leads": 70, "leads_fechados": 60}) is None


# ── qual transição a rotina elege ────────────────────────────────────────

def test_desempate_e_por_perda_absoluta_nao_percentual():
    """O caso real do site em 27/07/2026.

    191 visitas → 1 clique é 99,5%; 15 leads → 0 fechados é 100%. O percentual
    elegeria a segunda, mas a primeira perde 190 pessoas contra 15 — e é ali
    que mexer muda o resultado do mês.
    """
    de, para, queda = rev.maior_vazamento(
        {"visitas": 191, "cliques_cta": 1, "leads": 15, "leads_fechados": 0})
    assert (de, para) == ("visitas", "cliques_cta")
    assert queda == 99.5


def test_gargalo_no_meio_e_encontrado():
    de, para, _ = rev.maior_vazamento(
        {"visitas": 500, "cliques_cta": 400, "leads": 40, "leads_fechados": 30})
    assert (de, para) == ("cliques_cta", "leads")


# ── a memória entre execuções ────────────────────────────────────────────

def test_hipotese_nova_nao_cita_historico():
    p = rev.sugerir("visitas", "cliques_cta", 80.0, [])
    assert "Já mexemos aqui antes" not in p["hipotese"]
    assert p["decisao"] is None


def test_segunda_vez_na_mesma_transicao_lembra_a_decisao_anterior():
    """É isto que separa aprendizado de automação: a hipótese recusada na
    semana passada muda o que se propõe nesta."""
    antes = [{"data": "2026-07-20T09:00:00", "transicao": "visitas->cliques_cta",
              "queda_pct": 99.0, "decisao": "recusada — o CTA já estava acima da dobra"}]
    p = rev.sugerir("visitas", "cliques_cta", 96.0, antes)
    assert "Já mexemos aqui antes" in p["hipotese"]
    assert "recusada" in p["hipotese"]
    assert "olhar a etapa anterior" in p["hipotese"]


def test_historico_de_outra_transicao_nao_contamina():
    antes = [{"data": "2026-07-20T09:00:00", "transicao": "leads->leads_fechados",
              "queda_pct": 100.0, "decisao": "aprovada"}]
    p = rev.sugerir("visitas", "cliques_cta", 80.0, antes)
    assert "Já mexemos aqui antes" not in p["hipotese"]


def test_memoria_sobrevive_a_arquivo_corrompido(monkeypatch, tmp_path):
    """Histórico ilegível não pode derrubar a revisão da semana."""
    ruim = tmp_path / "hipoteses.json"
    ruim.write_text("{ isto não é json", encoding="utf-8")
    monkeypatch.setattr(rev, "MEMORIA", ruim)
    assert rev.historico() == []


def test_grava_e_le_o_historico(monkeypatch, tmp_path):
    arq = tmp_path / "sub" / "hipoteses.json"
    monkeypatch.setattr(rev, "MEMORIA", arq)
    rev.gravar_historico([{"transicao": "a->b", "decisao": "aprovada"}])
    assert rev.historico()[0]["decisao"] == "aprovada"


# ── a rotina está de fato agendada ───────────────────────────────────────

def test_a_rotina_esta_no_scheduler():
    """Rotina que existe mas ninguém chama é código morto."""
    sched = (REPO_ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert "weekly_funnel_review.py" in sched
    assert "sunday" in sched.lower()
