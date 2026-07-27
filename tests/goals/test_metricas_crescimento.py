"""
tests/goals/test_metricas_crescimento.py

2026-07-26 — o laço de medição que a esteira não tinha.

O único escritor de progresso era `_recompute_goal_from_tickets`, que conta
TICKET RESOLVIDO. Uma Goal de "1000 seguidores" media quantas tarefas foram
fechadas, não quantos seguidores existem — o mesmo tipo de mentira que deixou
`pipeline-reels-vertical-pronto` cumprida com zero trabalho.

Aqui mora o resultado; `goals.current_value` segue medindo execução.

Run:
    pytest tests/goals/test_metricas_crescimento.py -v
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import metricas_crescimento as mc  # noqa: E402


@pytest.fixture
def banco(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "DB_PATH", tmp_path / "evonexus.db")
    return mc


# ── gravação e idempotência ──────────────────────────────────────────────

def test_grava_medicoes(banco):
    assert banco.gravar([{"metrica": mc.VISITAS, "valor": 141},
                         {"metrica": mc.LEADS, "valor": 26}]) == 2
    assert banco.ultimo(mc.VISITAS) == 141


def test_coletar_duas_vezes_no_mesmo_dia_atualiza(banco):
    """A rotina roda diária mas pode ser disparada à mão para conferir. Série
    com ponto duplicado mente sobre a tendência."""
    hoje = date.today()
    banco.gravar([{"metrica": mc.VISITAS, "valor": 100}], dia=hoje)
    banco.gravar([{"metrica": mc.VISITAS, "valor": 141}], dia=hoje)
    assert len(banco.serie(mc.VISITAS)) == 1
    assert banco.ultimo(mc.VISITAS) == 141


def test_origens_diferentes_convivem(banco):
    """'20 visitas' e '20 visitas vindas do X' são fatos distintos."""
    hoje = date.today()
    banco.gravar([
        {"metrica": mc.VISITAS, "valor": 141},
        {"metrica": mc.VISITAS, "origem": "blog", "valor": 12},
        {"metrica": mc.VISITAS, "origem": "x", "valor": 8},
    ], dia=hoje)
    assert banco.ultimo(mc.VISITAS) == 141
    assert banco.ultimo(mc.VISITAS, origem="x") == 8


def test_medicao_sem_valor_e_ignorada(banco):
    assert banco.gravar([{"metrica": mc.VISITAS}, {"valor": 10}]) == 0


def test_origem_e_normalizada(banco):
    """'IG' e 'ig' seriam duas origens — foi o que aconteceu no site real."""
    banco.gravar([{"metrica": mc.VISITAS, "origem": " IG ", "valor": 4}])
    assert banco.ultimo(mc.VISITAS, origem="ig") == 4


# ── série histórica ──────────────────────────────────────────────────────

def test_serie_vem_em_ordem_cronologica(banco):
    hoje = date.today()
    for i, v in enumerate([100, 120, 141]):
        banco.gravar([{"metrica": mc.VISITAS, "valor": v}], dia=hoje - timedelta(days=2 - i))
    assert [p["valor"] for p in banco.serie(mc.VISITAS)] == [100, 120, 141]


def test_serie_respeita_a_janela(banco):
    hoje = date.today()
    banco.gravar([{"metrica": mc.VISITAS, "valor": 1}], dia=hoje - timedelta(days=60))
    banco.gravar([{"metrica": mc.VISITAS, "valor": 2}], dia=hoje)
    assert len(banco.serie(mc.VISITAS, dias=30)) == 1


def test_variacao_mede_o_crescimento(banco):
    hoje = date.today()
    banco.gravar([{"metrica": mc.LEADS, "valor": 20}], dia=hoje - timedelta(days=6))
    banco.gravar([{"metrica": mc.LEADS, "valor": 26}], dia=hoje)
    v = banco.variacao(mc.LEADS, dias=7)
    assert v["de"] == 20 and v["para"] == 26 and v["delta"] == 6
    assert v["pct"] == 30.0


def test_variacao_com_um_ponto_so_e_nula(banco):
    """Variação sobre um ponto seria invenção."""
    banco.gravar([{"metrica": mc.LEADS, "valor": 26}])
    assert banco.variacao(mc.LEADS) is None


def test_variacao_partindo_de_zero_nao_divide(banco):
    hoje = date.today()
    banco.gravar([{"metrica": mc.LEADS, "valor": 0}], dia=hoje - timedelta(days=3))
    banco.gravar([{"metrica": mc.LEADS, "valor": 5}], dia=hoje)
    v = banco.variacao(mc.LEADS, dias=7)
    assert v["delta"] == 5
    assert v["pct"] is None


# ── o resumo do painel ───────────────────────────────────────────────────

def test_resumo_mede_o_trafego_cego(banco):
    """A métrica que diz se a convenção de UTM está funcionando. Começou em
    95%: 134 de 141 visitas sem origem."""
    banco.gravar([
        {"metrica": mc.VISITAS, "origem": "direct", "valor": 134},
        {"metrica": mc.VISITAS, "origem": "blog", "valor": 5},
        {"metrica": mc.VISITAS, "origem": "x", "valor": 2},
    ])
    r = banco.resumo()
    assert r["trafego_sem_origem_pct"] == 95.0


def test_resumo_ordena_origens_por_volume(banco):
    banco.gravar([
        {"metrica": mc.VISITAS, "origem": "x", "valor": 2},
        {"metrica": mc.VISITAS, "origem": "blog", "valor": 9},
    ])
    assert [o["origem"] for o in banco.resumo()["por_origem"]] == ["blog", "x"]


def test_resumo_de_banco_vazio_nao_quebra(banco):
    r = banco.resumo()
    assert r["por_origem"] == []
    assert r["trafego_sem_origem_pct"] is None
    assert r["atual"][mc.VISITAS] is None


# ── o coletor do site ────────────────────────────────────────────────────

def test_coletor_exige_a_senha(monkeypatch):
    import site_analytics as sa

    monkeypatch.delenv("SITE_ADMIN_PASSWORD", raising=False)
    with pytest.raises(sa.SiteIndisponivel, match="SITE_ADMIN_PASSWORD"):
        sa.coletar()


def test_senha_nunca_entra_na_mensagem_de_erro(monkeypatch):
    """Mensagem de erro vira log e vira ticket — segredo ali vaza duas vezes."""
    import site_analytics as sa

    monkeypatch.setenv("SITE_ADMIN_PASSWORD", "senha-secreta-123")

    class _R:
        status_code = 401

        def json(self):
            return {}

    monkeypatch.setattr(sa.requests, "post", lambda *a, **k: _R())
    with pytest.raises(sa.SiteIndisponivel) as e:
        sa.coletar()
    assert "senha-secreta-123" not in str(e.value)


def test_coletor_normaliza_a_resposta_do_site(monkeypatch):
    import site_analytics as sa

    monkeypatch.setenv("SITE_ADMIN_PASSWORD", "x")
    monkeypatch.setattr(sa, "_token", lambda: "tok")

    def _get(caminho, token, **params):
        if "analytics" in caminho:
            return {"totalPageviews": 141, "uniqueVisitors": 96, "totalCtaClicks": 0,
                    "trafficBySource": [{"source": "direct", "views": 134},
                                        {"source": "blog", "views": 1}],
                    "topPages": [{"path": "/", "views": 79},
                                 {"path": "/sistema", "views": 20},
                                 {"path": "/socialjobs", "views": 12},
                                 {"path": "/whatsapp", "views": 9}]}
        return {"total": 26, "stages": [{"name": "Novo Lead", "count": 22},
                                        {"name": "Fechado", "count": 4}]}

    monkeypatch.setattr(sa, "_get", _get)
    m = {(x["metrica"], x.get("origem")): x["valor"] for x in sa.coletar()}

    assert m[(mc.VISITAS, None)] == 141
    assert m[(mc.VISITAS, "direct")] == 134
    assert m[(mc.LEADS, None)] == 26
    assert m[(mc.LEADS_FECHADOS, None)] == 4
    # A home fica de fora do total de funil: ela recebe a maior parte do
    # tráfego e misturá-la mascararia se o conteúdo empurra para a oferta.
    assert m[(mc.VISITAS_FUNIL, None)] == 41


def test_leads_indisponiveis_nao_perdem_o_analytics(monkeypatch):
    """Dado parcial vale mais que dado nenhum."""
    import site_analytics as sa

    monkeypatch.setenv("SITE_ADMIN_PASSWORD", "x")
    monkeypatch.setattr(sa, "_token", lambda: "tok")

    def _get(caminho, token, **params):
        if "leads" in caminho:
            raise sa.SiteIndisponivel("500")
        return {"totalPageviews": 10, "uniqueVisitors": 8, "totalCtaClicks": 0}

    monkeypatch.setattr(sa, "_get", _get)
    m = {x["metrica"] for x in sa.coletar()}
    assert mc.VISITAS in m
    assert mc.LEADS not in m


# ── atribuição do clique ao artigo ───────────────────────────────────────
# 2026-07-27: `trackCta` existia no site e nenhum botão a chamava — 636
# pageviews contra 1 clique registrado. Depois de instrumentar, o que faltava
# era responder QUAL artigo converteu: o total sozinho não distingue um post
# que converte de vinte que não convertem.

def test_resumo_mostra_quais_artigos_converteram(banco):
    hoje = date.today()
    banco.gravar([
        {"metrica": mc.CLIQUES_POR_ARTIGO, "origem": "bot-para-whatsapp", "valor": 7},
        {"metrica": mc.CLIQUES_POR_ARTIGO, "origem": "trafego-pago-instagram", "valor": 2},
    ], dia=hoje)

    por_artigo = banco.resumo()["por_artigo"]
    assert [a["artigo"] for a in por_artigo] == ["bot-para-whatsapp", "trafego-pago-instagram"]
    assert por_artigo[0]["valor"] == 7


def test_taxa_de_clique_fecha_o_funil(banco):
    """De quem chegou, quantos clicaram — o número que dizia zero enquanto
    nenhum botão do site registrava."""
    hoje = date.today()
    banco.gravar([{"metrica": mc.VISITAS, "valor": 200},
                  {"metrica": mc.CLIQUES_CTA, "valor": 13}], dia=hoje)
    assert banco.resumo()["taxa_clique_pct"] == 6.5


def test_taxa_de_clique_sem_visita_e_nula_em_vez_de_zero(banco):
    """Zero sugere "ninguém clicou"; nulo diz "ainda não há o que medir"."""
    assert banco.resumo()["taxa_clique_pct"] is None


def test_variacao_de_cliques_entra_no_resumo(banco):
    """Sem a série de cliques, dá para ver o total mas não se está subindo."""
    hoje = date.today()
    banco.gravar([{"metrica": mc.CLIQUES_CTA, "valor": 4}], dia=hoje - timedelta(days=7))
    banco.gravar([{"metrica": mc.CLIQUES_CTA, "valor": 12}], dia=hoje)
    v = banco.resumo()["variacao_7d"][mc.CLIQUES_CTA]
    assert (v["de"], v["para"], v["pct"]) == (4.0, 12.0, 200.0)


def test_resumo_de_base_vazia_nao_quebra(banco):
    r = banco.resumo()
    assert r["por_artigo"] == []
    assert r["taxa_clique_pct"] is None
