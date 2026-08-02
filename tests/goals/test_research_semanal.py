"""
tests/goals/test_research_semanal.py

2026-07-27 — a semana precisa falar de três assuntos, não de um.

O ciclo de 27/07 saiu com 18 das 21 pautas sobre WhatsApp: a seleção ordenava
puramente por retorno esperado (volume ÷ dificuldade) e o WhatsApp tem volume
de busca muito acima dos outros dois funis. Os três posts de um mesmo dia
falavam da mesma coisa, e os funis /socialjobs e /sistema não recebiam tráfego
nenhum.

Run:
    pytest tests/goals/test_research_semanal.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

_spec = importlib.util.spec_from_file_location(
    "weekly_content_research", REPO_ROOT / "ADWs" / "routines" / "weekly_content_research.py")
research = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(research)

from escritor_de_artigo import funil_de  # noqa: E402


def _kw(termo: str, vol: int = 1000) -> dict:
    return {"kw": termo, "vol": vol, "kd": 20.0}


# ── rodízio de funis ─────────────────────────────────────────────────────

def test_whatsapp_nao_leva_a_semana_inteira():
    """O caso real: 21 candidatas de WhatsApp e 6 dos outros funis.

    Com a cota por funil (ceil(alvo/3) sobre os funis presentes), o WhatsApp
    fica limitado à fatia igualitária — 7 de 21 — e os slots vagos voltam para
    pautas_do_x no main(), que é a fonte de diversidade de verdade.
    """
    keywords = ([_kw(f"bot para whatsapp {i}", 9000 - i) for i in range(21)]
                + [_kw(f"agendar post instagram {i}", 300) for i in range(3)]
                + [_kw(f"automatizar processos da empresa {i}", 200) for i in range(3)])

    escolhidas = research.alternar_funis(keywords, 21)

    por_funil = {}
    for k in escolhidas:
        por_funil[funil_de(k["kw"])] = por_funil.get(funil_de(k["kw"]), 0) + 1
    assert por_funil["socialjobs"] == 3
    assert por_funil["sistema"] == 3
    assert por_funil["whatsapp"] == 7  # cota: antes era 15, saturando a semana


def test_cada_dia_nasce_com_um_assunto_de_cada_funil():
    """A queixa não era o total, era ver o mesmo tema três vezes num dia.

    As pautas viram calendário em blocos de três (POSTS_POR_DIA), então
    intercalar a lista é o que garante variedade dentro do dia.
    """
    keywords = ([_kw(f"chatbot whatsapp {i}") for i in range(7)]
                + [_kw(f"roteiro para reels {i}") for i in range(7)]
                + [_kw(f"agentes de ia para negocios {i}") for i in range(7)])

    escolhidas = research.alternar_funis(keywords, 21)

    for dia in range(7):
        bloco = escolhidas[dia * 3:(dia + 1) * 3]
        assert len({funil_de(k["kw"]) for k in bloco}) == 3, f"dia {dia} repetiu funil"


def test_funil_esgotado_nao_segura_os_outros():
    """Faltar pauta de um funil limita o outro à cota — o resto vem do X.

    Antes o WhatsApp engolia o slot vazio de socialjobs e a semana nascia
    monótona. Agora o WhatsApp fica na cota (ceil(21/2) com dois funis
    presentes = 11) e o que sobrar é responsabilidade do pautas_do_x no
    main(), não do rodízio.
    """
    keywords = ([_kw(f"bot para whatsapp {i}") for i in range(20)]
                + [_kw("agendar post instagram")])
    escolhidas = research.alternar_funis(keywords, 21)
    por_funil = {f: sum(1 for k in escolhidas if funil_de(k["kw"]) == f)
                 for f in ("whatsapp", "socialjobs", "sistema")}
    assert por_funil["whatsapp"] == 11  # cota com dois funis presentes
    assert por_funil["socialjobs"] == 1


def test_ordem_de_retorno_esperado_e_preservada_dentro_do_funil():
    """O rodízio equilibra entre funis; não reordena o mérito dentro de um."""
    keywords = [_kw("bot para whatsapp A"), _kw("bot para whatsapp B"),
                _kw("bot para whatsapp C")]
    escolhidas = research.alternar_funis(keywords, 3)
    assert [k["kw"][-1] for k in escolhidas] == ["A", "B", "C"]


def test_lista_vazia_nao_quebra():
    assert research.alternar_funis([], 21) == []


# ── o classificador que o rodízio usa ────────────────────────────────────

def test_toda_seed_classifica_no_proprio_funil():
    """O rodízio só equilibra se o classificador concordar com as seeds.

    Quatro discordavam: "roteiro para reels", "automatizar redes sociais com
    ia" e "calendario editorial redes sociais" caíam em /sistema, e "gerar
    leads com inteligencia artificial" caía em /whatsapp porque "lead" estava
    na lista dele. Além de desequilibrar a semana, isso punha o CTA errado no
    rodapé do artigo.
    """
    erradas = [(funil, seed, funil_de(seed))
               for funil, seeds in research.SEEDS_POR_FUNIL.items()
               for seed in seeds if funil_de(seed) != funil]
    assert erradas == []


# ── o filtro de repetição que já existia ─────────────────────────────────

def test_dedupe_derruba_o_mesmo_assunto_dito_de_outro_jeito():
    keywords = [_kw("resposta automatica whatsapp"), _kw("respostas automaticas whatsapp")]
    assert len(research.descartar_repetidas(keywords, [])) == 1


def test_dedupe_respeita_o_que_o_blog_ja_cobre():
    keywords = [_kw("como colocar mensagem automatica no whatsapp")]
    ja = ["Como colocar mensagem automática no WhatsApp em 2026"]
    assert research.descartar_repetidas(keywords, ja) == []


@pytest.mark.parametrize("a,b", [
    ("bot para whatsapp", "crm integrado ao whatsapp"),
    ("whatsapp business api preço", "lista de transmissão whatsapp business"),
])
def test_dedupe_nao_confunde_pautas_de_fato_diferentes(a, b):
    """Por que o dedupe sozinho não resolvia a monotonia: são pautas distintas."""
    assert len(research.descartar_repetidas([_kw(a), _kw(b)], [])) == 2
