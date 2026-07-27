"""
tests/goals/test_rule_da_esteira.py

2026-07-27 — o padrão da esteira vira instrução, não só código.

O Felipe pediu que o padrão de thumbnail, CTA, texto humanizado e diversidade de
tema ficasse salvo nas instruções do Nexus, "para que eles se virem daqui pra
frente". Documentação que ninguém verifica apodrece: alguém renomeia
`variacao_de`, a rule segue mandando chamá-la, e o agente que a lê faz a coisa
errada com convicção.

Estes testes não julgam a redação — checam que cada função e caminho que a rule
manda usar continua existindo, e que o primer da skill não voltou a contradizê-la.

Run:
    pytest tests/goals/test_rule_da_esteira.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

RULE = REPO_ROOT / ".claude" / "rules" / "esteira-de-conteudo.md"
PRIMER = (REPO_ROOT / ".claude" / "skills" / "social-ai-trends-blog" / "assets"
          / "THUMBNAIL-PRIMER.md")


@pytest.fixture(scope="module")
def rule() -> str:
    return RULE.read_text(encoding="utf-8")


def test_a_rule_vive_onde_o_agente_a_encontra(rule):
    """`.claude/rules/` é auto-carregado pelo Claude Code, e é versionado —
    que é o que faz a instrução chegar à VPS junto com o código.

    O CLAUDE.md é deliberadamente gitignored (na VPS ele é um symlink para o
    volume `config/`), então citar a rule lá ajuda quem lê, mas não é o que
    garante a entrega. Quem garante é o diretório de rules.
    """
    import subprocess

    assert rule.strip()
    rastreados = subprocess.run(
        ["git", "ls-files", ".claude/rules/esteira-de-conteudo.md"],
        cwd=REPO_ROOT, capture_output=True, text=True).stdout
    assert rastreados.strip(), "a rule não está versionada — não chega ao deploy"


@pytest.mark.parametrize("modulo,funcao", [
    ("thumbnail_maker", "variacao_de"),
    ("thumbnail_maker", "montar_prompt"),
    ("thumbnail_maker", "gerar"),
    ("escritor_de_artigo", "funil_de"),
    ("escritor_de_artigo", "escrever"),
    ("ghost_publisher", "briefing_de_capa"),
    ("ghost_publisher", "criar_rascunho"),
    ("pauta_fila", "keywords_em_cache"),
    ("pauta_fila", "gravar_ciclo"),
])
def test_toda_funcao_que_a_rule_manda_usar_existe(rule, modulo, funcao):
    import importlib

    assert funcao in rule, f"a rule deixou de citar {funcao}"
    assert hasattr(importlib.import_module(modulo), funcao), \
        f"a rule manda chamar {modulo}.{funcao}, que não existe mais"


def test_a_rule_cita_os_tres_funis_reais(rule):
    from escritor_de_artigo import FUNIS

    for slug in FUNIS:
        assert f"/{slug}" in rule, f"funil {slug} fora da rule"


def test_a_rule_nao_promete_mais_poses_do_que_existem(rule):
    """"quatro fotos" e "seis registros" são números concretos na rule."""
    import thumbnail_maker as tm

    assert f"({len(tm.POSES)} fotos)" in rule
    assert f"({len(tm.REGISTROS)})" in rule


def test_o_primer_nao_contradiz_o_rodizio():
    """O primer mandava "sorriso confiante" e "terço direito" fixos — foi o que
    fez toda capa sair igual. Ele é lido por quem gera capa à mão."""
    primer = PRIMER.read_text(encoding="utf-8")
    assert "variacao_de" in primer, "o primer não aponta para o rodízio"
    assert "incongruente" in primer.lower()
    assert "alternando o lado" in primer


def test_a_rule_ensina_a_convencao_de_utm(rule):
    """A atribuição do clique ao artigo depende inteiramente disto: a campanha
    tem de ser o slug do post. Um agente que marcar o link de outro jeito
    quebra a única métrica que diz qual artigo converteu."""
    assert "utm_campaign" in rule
    assert "slug do artigo" in rule
    assert "trackCta" in rule, "quem mexer no site precisa saber que CTA registra"
    assert "keepalive" in rule, "o CTA que sai do site é o que mais converte"


def test_a_rule_registra_o_que_nao_pode_ser_reintroduzido(rule):
    """Cada item aqui é um defeito que já foi a produção. A rule existe para
    que a próxima pessoa não os redescubra do zero."""
    for armadilha in (
        "thumbnail-refs",      # referência de estilo confundida com foto do Felipe
        "images/generations",  # endpoint que recusa referência de rosto
        "source=html",         # sem isso o Ghost descarta o corpo em silêncio
        "sdk_client",          # rotina do scheduler não escreve no SQLite direto
        "draft",               # artigo nunca nasce publicado
    ):
        assert armadilha in rule, f"a rule perdeu o aviso sobre {armadilha}"
