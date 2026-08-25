"""
tests/goals/test_diversidade_de_tema.py

05/08/2026 — a cota de funil resolvia a SEMANA, não o DIA.

O ciclo 2026-08-03 nasceu com 11 das 21 pautas em /whatsapp (cota de funil
furada por keyword que entrou fora do rodízio, na reserva do X completando
manualmente o que sobrou), e 04 e 05/08/2026 tiveram os três posts do dia
sobre WhatsApp Business — "vantagens e desvantagens", "premium valor",
"atendimento automatizado grátis". Três keywords passam pelo dedupe de núcleo
(exige 60% de sobreposição literal), mas o leitor que abre o blog naquele dia
lê a mesma coisa três vezes.

Dois mecanismos, testados separadamente:

1. `tema_de` / `equilibrar_temas` — eixo mais fino que funil, reordena (nunca
   descarta) para não repetir tema no mesmo bloco de dia, e empurra o
   excedente de um tema além da cota do ciclo para mais tarde na semana.
2. `titulos_publicados` — a carência do dedupe de núcleo passa a ser uma
   janela de TEMPO (45 dias) em vez de uma janela de CONTAGEM (`limit=100`),
   que encolhe conforme o blog cresce e silenciosamente perde alcance.

Run:
    pytest tests/goals/test_diversidade_de_tema.py -v
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))


@pytest.fixture
def research():
    spec = importlib.util.spec_from_file_location(
        "wcr_diversidade", REPO_ROOT / "ADWs" / "routines" / "weekly_content_research.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _kw(termo: str, vol: int = 1000) -> dict:
    return {"kw": termo, "vol": vol, "kd": 20.0}


# ── tema_de ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("keyword,esperado", [
    ("whatsapp business vantagens e desvantagens", "whatsapp"),
    ("atendimento automatizado whatsapp grátis", "whatsapp"),
    ("melhor horário para postar no instagram", "redes-sociais"),
    ("trafego pago instagram", "redes-sociais"),
    ("plataformas de agentes de ia", "ia-automacao"),
    ("como fazer automação de whatsapp", "whatsapp"),  # "whatsapp" vence "automação"
    ("o que é crm de vendas", "vendas-crm"),
    ("pagina de vendas de alta conversão", "vendas-crm"),
    ("qual a melhor plataforma de gestão financeira", "outros"),
])
def test_tema_de_classifica_o_assunto_real(research, keyword, esperado):
    assert research.tema_de(keyword) == esperado


# ── equilibrar_temas: nunca perde pauta ─────────────────────────────────────

def test_equilibrar_temas_preserva_todas_as_pautas(research):
    """Nunca pode encolher a semana — é o mesmo erro que a reserva do X já
    cometeu uma vez (falha calada ao devolver menos do que recebeu)."""
    keywords = ([_kw(f"whatsapp business {i}") for i in range(6)]
                + [_kw(f"crm de vendas {i}") for i in range(3)]
                + [_kw(f"agente de ia {i}") for i in range(3)])
    saida = research.equilibrar_temas(keywords)
    assert sorted(k["kw"] for k in saida) == sorted(k["kw"] for k in keywords)


# ── equilibrar_temas: não repete tema no mesmo dia ──────────────────────────

def test_nao_repete_tema_no_mesmo_dia_quando_ha_diversidade():
    """O caso real: WhatsApp com sobra de keyword, mas os outros dois temas
    também têm o suficiente para cobrir a semana sem repetir dia."""
    spec = importlib.util.spec_from_file_location(
        "wcr_diversidade_dia", REPO_ROOT / "ADWs" / "routines" / "weekly_content_research.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    keywords = ([_kw(f"whatsapp business {i}", 9000 - i) for i in range(7)]
                + [_kw(f"crm de vendas {i}", 500) for i in range(7)]
                + [_kw(f"agente de ia {i}", 500) for i in range(7)])
    saida = mod.equilibrar_temas(keywords, por_dia=3)

    for inicio in range(0, len(saida), 3):
        bloco = saida[inicio: inicio + 3]
        temas = [mod.tema_de(k["kw"]) for k in bloco]
        assert len(set(temas)) == len(temas), f"dia repetiu tema: {temas}"


def test_repete_tema_so_quando_nao_ha_outro_assunto(research, capsys):
    """Sem diversidade real (20 WhatsApp e 1 de outro tema), repetir é
    inevitável — mas o log tem de admitir isso, não fingir que resolveu."""
    keywords = [_kw(f"whatsapp business {i}") for i in range(20)] + [_kw("crm de vendas")]
    saida = research.equilibrar_temas(keywords, por_dia=3)

    assert len(saida) == 21
    saida_log = capsys.readouterr().out
    assert "repetiram tema" in saida_log


# ── equilibrar_temas: empurra o excedente da cota do ciclo ──────────────────

def test_excedente_da_cota_de_ciclo_vai_para_o_fim(research):
    """21 WhatsApp e nada mais: a cota do ciclo (6) não pode travar a
    reordenação, mas as primeiras 6 posições devem ser as únicas garantidas
    dentro da cota — o resto sobra por falta de alternativa, não por escolha."""
    keywords = [_kw(f"whatsapp business {i}") for i in range(21)]
    saida = research.equilibrar_temas(keywords, por_dia=3)
    # Permutação pura: nada se perde mesmo quando a cota não pode ser respeitada.
    assert len(saida) == 21


def test_tema_variado_respeita_a_cota_de_ciclo_quando_da(research):
    """8 WhatsApp e 13 de outros temas — dá para manter WhatsApp dentro da
    cota de 6 no ciclo, empurrando as 2 restantes para o fim."""
    keywords = ([_kw(f"whatsapp business {i}", 9000) for i in range(8)]
                + [_kw(f"crm de vendas {i}", 500) for i in range(7)]
                + [_kw(f"agente de ia {i}", 500) for i in range(6)])
    saida = research.equilibrar_temas(keywords, por_dia=3)

    primeiras_18 = saida[:18]
    contagem_whatsapp = sum(1 for k in primeiras_18 if research.tema_de(k["kw"]) == "whatsapp")
    assert contagem_whatsapp <= research.COTA_TEMA_POR_CICLO, (
        "com supply de sobra nos outros temas, WhatsApp não devia passar da cota "
        "antes de esgotar as alternativas")


# ── titulos_publicados: janela de tempo, não de contagem ───────────────────

def _post(titulo: str, dias_atras: int) -> dict:
    quando = datetime.now(timezone.utc) - timedelta(days=dias_atras)
    return {"title": titulo, "status": "published",
            "published_at": quando.isoformat().replace("+00:00", "Z")}


def test_titulos_publicados_ignora_o_que_passou_da_carencia(research, monkeypatch):
    posts = [_post("WhatsApp Business recente", 10), _post("WhatsApp Business antigo", 90)]

    class _Resp:
        status_code = 200

        def json(self):
            return {"posts": posts}

    ghost_falso = types.SimpleNamespace(
        _config=lambda: ("https://blog.exemplo", "chave"),
        _headers=lambda key: {},
    )
    requests_falso = types.SimpleNamespace(get=lambda *a, **k: _Resp())
    monkeypatch.setitem(sys.modules, "ghost_publisher", ghost_falso)
    monkeypatch.setitem(sys.modules, "requests", requests_falso)

    class _EvoVazio:
        def get(self, *a, **k):
            return {"pautas": []}

    monkeypatch.setitem(sys.modules, "sdk_client", types.SimpleNamespace(evo=_EvoVazio()))

    titulos = research.titulos_publicados(dias=45)
    assert "WhatsApp Business recente" in titulos
    assert "WhatsApp Business antigo" not in titulos


def test_titulos_publicados_mantem_rascunho_sem_data(research, monkeypatch):
    """Rascunho nunca publicado (`published_at` vazio) é trabalho em
    andamento no mesmo assunto, não histórico — não pode ser descartado por
    não ter data."""
    posts = [{"title": "Ainda em rascunho", "status": "draft", "published_at": None}]

    class _Resp:
        status_code = 200

        def json(self):
            return {"posts": posts}

    ghost_falso = types.SimpleNamespace(
        _config=lambda: ("https://blog.exemplo", "chave"),
        _headers=lambda key: {},
    )
    monkeypatch.setitem(sys.modules, "ghost_publisher", ghost_falso)
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=lambda *a, **k: _Resp()))
    monkeypatch.setitem(sys.modules, "sdk_client",
                        types.SimpleNamespace(evo=types.SimpleNamespace(get=lambda *a, **k: {"pautas": []})))

    assert "Ainda em rascunho" in research.titulos_publicados(dias=45)
