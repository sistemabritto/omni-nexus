"""
tests/goals/test_sem_travessao.py

2026-07-27 — o travessão que denuncia o texto de máquina.

O Felipe leu as páginas do site e apontou de imediato: "tira os travessões,
fica a cara da IA quando usa travessão". Ele está certo sobre o que importa
aqui. O travessão é gramatical em português, mas hoje o leitor associa o
símbolo a texto gerado, e a percepção de quem lê decide se o texto convence.

A proibição está no prompt do escritor e no do bridge. Instrução negativa,
porém, não vence hábito de treino: o modelo volta a usar. Estes testes
guardam a rede que age depois da geração.

Run:
    pytest tests/goals/test_sem_travessao.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from escritor_de_artigo import sem_travessao  # noqa: E402


# ── a troca por pontuação equivalente ────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    ("O problema não é você — é o WhatsApp.", "O problema não é você, é o WhatsApp."),
    ("Design, código, infra — tudo pro seu negócio.",
     "Design, código, infra, tudo pro seu negócio."),
    ("<p>Tag — e texto</p>", "<p>Tag, e texto</p>"),
    ("Meia-risca – também sai.", "Meia-risca, também sai."),
])
def test_travessao_vira_virgula(entrada, esperado):
    assert sem_travessao(entrada) == esperado


def test_colado_nao_cola_as_palavras():
    """"redes—uma" virando "redesuma" seria pior que deixar o travessão."""
    assert sem_travessao("Três redes—uma esteira.") == "Três redes, uma esteira."


def test_entre_digitos_vira_hifen():
    """Ali é intervalo, e intervalo com vírgula vira outra coisa."""
    assert sem_travessao("Entre 2020—2024 mudou tudo.") == "Entre 2020-2024 mudou tudo."


# ── o que não pode acontecer ─────────────────────────────────────────────

def test_nao_deixa_pontuacao_dobrada():
    assert sem_travessao("Isso custa caro, — e ninguém avisa.") == \
        "Isso custa caro, e ninguém avisa."


def test_nao_deixa_espaco_pendurado_antes_da_tag():
    assert sem_travessao("<p>Ele some no fim —</p>") == "<p>Ele some no fim</p>"


def test_hifen_de_palavra_composta_sobrevive():
    """Hífen não é travessão. Mexer nele quebraria 'guarda-chuva'."""
    assert sem_travessao("guarda-chuva bem-vindo") == "guarda-chuva bem-vindo"


def test_texto_limpo_passa_intacto():
    limpo = "Sem travessão nenhum aqui, só vírgula."
    assert sem_travessao(limpo) == limpo


@pytest.mark.parametrize("vazio", ["", None])
def test_vazio_nao_quebra(vazio):
    assert sem_travessao(vazio) == vazio


# ── os dois caminhos de geração aplicam o guard ──────────────────────────

def test_prompt_do_artigo_proibe_travessao():
    from escritor_de_artigo import montar_prompt

    assert "travessão" in montar_prompt({"keyword": "chatbot whatsapp"}).lower()


def test_briefing_das_redes_proibe_travessao():
    import ghost_social_bridge as bridge

    assert "travessão" in bridge.BRIEFING.lower()


def test_limpar_das_redes_aplica_o_guard():
    """O texto da rede passa por `limpar`; é ali que a rede tem de agir."""
    import ghost_social_bridge as bridge

    assert "—" not in bridge.limpar("Post pronto — com travessão.", 280)


def test_guard_roda_antes_do_corte_de_limite():
    """Trocar travessão muda o tamanho.

    Se a troca viesse depois do corte, um post medido em 280 antes viraria
    281 depois — e o X recusa o post inteiro por um caractere.
    """
    import ghost_social_bridge as bridge

    texto = "a" * 270 + " — fim demais para caber"
    assert len(bridge.limpar(texto, 280)) <= 280
