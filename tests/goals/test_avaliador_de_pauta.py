"""
tests/goals/test_avaliador_de_pauta.py

2026-07-26 — o julgamento de público que o regex não consegue fazer.

O filtro por expressão regular separa lixo óbvio (curso técnico, vaga, caixa de
plástico), mas deixava passar `mercado pago api` — negócio de outra empresa — e
`como postar story no instagram pelo pc` — consumidor final, não dono de
empresa. As duas têm termo do domínio e intenção comercial; o que as reprova é
QUEM busca, e isso exige conhecer o negócio.

Run:
    pytest tests/goals/test_avaliador_de_pauta.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import avaliador_de_pauta as juiz  # noqa: E402


def _cands(*termos: str) -> list[dict]:
    return [{"kw": t, "vol": 500, "kd": 20} for t in termos]


def _resposta(notas: dict[int, int]) -> str:
    return json.dumps({"notas": [{"n": n, "nota": v, "porque": "motivo"}
                                 for n, v in notas.items()]})


# ── o perfil precisa refletir o negócio real ─────────────────────────────

def test_perfil_cobre_as_tres_ofertas():
    """Sem as três, o modelo julga contra um negócio que não existe."""
    for funil in ("whatsapp", "socialjobs", "sistema"):
        assert f"sistemabritto.com.br/{funil}" in juiz.PERFIL


def test_perfil_diz_quem_NAO_compra():
    """É o que separa 'dono de empresa' de 'estudante' e 'candidato a vaga' —
    exatamente o público que passava pelo regex."""
    # Normaliza a quebra de linha: o texto é escrito em parágrafo e a frase
    # atravessa linhas, mas o que importa é o modelo lê-la inteira.
    perfil = " ".join(juiz.PERFIL.split())
    for excluido in ("NÃO é desenvolvedor", "NÃO é estudante",
                     "NÃO é quem procura emprego", "NÃO é consumidor final"):
        assert excluido in perfil


def test_criterios_ancoram_a_nota_em_exemplos():
    """Escala sem exemplo vira nota arbitrária entre execuções."""
    for ancora in ("10 —", "7 —", "4 —", "0 —"):
        assert ancora in juiz.CRITERIOS


def test_prompt_numera_as_keywords():
    prompt = juiz._montar_prompt(["primeira", "segunda"])
    assert "1. primeira" in prompt and "2. segunda" in prompt
    assert "APENAS um JSON" in prompt


# ── o corte ──────────────────────────────────────────────────────────────

def test_corta_o_que_ficou_abaixo_da_nota(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: _resposta({1: 9, 2: 2, 3: 7}))
    sobraram = juiz.avaliar(_cands("chatbot whatsapp", "mercado pago api", "gerar leads"))
    assert [c["kw"] for c in sobraram] == ["chatbot whatsapp", "gerar leads"]


def test_ordena_por_relevancia_e_nao_por_volume(monkeypatch):
    """Pauta nota 9 com 200 buscas vale mais que nota 6 com 5000: a segunda
    traz visita que não compra."""
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: _resposta({1: 6, 2: 9}))
    candidatas = [{"kw": "muito volume", "vol": 5000, "kd": 10},
                  {"kw": "muito relevante", "vol": 200, "kd": 10}]
    assert [c["kw"] for c in juiz.avaliar(candidatas)] == ["muito relevante", "muito volume"]


def test_volume_desempata_notas_iguais(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: _resposta({1: 8, 2: 8}))
    candidatas = [{"kw": "menos busca", "vol": 100, "kd": 10},
                  {"kw": "mais busca", "vol": 3000, "kd": 10}]
    assert [c["kw"] for c in juiz.avaliar(candidatas)][0] == "mais busca"


def test_nota_exatamente_no_corte_passa(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: _resposta({1: juiz.NOTA_MINIMA}))
    assert len(juiz.avaliar(_cands("na linha"))) == 1


def test_nota_minima_e_ajustavel(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: _resposta({1: 7}))
    assert juiz.avaliar(_cands("boa"), nota_minima=9) == []


# ── falhar sem derrubar a semana ─────────────────────────────────────────

def test_modelo_mudo_devolve_tudo(monkeypatch):
    """Perder a semana porque um julgamento opcional falhou seria pior que
    publicar uma pauta mediana."""
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", lambda p, timeout=0: "")
    entrada = _cands("a", "b", "c")
    assert juiz.avaliar(entrada) == entrada


def test_json_quebrado_devolve_tudo(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: "não sou json")
    assert len(juiz.avaliar(_cands("a", "b"))) == 2


def test_keyword_sem_nota_nao_some(monkeypatch):
    """Omissão do modelo não é reprovação — sumir por silêncio esvaziaria a
    semana sem ninguém entender por quê."""
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: _resposta({1: 9}))
    sobraram = juiz.avaliar(_cands("avaliada", "esquecida"))
    assert {c["kw"] for c in sobraram} == {"avaliada", "esquecida"}
    assert next(c for c in sobraram if c["kw"] == "esquecida")["porque"] == "não avaliada"


def test_indice_fora_da_lista_e_ignorado(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: _resposta({1: 9, 99: 10}))
    assert len(juiz.avaliar(_cands("única"))) == 1


def test_nota_nao_numerica_nao_quebra(monkeypatch):
    monkeypatch.setattr(
        "ghost_publisher._pedir_ao_modelo",
        lambda p, timeout=0: json.dumps({"notas": [{"n": 1, "nota": "dez"}]}))
    assert len(juiz.avaliar(_cands("uma"))) == 1  # cai no fallback de "não avaliada"


def test_cerca_de_codigo_e_tolerada(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: f"```json\n{_resposta({1: 2})}\n```")
    assert juiz.avaliar(_cands("ruim")) == []


def test_lista_vazia_nao_chama_o_modelo(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("não deveria chamar o modelo para lista vazia")

    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", _explode)
    assert juiz.avaliar([]) == []


def test_avalia_em_lotes(monkeypatch):
    """Lote grande faz o modelo encurtar a lista e devolver menos notas."""
    chamadas = []

    def _responde(prompt, timeout=0):
        chamadas.append(prompt)
        # devolve nota alta para todas as posições do lote
        n = prompt.count("\n1. ") and len([l for l in prompt.splitlines()
                                           if l.strip() and l.split(".")[0].strip().isdigit()])
        return _resposta({i: 9 for i in range(1, juiz.POR_LOTE + 1)})

    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", _responde)
    juiz.avaliar(_cands(*[f"kw {i}" for i in range(juiz.POR_LOTE + 5)]))
    assert len(chamadas) == 2, "deveria quebrar em dois lotes"
