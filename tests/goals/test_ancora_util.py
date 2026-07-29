"""
tests/goals/test_ancora_util.py

2026-07-29 — o texto do link que não diz nada.

Os posts de 28 e 29/07/2026 saíram com "Clique aqui" e "clique aqui e veja as
estruturas que usamos" como texto do CTA, mesmo com a instrução no prompt.
É o mesmo padrão do travessão: instrução negativa não vence hábito de treino,
precisa de rede embaixo.

Run:
    pytest tests/goals/test_ancora_util.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from escritor_de_artigo import ancora_util  # noqa: E402


FUNIL = "https://sistemabritto.com.br/whatsapp"


# ── os casos que saíram em produção ──────────────────────────────────────

def test_clique_aqui_puro_e_trocado():
    """O que saiu no post de 29/07."""
    html = f'<p>Para ver na prática, <a href="{FUNIL}">Clique aqui</a>.</p>'
    saida = ancora_util(html, "chatbot whatsapp")
    assert "Clique aqui" not in saida
    assert "ver como montamos o atendimento" in saida
    assert FUNIL in saida            # o href não pode ser tocado


def test_clique_aqui_com_cauda_e_trocado_inteiro():
    """"clique aqui e veja as estruturas que usamos" — o do post de 28/07.

    A cauda tem que sair junto: trocar só o "clique aqui" deixaria
    "ver como montamos o atendimento e veja as estruturas que usamos".
    """
    html = f'<p><a href="{FUNIL}">clique aqui e veja as estruturas que usamos</a></p>'
    saida = ancora_util(html, "chatbot whatsapp")
    assert "clique aqui" not in saida.lower()
    assert "estruturas que usamos" not in saida
    assert ">ver como montamos o atendimento</a>" in saida


# ── as outras âncoras vazias ─────────────────────────────────────────────

def test_variacoes_genericas_sao_trocadas():
    for ruim in ("Saiba mais", "confira", "ACESSE AQUI", "veja mais", "aqui", "link"):
        html = f'<p><a href="{FUNIL}">{ruim}</a></p>'
        saida = ancora_util(html, "chatbot whatsapp")
        assert ruim.lower() not in saida.lower(), f"não trocou: {ruim}"


def test_url_crua_como_texto_e_trocada():
    """Link exposto não é âncora, é ruído — e some no meio do parágrafo."""
    html = f'<p>Veja <a href="{FUNIL}">{FUNIL}</a>.</p>'
    saida = ancora_util(html, "chatbot whatsapp")
    assert f'>{FUNIL}</a>' not in saida
    assert "ver como montamos o atendimento" in saida


# ── o que NÃO pode ser tocado ────────────────────────────────────────────

def test_ancora_boa_e_preservada():
    """Se o modelo acertou, não mexe. O guard é rede, não reescritor."""
    html = f'<p><a href="{FUNIL}">ver o fluxo de atendimento que montamos</a></p>'
    assert ancora_util(html, "chatbot whatsapp") == html


def test_link_externo_com_ancora_ruim_e_preservado():
    """Âncora ruim em link de terceiro é problema do destino, não nosso —
    e reescrever citação alheia seria pior que o problema."""
    html = '<p>Fonte: <a href="https://exemplo.com/estudo">clique aqui</a></p>'
    assert ancora_util(html, "chatbot whatsapp") == html


def test_texto_com_tag_dentro_do_link_nao_e_destruido():
    html = f'<p><a href="{FUNIL}"><strong>montar meu atendimento</strong></a></p>'
    assert ancora_util(html, "chatbot whatsapp") == html


# ── substituto por funil ─────────────────────────────────────────────────

def test_substituto_segue_o_funil_da_keyword():
    """Cada funil vende uma coisa diferente; a âncora tem que dizer qual."""
    html_sj = '<p><a href="https://sistemabritto.com.br/socialjobs">clique aqui</a></p>'
    assert "operação de conteúdo" in ancora_util(html_sj, "roteiro para reels")

    html_sis = '<p><a href="https://sistemabritto.com.br/sistema">clique aqui</a></p>'
    assert "PRD" in ancora_util(html_sis, "automacao de processos")


def test_sem_keyword_usa_fallback_generico():
    html = f'<p><a href="{FUNIL}">clique aqui</a></p>'
    saida = ancora_util(html, "")
    assert "clique aqui" not in saida.lower()
    assert "</a>" in saida


def test_html_vazio_nao_quebra():
    assert ancora_util("", "x") == ""
    assert ancora_util(None, "x") is None  # type: ignore[arg-type]


def test_varios_links_no_mesmo_html():
    html = (
        f'<p>Um: <a href="{FUNIL}">clique aqui</a>.</p>'
        f'<p>Dois: <a href="{FUNIL}">ver o fluxo pronto</a>.</p>'
        f'<p>Três: <a href="https://exemplo.com">saiba mais</a>.</p>'
    )
    saida = ancora_util(html, "chatbot whatsapp")
    assert saida.count("ver como montamos o atendimento") == 1   # só o primeiro
    assert "ver o fluxo pronto" in saida                          # bom, preservado
    assert ">saiba mais</a>" in saida                             # externo, preservado
