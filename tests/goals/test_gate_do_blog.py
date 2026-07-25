"""
tests/goals/test_gate_do_blog.py

Fluxo de conteúdo em dois estágios (decisão do Felipe, 25/07/2026):

    draft no Ghost
      -> gate 1: humano lê o texto, confere os CTAs e vê a capa
      -> aprovado: publica/agenda no Ghost
      -> webhook post.published dispara a ponte
      -> gate 2..4: uma aprovação por rede (X, LinkedIn, Threads)

O ponto é a ordem. Derivar post de rede a partir de artigo não aprovado gasta
aprovação humana em cima de conteúdo que talvez nem devesse existir, e pior:
deixa o post da rede sair sem que ninguém tenha lido o artigo.

O erro perigoso deste módulo é confundir os dois textos: `publish_content` é o
resumo que o humano lê para decidir; o que se publica é o ARTIGO identificado
por `publish_ref`. Trocar um pelo outro publicaria o resumo como se fosse o
artigo.

Run:
    pytest tests/goals/test_gate_do_blog.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import ghost_publisher as gp  # noqa: E402
import ghost_social_bridge as bridge  # noqa: E402
import heartbeat_outcome as ho  # noqa: E402


DRAFT = {
    "id": "abc123",
    "status": "draft",
    "title": "IA open source vale a pena?",
    "custom_excerpt": "O que muda para quem vende.",
    "url": "https://blog.sistemabritto.com.br/p/uuid-preview/",
    "feature_image": "https://blog.sistemabritto.com.br/content/images/capa.png",
    "plaintext": "corpo " * 400,
    "html": ('<p>Texto <a href="https://sistemabritto.com.br/whatsapp">fala com a gente</a> '
             'e <a href="https://blog.sistemabritto.com.br/outro/">outro artigo</a> '
             'e <a href="https://exemplo.com/fonte">fonte</a>.</p>'),
    "updated_at": "2026-07-25T20:00:00.000Z",
}


# ── o que o humano vê para decidir ───────────────────────────────────────

def test_separa_cta_de_funil_de_link_externo(monkeypatch):
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    ctas = gp.ctas_do_artigo(DRAFT)
    assert ctas["funis"] == ["https://sistemabritto.com.br/whatsapp"]
    assert ctas["externos"] == ["https://exemplo.com/fonte"]
    assert ctas["internos"] == ["https://blog.sistemabritto.com.br/outro/"]


def test_resumo_mostra_o_cta_para_conferir_antes_de_publicar(monkeypatch):
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    texto = gp.resumo_para_aprovacao(DRAFT)
    assert "sistemabritto.com.br/whatsapp" in texto
    assert "IA open source vale a pena?" in texto


def test_artigo_sem_cta_avisa_em_vez_de_passar_batido(monkeypatch):
    """Informa e não converte é erro que só aparece depois de publicado."""
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    sem_cta = {**DRAFT, "html": '<p><a href="https://exemplo.com/x">fonte</a></p>'}
    assert "NENHUM CTA" in gp.resumo_para_aprovacao(sem_cta)


def test_artigo_sem_capa_avisa(monkeypatch):
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    assert "SEM imagem de capa" in gp.resumo_para_aprovacao({**DRAFT, "feature_image": ""})


# ── o gate ───────────────────────────────────────────────────────────────

@pytest.fixture
def ghost_falso(monkeypatch):
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    monkeypatch.setattr(gp, "buscar", lambda _id: DRAFT)
    return DRAFT


def test_gate_do_blog_carrega_o_id_do_artigo_e_nao_so_o_texto(ghost_falso):
    r = bridge.aprovar_artigo("abc123", dry_run=True)
    o = r["outcome"]
    assert o["publish_target"] == "blog"
    assert o["publish_ref"] == "abc123", "sem o id não há o que publicar"
    assert o["publish_content"] != o["publish_ref"]


def test_gate_do_blog_leva_capa_e_preview(ghost_falso):
    o = bridge.aprovar_artigo("abc123", dry_run=True)["outcome"]
    assert o["publish_media"] == [DRAFT["feature_image"]]
    assert o["source_url"] == DRAFT["url"], "o preview do draft abre sem login"


def test_artigo_ja_publicado_nao_abre_gate_de_novo(monkeypatch):
    monkeypatch.setattr(gp, "buscar", lambda _id: {**DRAFT, "status": "published"})
    r = bridge.aprovar_artigo("abc123", dry_run=True)
    assert r["ok"] is True and "ignorado" in r


def test_post_inexistente_falha_claro(monkeypatch):
    monkeypatch.setattr(gp, "buscar", lambda _id: None)
    r = bridge.aprovar_artigo("sumiu", dry_run=True)
    assert r["ok"] is False and "não encontrado" in r["erro"]


# ── execução da aprovação ────────────────────────────────────────────────

def test_blog_publica_pelo_ghost_e_nao_pelo_postiz(monkeypatch):
    chamou = {}
    monkeypatch.setattr(gp, "publicar",
                        lambda ref, quando=None: chamou.update(ref=ref, quando=quando)
                        or {"published": True, "detail": "publicado."})
    r = ho._run_blog_publish({"publish_ref": "abc123", "publish_at": None})
    assert r["published"] is True
    assert chamou["ref"] == "abc123"


def test_sem_publish_ref_recusa_em_vez_de_adivinhar():
    r = ho._run_blog_publish({"publish_content": "resumo bonito"})
    assert r["published"] is False and "publish_ref" in r["detail"]


def test_data_no_passado_e_recusada():
    r = ho._run_blog_publish({"publish_ref": "abc", "publish_at": "2020-01-01T00:00:00Z"})
    assert r["published"] is False and "passado" in r["detail"]


def test_blog_e_canal_valido_do_gate():
    assert "blog" in ho.PUBLISH_CHANNELS


# ── ordem dos estágios ───────────────────────────────────────────────────

def test_ponte_das_redes_recusa_artigo_nao_publicado(monkeypatch):
    """A garantia central: rede nunca deriva de artigo em draft."""
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: DRAFT)
    r = bridge.distribuir("abc123", dry_run=True)
    assert r.get("ignorado"), f"deveria recusar draft, devolveu {r}"
    assert not r.get("redes")


def test_ponte_das_redes_aceita_publicado(monkeypatch):
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: {**DRAFT, "status": "published"})
    monkeypatch.setenv("XAI_API_KEY", "")
    r = bridge.distribuir("abc123", dry_run=True)
    assert set(r["redes"]) == set(bridge.REDES)
