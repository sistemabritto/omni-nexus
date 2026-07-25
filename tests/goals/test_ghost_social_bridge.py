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
    assert len(saida) <= 51  # 50 + a reticência


def test_respeita_limite_de_cada_rede():
    longo = "frase de teste. " * 300
    for rede, limite in bridge.LIMITES.items():
        assert len(bridge.limpar(longo, limite)) <= limite + 1, rede


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


def test_instagram_pulado_por_exigir_midia(monkeypatch):
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: {
        "status": "published", "title": "T", "custom_excerpt": "R", "url": "https://e.com/p"})
    monkeypatch.setattr(bridge, "adaptar", lambda post, rede: "texto")
    out = bridge.distribuir("qualquer", dry_run=True)
    assert "instagram" in out["pulados"]
    assert set(out["redes"]) == {"x", "linkedin", "threads"}
