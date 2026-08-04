"""
tests/goals/test_utm.py

2026-07-26 — a origem de cada clique que a esteira gera.

Medido no analytics de sistemabritto.com.br: de 141 visitas em 30 dias, **134
caíram em "direct"** — 95% sem origem identificável. Das 7 restantes, duas
grafias apontavam para a mesma rede (`ig` com 4 visitas, `instagram` com 2),
fragmentando o pouco que existia.

Sem isso não dá para saber se os 41 acessos aos funis vieram do blog, do X ou
de indicação — e sem saber, não dá para decidir onde investir esforço.

Run:
    pytest tests/goals/test_utm.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import utm  # noqa: E402


FUNIL = "https://sistemabritto.com.br/whatsapp"
ARTIGO = "https://blog.sistemabritto.com.br/resposta-automatica/"


def _params(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# ── marcação básica ──────────────────────────────────────────────────────

def test_marca_origem_e_meio():
    p = _params(utm.marcar(FUNIL, "blog"))
    assert p["utm_source"] == "blog"
    assert p["utm_medium"] == "content"


@pytest.mark.parametrize("rede,meio", [
    ("x", "social"), ("linkedin", "social"), ("threads", "social"),
    ("instagram", "social"), ("tiktok", "social"), ("youtube", "video"),
])
def test_cada_rede_tem_origem_propria(rede, meio):
    p = _params(utm.marcar(FUNIL, rede))
    assert p["utm_source"] == rede
    assert p["utm_medium"] == meio


def test_campanha_vira_slug_estavel():
    """'automação' e 'automacao' viravam duas campanhas para o mesmo artigo."""
    a = _params(utm.marcar(FUNIL, "blog", campanha="Automação no WhatsApp!"))
    assert a["utm_campaign"] == "automacao-no-whatsapp"


def test_preserva_query_que_ja_existia():
    url = utm.marcar("https://sistemabritto.com.br/whatsapp?plano=pro", "x")
    p = _params(url)
    assert p["plano"] == "pro"
    assert p["utm_source"] == "x"


# ── idempotência: o texto passa por reescrita e refação ──────────────────

def test_marcar_duas_vezes_nao_duplica():
    """Sem isto sairia utm_source=blog&utm_source=x, e o analytics leria o
    primeiro — atribuindo o clique à origem errada."""
    uma = utm.marcar(FUNIL, "blog")
    duas = utm.marcar(uma, "x")
    assert duas == uma
    assert _params(duas)["utm_source"] == "blog"


def test_texto_remarcado_fica_intacto():
    texto = f"Veja em {FUNIL}"
    uma = utm.marcar_no_texto(texto, "x")
    assert utm.marcar_no_texto(uma, "linkedin") == uma


# ── só o que é nosso ─────────────────────────────────────────────────────

def test_link_externo_nao_e_marcado():
    """Rastrear link de terceiro polui o analytics deles e não nos diz nada —
    esse clique nunca volta."""
    fora = "https://developers.facebook.com/docs/"
    assert utm.marcar_no_texto(f"fonte: {fora}", "blog") == f"fonte: {fora}"


def test_subdominio_do_blog_conta_como_nosso():
    """O link do artigo compartilhado na rede precisa carregar a origem."""
    assert utm.e_funil(ARTIGO) is True
    assert "utm_source=x" in utm.marcar(ARTIGO, "x")


def test_dominio_parecido_nao_engana():
    assert utm.e_funil("https://sistemabritto.com.br.evil.com/x") is False


# ── varredura no texto do post ───────────────────────────────────────────

def test_marca_todos_os_funis_do_texto():
    texto = (f"Comece em {FUNIL} ou veja o sistema em "
             "https://sistemabritto.com.br/sistema hoje.")
    saida = utm.marcar_no_texto(texto, "linkedin")
    assert saida.count("utm_source=linkedin") == 2


def test_nao_engole_o_fecho_do_markdown():
    texto = f"[clique aqui]({FUNIL})"
    saida = utm.marcar_no_texto(texto, "x")
    assert saida.endswith(")")
    assert "utm_source=x" in saida


def test_texto_sem_link_passa_intacto():
    assert utm.marcar_no_texto("Sem link nenhum aqui.", "x") == "Sem link nenhum aqui."


def test_texto_vazio_nao_quebra():
    assert utm.marcar_no_texto("", "x") == ""
    assert utm.marcar("", "x") == ""


def test_valor_que_nao_e_url_passa_intacto():
    assert utm.marcar("nao sou url", "x") == "nao sou url"


# ── integração com a esteira ─────────────────────────────────────────────

def test_artigo_sai_com_utm_do_blog(monkeypatch):
    import json

    import escritor_de_artigo as escritor

    corpo = ("<p>" + ("palavra " * 700) + "</p>"
             f'<p><a href="{FUNIL}">veja</a></p>')
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: json.dumps(
                            {"titulo": "Chatbot no WhatsApp", "excerpt": "e", "html": corpo}))
    artigo, erro = escritor.escrever(
        {"keyword": "chatbot whatsapp para empresas", "volume": 100, "kd": 10})
    assert erro == ""
    assert "utm_source=blog" in artigo["html"]
    assert "utm_campaign=chatbot-no-whatsapp" in artigo["html"]


def test_link_no_post_da_rede_carrega_a_rede():
    import ghost_social_bridge as bridge

    texto = bridge.garantir_link("Gancho.", ARTIGO, "x", "Título do Artigo")
    assert "utm_source=x" in texto
    assert "utm_medium=social" in texto


def test_comentario_do_linkedin_carrega_a_rede():
    import ghost_social_bridge as bridge

    c = bridge.comentarios_da_rede("linkedin", ARTIGO, "Título")[0]
    assert "utm_source=linkedin" in c


def test_utm_cabe_no_limite_do_x():
    """O UTM ocupa espaço real: reservar sem contá-lo estouraria o post e o
    Postiz devolveria 400 'post is too long'."""
    import ghost_social_bridge as bridge

    texto = bridge.garantir_link("palavra " * 200, ARTIGO, "x", "Um Título Longo Para Testar")
    assert bridge.medida(texto) <= bridge.teto_de("x")
    assert "utm_source=x" in texto
