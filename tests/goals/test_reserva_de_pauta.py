"""
tests/goals/test_reserva_de_pauta.py

A reserva de trending, que fecha os 21 slots quando o SEO não dá conta.

Dois defeitos reais, descobertos em 04-05/08/2026:

1. Ela morria calada. `XAI_API_KEY` não existe no .env da VPS (HTTP 401 na
   api.x.ai). `pesquisar_noticias` sobrevive pelo fallback de Perplexity;
   esta função não tinha nenhum — e o ciclo 2026-08-03 nasceu com 8 pautas
   em vez de 21, com dois dias sem artigo.

2. Ela não passava pelo avaliador de ICP. Com o Grok isso passava batido;
   quando caiu no Perplexity, vieram 13 descrições de sessão de evento com
   volume 0 — "innovation meeting br 2026 inteligencia artificial marketing
   digital pequenas empresas" (11 palavras). As 12 foram descartadas na mão.

Run:
    pytest tests/goals/test_reserva_de_pauta.py -v
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dashboard" / "backend"))


@pytest.fixture
def research(monkeypatch):
    """O módulo do research com as dependências de rede neutralizadas."""
    spec = importlib.util.spec_from_file_location(
        "wcr_reserva", ROOT / "ADWs" / "routines" / "weekly_content_research.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Sem isto o filtro consultaria o Ghost para saber o que já foi publicado.
    monkeypatch.setattr(mod, "titulos_publicados", lambda: [])
    return mod


def _resposta(keywords):
    """Uma resposta do provider no formato que a função espera."""
    import json as _json
    return _json.dumps({"pautas": [{"keyword": k, "porque": "gancho"} for k in keywords]})


@pytest.fixture
def com_provider(research, monkeypatch):
    """Injeta a resposta do provider sem tocar em rede.

    Devolve uma função `preparar(keywords)` que arma o retorno.
    """
    def preparar(keywords, *, xai_ok=False):
        estado = {"chamadas": []}

        class _Resp:
            def __init__(self, code, body=""):
                self.status_code, self.text = code, body

            def json(self):
                if xai_ok:
                    return {"output": [{"type": "message", "content": [
                        {"type": "output_text", "text": _resposta(keywords)}]}]}
                return {"choices": [{"message": {"content": _resposta(keywords)}}]}

        def post(url, **kwargs):
            estado["chamadas"].append(url)
            if "x.ai" in url:
                return _Resp(200 if xai_ok else 403, "forbidden")
            return _Resp(200)

        falso = types.SimpleNamespace(post=post)
        monkeypatch.setitem(sys.modules, "requests", falso)
        return estado

    monkeypatch.setenv("XAI_API_KEY", "chave-de-teste")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "chave-perplexity")
    return preparar


# ── 1. o fallback ────────────────────────────────────────────────────────

def test_cai_no_perplexity_quando_o_xai_recusa(research, com_provider):
    """O caso real: x.ai 403 e a semana ficando pela metade."""
    estado = com_provider(["automatizar whatsapp business gratis"])
    achadas = research.pautas_do_x(3, [], "")

    assert any("x.ai" in u for u in estado["chamadas"]), "tinha de tentar o xAI primeiro"
    assert any("perplexity" in u for u in estado["chamadas"]), "tinha de cair no Perplexity"
    assert [a["kw"] for a in achadas] == ["automatizar whatsapp business gratis"]


def test_sem_nenhuma_chave_devolve_vazio_e_avisa(research, monkeypatch, capsys):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    assert research.pautas_do_x(5, [], "") == []
    assert "sem reserva" in capsys.readouterr().out


def test_nao_chama_ninguem_quando_nao_falta_pauta(research, monkeypatch):
    """A semana já fechou pelo SEO — gastar uma chamada aqui é desperdício."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "x")
    assert research.pautas_do_x(0, [], "") == []
    assert research.pautas_do_x(-1, [], "") == []


# ── 2. termo de busca tem tamanho de termo de busca ──────────────────────

def test_descarta_nome_de_sessao_de_evento(research, com_provider, capsys):
    """As keywords reais que o Perplexity devolveu em 04/08/2026."""
    com_provider([
        "innovation meeting br 2026 inteligencia artificial marketing digital pequenas empresas",
        "forum ecommerce brasil 2026 tendencias de ia para lojas virtuais",
        "uso de ia por pmes no brasil dados recentes 2025 2026",
        "automatizar whatsapp business gratis",          # esta presta
    ])
    achadas = research.pautas_do_x(4, [], "")

    assert [a["kw"] for a in achadas] == ["automatizar whatsapp business gratis"]
    assert "não ser termo de busca" in capsys.readouterr().out


def test_o_teto_de_palavras_cabe_a_cauda_longa_comercial(research, com_provider):
    """Seis palavras não pode cortar a pauta boa junto com a ruim."""
    boas = [
        "como automatizar whatsapp business gratis",       # 5
        "crm integrado ao whatsapp para empresas",         # 6
        # 7: as palavras funcionais contam, e esta é pauta legítima de trending
        # (o caso que test_esteira_de_conteudo.py::test_x_completa_a_semana usa)
        "meta lanca agente de ia no whatsapp",
    ]
    com_provider(boas)
    assert len(research.pautas_do_x(3, [], "")) == 3
    # 7 é o corte medido: a maior pauta boa tem 7 palavras e a menor descrição
    # de evento tem 8.
    assert research.PALAVRAS_MAX_NA_RESERVA == 7


# ── 3. o avaliador de ICP ────────────────────────────────────────────────

def test_reserva_passa_pelo_avaliador(research, com_provider, monkeypatch):
    """O julgamento de público que só existia para o funil de SEO."""
    vistos = {}

    def avaliar_falso(candidatas, **kwargs):
        vistos["kws"] = [c["kw"] for c in candidatas]
        return [c for c in candidatas if "whatsapp" in c["kw"]]

    monkeypatch.setitem(sys.modules, "avaliador_de_pauta",
                        types.SimpleNamespace(avaliar=avaliar_falso))
    # "mercado pago api" é o exemplo real que o regex deixava passar e o
    # avaliador reprova: negócio de outra empresa, não do leitor.
    com_provider(["automatizar whatsapp gratis", "mercado pago api"])
    achadas = research.pautas_do_x(2, [], "")

    assert vistos["kws"] == ["automatizar whatsapp gratis", "mercado pago api"], \
        "as duas têm de chegar ao avaliador — quem julga público é ele, não o regex"
    assert [a["kw"] for a in achadas] == ["automatizar whatsapp gratis"]


def test_avaliador_indisponivel_nao_derruba_a_reserva(research, com_provider, monkeypatch):
    """Fail-open, igual ao funil de SEO: perder a semana porque um julgamento
    opcional falhou seria pior que uma pauta mediana."""
    def explode(*a, **k):
        raise RuntimeError("modelo fora do ar")

    monkeypatch.setitem(sys.modules, "avaliador_de_pauta",
                        types.SimpleNamespace(avaliar=explode))
    com_provider(["automatizar whatsapp gratis"])
    assert [a["kw"] for a in research.pautas_do_x(1, [], "")] == ["automatizar whatsapp gratis"]


def test_pede_com_folga_para_o_corte_nao_encurtar_a_semana(research, com_provider, monkeypatch):
    """Pedir exatamente o que falta e perder metade no julgamento deixaria a
    semana curta de novo — que é o problema que a reserva existe para resolver."""
    capturado = {}
    com_provider(["kw um", "kw dois"])
    import requests  # o falso injetado pelo fixture

    def post_espiao(url, **kwargs):
        corpo = kwargs.get("json") or {}
        texto = str(corpo.get("input") or corpo.get("messages") or "")
        capturado["prompt"] = texto
        class _R:
            status_code = 200
            text = ""
            def json(self_inner):
                return {"choices": [{"message": {"content": _resposta(["kw um"])}}]}
        return _R()

    monkeypatch.setattr(requests, "post", post_espiao)
    research.pautas_do_x(5, [], "")
    # 5 que faltam -> pede 10 (o dobro, limitado a +10)
    assert "Proponha 10 pautas" in capturado["prompt"]


def test_o_prompt_pede_termo_de_busca_e_nao_acontecimento(research):
    """Instrução no prompt não basta sozinha (por isso o filtro de palavras),
    mas tirar a instrução faria o modelo reincidir mais."""
    fonte = (ROOT / "ADWs" / "routines" / "weekly_content_research.py").read_text(encoding="utf-8")
    trecho = fonte.split("def pautas_do_x")[1].split("def montar_pautas")[0]
    assert "no máximo 7 palavras" in trecho
    assert "sem nome de evento" in trecho
