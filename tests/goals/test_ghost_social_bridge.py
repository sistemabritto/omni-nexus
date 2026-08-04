"""
tests/goals/test_ghost_social_bridge.py

Objetivo 5 (2026-07-25) — ponte Ghost -> redes sociais.

O caso perigoso aqui não é o modelo pôr um rótulo ("**Texto final para
Threads:**"); é a limpeza desse rótulo comer prosa legítima. "Post agendado não
é post pensado: eis o problema." começa com "Post" e tem dois-pontos adiante —
uma regra ingênua ("corta até o primeiro dois-pontos") decapita o post e ele vai
ao ar truncado. Por isso o discriminador exige uma das três marcas de rótulo
real: abertura inequívoca, fecho em negrito, ou nome de rede antes do ":".

Run:
    pytest tests/goals/test_ghost_social_bridge.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import ghost_social_bridge as bridge  # noqa: E402


# ── rótulos do modelo devem sumir ────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    ("**Texto final para Threads:** Conteúdo real aqui.", "Conteúdo real aqui."),
    ("**Texto final:**\n\nIA open source não é sobre servidor.", "IA open source não é sobre servidor."),
    ("**Legenda:**\nGancho forte", "Gancho forte"),
    ("Texto final para X: Post curto.", "Post curto."),
    ("Aqui está o post para LinkedIn: Texto.", "Texto."),
    ("Segue a versão para X: Curto.", "Curto."),
    ("Caption para Instagram: Olha isso.", "Olha isso."),
])
def test_remove_rotulo_do_modelo(entrada, esperado):
    assert bridge.limpar(entrada, 2200) == esperado


def test_remove_regua_de_markdown():
    assert bridge.limpar("---\n\nTexto real.", 500) == "Texto real."


def test_remove_rotulo_e_regua_empilhados():
    assert bridge.limpar("**Legenda:**\n---\nGancho forte", 2200) == "Gancho forte"


# ── prosa legítima é intocável ───────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "Texto normal sem preâmbulo nenhum.",
    "Postar sempre no mesmo horário derruba alcance.",
    "IA open source vale a pena? Depende.",
    # o caso que motivou o discriminador estreito: começa com "Post" e tem ":"
    "Post agendado não é post pensado: eis o problema.",
    # menciona rede, mas não é rótulo
    "Texto que fala de LinkedIn e vendas, sem rótulo nenhum.",
])
def test_nao_toca_prosa_legitima(texto):
    assert bridge.limpar(texto, 2200) == texto


# ── truncamento ──────────────────────────────────────────────────────────

def test_corta_em_fim_de_frase_quando_sobra_texto_suficiente():
    entrada = "Uma frase completa. E outra que estoura o limite bem aqui agora."
    assert bridge.limpar(entrada, 30) == "Uma frase completa."


def test_nunca_parte_palavra_no_meio():
    saida = bridge.limpar("palavra " * 40, 50)
    assert saida.rstrip("…").split()[-1] == "palavra"
    assert bridge.medida(saida) <= 50  # a reticência cabe DENTRO do orçamento


def test_respeita_limite_de_cada_rede():
    longo = "frase de teste. " * 300
    for rede in bridge.LIMITES:
        teto = bridge.teto_de(rede)
        assert bridge.medida(bridge.limpar(longo, teto)) <= teto, rede


# ── o limite é medido em bytes, não em caracteres ────────────────────────
#
# A regressão real (28/07 a 02/08/2026): dez posts do X e um do Threads foram
# aprovados no Telegram e recusados pelo Postiz com
# `400 {"provider":"x","message":"post is too long, please fix it"}` — a
# aprovação parava em `approved` e o post nunca existia. Os textos mediam entre
# 271 e 280 caracteres, todos dentro do limite nominal de 280. Em bytes, todos
# passavam de 275.

def test_texto_acentuado_respeita_o_orcamento_em_bytes():
    """`len()` conta "ç" como 1; a régua que recusa o post conta como 2."""
    acentuado = "coração é ação não vá até lá após três anos. " * 40
    saida = bridge.limpar(acentuado, 200)
    assert bridge.medida(saida) <= 200
    assert len(saida) < 200, "texto acentuado tem de sobrar caracteres, não empatar"


def test_corte_por_bytes_nao_parte_caractere_multibyte():
    """Fatiar bytes crus no meio de um "ã" produziria lixo no post."""
    saida = bridge.limpar("ação " * 60, 51)
    assert bridge.medida(saida) <= 51
    saida.encode("utf-8").decode("utf-8")  # levanta se houver byte órfão


def test_post_do_x_nao_sai_colado_no_teto_da_plataforma():
    """O bug não era o corte errado — era ele mirar exatamente em 280.

    Sem margem, qualquer divergência entre a nossa régua e a do validador que
    está no caminho derruba o post inteiro. Os dados de 20 derivações reais:
    o X publicou com até 272 bytes e recusou a partir de 276.
    """
    assert bridge.teto_de("x") <= 272
    assert bridge.teto_de("threads") <= 501


# ── contrato de distribuição ─────────────────────────────────────────────

def test_offsets_evitam_publicacao_simultanea():
    """O mesmo texto saindo no mesmo minuto em 4 redes parece bot."""
    offsets = sorted(bridge.OFFSET_MIN.values())
    assert offsets == sorted(set(offsets)), "offsets duplicados publicariam junto"
    assert offsets[0] == 0


def test_jwt_do_ghost_tem_tres_partes_e_kid_no_header():
    import base64
    import json

    # chave de teste: kid arbitrário + segredo hex válido
    token = bridge.ghost_jwt("64f1a2b3c4d5e6f708192a3b:" + "ab" * 32)
    partes = token.split(".")
    assert len(partes) == 3
    header = json.loads(base64.urlsafe_b64decode(partes[0] + "=="))
    assert header["kid"] == "64f1a2b3c4d5e6f708192a3b"
    assert header["alg"] == "HS256"


def test_post_nao_publicado_nao_distribui(monkeypatch):
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: {"status": "draft", "title": "x"})
    out = bridge.distribuir("qualquer")
    assert out["ok"] is True
    assert "ignorado" in out


def test_ponte_do_blog_cobre_so_as_tres_redes_de_texto(monkeypatch):
    """Instagram, TikTok e YouTube não pertencem a este gatilho: são a trilha
    de vídeo, com produção própria (decisão do Felipe, 25/07/2026). Aqui não
    aparecem nem como "pulado" — não fazem parte do fluxo."""
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: {
        "status": "published", "title": "T", "custom_excerpt": "R", "url": "https://e.com/p"})
    monkeypatch.setattr(bridge, "adaptar", lambda post, rede: "texto")
    out = bridge.distribuir("qualquer", dry_run=True)
    assert set(out["redes"]) == {"x", "linkedin", "threads"}
    assert out["pulados"] == {}
    for rede_de_video in ("instagram", "tiktok", "youtube"):
        assert rede_de_video not in out["redes"]
        assert rede_de_video not in out["pulados"]


# ── rótulos vistos em validação real (2026-07-25) ────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    # O modelo repetiu o vocabulário da própria instrução de formato do LinkedIn
    # ("a primeira linha é o gancho") como se fosse estrutura do post.
    ("**Gancho:** IA open source não é sobre economizar servidor.",
     "IA open source não é sobre economizar servidor."),
    ("**Abertura:**\nQuem constrói sabe.", "Quem constrói sabe."),
    ("**Corpo:** O resto do texto.", "O resto do texto."),
])
def test_remove_rotulo_de_estrutura(entrada, esperado):
    assert bridge.limpar(entrada, 3000) == esperado


@pytest.mark.parametrize("texto", [
    "Gancho certeiro é o que segura o leitor: sem ele ninguém para.",
    "Corpo mole não sustenta jornada longa: treine.",
    "Abertura de capital não é para todo mundo: entenda o custo.",
])
def test_prosa_com_a_mesma_palavra_sobrevive(texto):
    """A palavra sozinha não é rótulo — sem negrito e sem 'aqui está', é frase."""
    assert bridge.limpar(texto, 3000) == texto
