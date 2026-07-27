"""
tests/goals/test_fila_de_pautas.py

2026-07-26 — a fila que dá continuidade à esteira de conteúdo.

O research semanal já levantava 21 pautas cruzando notícia com volume de busca,
mas elas viravam um markdown e um ticket de texto. No dia seguinte, nada no
sistema sabia responder "o que a gente escreve hoje?" — e sem essa resposta não
existe rotina diária nem métrica de funil.

Run:
    pytest tests/goals/test_fila_de_pautas.py -v
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import pauta_fila as fila  # noqa: E402


@pytest.fixture
def banco(monkeypatch, tmp_path):
    monkeypatch.setattr(fila, "DB_PATH", tmp_path / "evonexus.db")
    return fila


def _pauta(prioridade: int, dia: date, keyword: str = "chatbot whatsapp") -> dict:
    return {
        "prioridade": prioridade,
        "keyword": keyword,
        "volume": 1300,
        "kd": 21.5,
        "data": dia.isoformat(),
        "publish_at": f"{dia.isoformat()}T12:00:00Z",
    }


# ── o ciclo semanal ──────────────────────────────────────────────────────

def test_ciclo_ancora_na_segunda_da_semana(banco):
    """Duas execuções do research na mesma semana caem no mesmo ciclo."""
    segunda = date(2026, 7, 27)
    for offset in range(7):
        assert banco.ciclo_de(segunda + timedelta(days=offset)) == "2026-07-27"


def test_grava_o_ciclo_inteiro(banco):
    inicio = date(2026, 7, 27)
    pautas = [_pauta(i + 1, inicio + timedelta(days=i // 3)) for i in range(21)]
    assert banco.gravar_ciclo(pautas)["gravadas"] == 21
    assert len(banco.listar(limite=500)) == 21


def test_rodar_o_research_de_novo_atualiza_em_vez_de_duplicar(banco):
    """Idempotência por (ciclo, prioridade) — senão a fila dobra a cada run."""
    dia = date(2026, 7, 27)
    banco.gravar_ciclo([_pauta(1, dia, "keyword antiga")])
    banco.gravar_ciclo([_pauta(1, dia, "keyword nova")])
    todas = banco.listar()
    assert len(todas) == 1
    assert todas[0]["keyword"] == "keyword nova"


def test_pauta_publicada_nunca_e_sobrescrita(banco):
    """O research não pode apagar trabalho que já foi ao ar."""
    dia = date(2026, 7, 27)
    banco.gravar_ciclo([_pauta(1, dia, "a que foi publicada")])
    pid = banco.listar()[0]["id"]
    banco.mover(pid, "publicada", ghost_url="https://blog.local/artigo/")

    resultado = banco.gravar_ciclo([_pauta(1, dia, "tentativa de sobrescrever")])
    assert resultado["preservadas"] == 1
    sobrevivente = banco.listar()[0]
    assert sobrevivente["keyword"] == "a que foi publicada"
    assert sobrevivente["ghost_url"] == "https://blog.local/artigo/"


def test_pauta_escrita_tambem_e_preservada(banco):
    """Rascunho no Ghost é trabalho feito; regravar perderia o vínculo."""
    dia = date(2026, 7, 27)
    banco.gravar_ciclo([_pauta(1, dia)])
    banco.mover(banco.listar()[0]["id"], "escrita", ghost_post_id="abc123")
    assert banco.gravar_ciclo([_pauta(1, dia, "outra")])["preservadas"] == 1
    assert banco.listar()[0]["ghost_post_id"] == "abc123"


def test_pauta_escrita_nao_apaga_o_slot_de_outro_dia(banco):
    """O dia 27/07/2026 amanheceu sem post por causa disto.

    A pauta #1 do ciclo estava `escrita` no slot das 18h do dia 26. Na rodada
    seguinte, a pauta que ocuparia a prioridade 1 — o post das 09h do dia 27 —
    foi tratada como "já existe" e descartada. Preservar trabalho feito não
    pode custar um slot vazio no calendário.
    """
    ontem, hoje = date(2026, 7, 26), date(2026, 7, 27)
    banco.gravar_ciclo([{**_pauta(1, ontem, "a que ja virou rascunho"),
                         "publish_at": f"{ontem.isoformat()}T21:00:00Z"}])
    banco.mover(banco.listar()[0]["id"], "escrita", ghost_post_id="abc123")

    novas = [{**_pauta(i + 1, hoje, f"pauta {i}"),
              "publish_at": f"{hoje.isoformat()}T{h}:00:00Z"}
             for i, h in enumerate(("12", "16", "21"))]
    assert banco.gravar_ciclo(novas)["gravadas"] == 3

    do_dia = banco.listar(limite=50)
    slots = sorted(p["publish_at"] for p in do_dia if p["data_alvo"] == hoje.isoformat())
    assert slots == [f"{hoje.isoformat()}T{h}:00:00Z" for h in ("12", "16", "21")]
    # E o rascunho de ontem segue intocado, com seu vínculo no Ghost.
    assert [p for p in do_dia if p["data_alvo"] == ontem.isoformat()][0]["ghost_post_id"] == "abc123"


def test_pauta_sem_keyword_ou_data_e_ignorada(banco):
    """Pauta incompleta não entra na fila fingindo que dá para escrever."""
    dia = date(2026, 7, 27)
    ruins = [
        {"prioridade": 1, "keyword": "", "data": dia.isoformat(), "publish_at": "x"},
        {"prioridade": 2, "keyword": "ok", "publish_at": "x"},
    ]
    assert banco.gravar_ciclo(ruins)["gravadas"] == 0


# ── o que a rotina diária consome ────────────────────────────────────────

def test_do_dia_traz_so_o_aprovado_na_ordem_de_prioridade(banco):
    dia = date(2026, 7, 27)
    banco.gravar_ciclo([_pauta(3, dia, "terceira"), _pauta(1, dia, "primeira"),
                        _pauta(2, dia, "segunda")])
    assert banco.do_dia(dia) == []  # nada aprovado ainda

    banco.aprovar_ciclo("2026-07-27")
    assert [p["keyword"] for p in banco.do_dia(dia)] == ["primeira", "segunda", "terceira"]


def test_do_dia_nao_vaza_pauta_de_outro_dia(banco):
    hoje, amanha = date(2026, 7, 27), date(2026, 7, 28)
    banco.gravar_ciclo([_pauta(1, hoje, "de hoje"), _pauta(2, amanha, "de amanha")])
    banco.aprovar_ciclo("2026-07-27")
    assert [p["keyword"] for p in banco.do_dia(hoje)] == ["de hoje"]


def test_aprovacao_e_em_lote(banco):
    """A decisão do humano é sobre a semana, não sobre 21 itens um a um."""
    inicio = date(2026, 7, 27)
    banco.gravar_ciclo([_pauta(i + 1, inicio + timedelta(days=i // 3)) for i in range(21)])
    assert banco.aprovar_ciclo("2026-07-27") == 21
    # Segunda chamada não reaprova nada — só 'proposta' é elegível.
    assert banco.aprovar_ciclo("2026-07-27") == 0


# ── estados ──────────────────────────────────────────────────────────────

def test_mover_anexa_o_que_o_estado_produziu(banco):
    banco.gravar_ciclo([_pauta(1, date(2026, 7, 27))])
    pid = banco.listar()[0]["id"]
    banco.mover(pid, "escrita", ghost_post_id="post-1", titulo="Título gerado")
    escrita = banco.listar()[0]
    assert escrita["status"] == "escrita"
    assert escrita["ghost_post_id"] == "post-1"
    assert escrita["titulo"] == "Título gerado"

    banco.mover(pid, "publicada", ghost_url="https://blog.local/x/")
    publicada = banco.listar()[0]
    # COALESCE preserva o que já estava — publicar não pode apagar o post_id.
    assert publicada["ghost_post_id"] == "post-1"
    assert publicada["ghost_url"] == "https://blog.local/x/"


def test_status_invalido_e_recusado(banco):
    banco.gravar_ciclo([_pauta(1, date(2026, 7, 27))])
    with pytest.raises(ValueError):
        banco.mover(banco.listar()[0]["id"], "quase-publicada")


def test_mover_pauta_inexistente_devolve_false(banco):
    assert banco.mover(9999, "publicada") is False


# ── vencimento ───────────────────────────────────────────────────────────

def test_pauta_atrasada_e_descartada(banco):
    """Gancho de notícia tem validade de dias; publicar depois é assunto velho."""
    hoje = date(2026, 7, 30)
    velha = hoje - timedelta(days=5)
    banco.gravar_ciclo([_pauta(1, velha, "assunto vencido")])
    banco.aprovar_ciclo(banco.ciclo_de(velha))

    assert banco.vencer_atrasadas(hoje=hoje) == 1
    descartada = banco.listar()[0]
    assert descartada["status"] == "descartada"
    assert "venceu" in descartada["motivo"]


def test_pauta_de_hoje_nao_vence(banco):
    hoje = date(2026, 7, 30)
    banco.gravar_ciclo([_pauta(1, hoje)])
    banco.aprovar_ciclo(banco.ciclo_de(hoje))
    assert banco.vencer_atrasadas(hoje=hoje) == 0


def test_pauta_publicada_nao_vence(banco):
    """Já foi ao ar — não há o que descartar."""
    hoje = date(2026, 7, 30)
    banco.gravar_ciclo([_pauta(1, hoje - timedelta(days=10))])
    banco.mover(banco.listar()[0]["id"], "publicada")
    assert banco.vencer_atrasadas(hoje=hoje) == 0
    assert banco.listar()[0]["status"] == "publicada"


# ── o funil que vai para o painel ────────────────────────────────────────

def test_resumo_conta_o_funil(banco):
    inicio = date.today()
    banco.gravar_ciclo([_pauta(i + 1, inicio) for i in range(4)])
    ids = [p["id"] for p in banco.listar()]
    banco.mover(ids[0], "publicada")
    banco.mover(ids[1], "escrita")
    banco.mover(ids[2], "descartada")

    r = banco.resumo()
    assert r["por_status"]["publicada"] == 1
    assert r["por_status"]["escrita"] == 1
    assert r["por_status"]["descartada"] == 1
    assert r["por_status"]["proposta"] == 1


def test_taxa_conta_so_o_que_ja_foi_decidido(banco):
    """Incluir pauta ainda na fila derrubaria a taxa só porque a semana começou."""
    hoje = date.today()
    banco.gravar_ciclo([_pauta(i + 1, hoje) for i in range(10)])
    ids = [p["id"] for p in banco.listar()]
    banco.mover(ids[0], "publicada")
    banco.mover(ids[1], "publicada")
    banco.mover(ids[2], "publicada")
    banco.mover(ids[3], "descartada")
    # 3 publicadas de 4 decididas = 0.75, apesar de 6 ainda na fila.
    assert banco.resumo()["taxa_aproveitamento"] == 0.75


def test_taxa_e_nula_sem_nada_decidido(banco):
    banco.gravar_ciclo([_pauta(1, date.today())])
    assert banco.resumo()["taxa_aproveitamento"] is None


def test_resumo_mostra_as_proximas_a_sair(banco):
    # Datas ancoradas no meio de uma semana: usar `hoje` real quebrava aos
    # domingos, quando "amanhã" já é o ciclo seguinte e `aprovar_ciclo` do
    # ciclo de hoje não o alcança.
    hoje = date.today()
    dias = [hoje, hoje + timedelta(days=1)]
    banco.gravar_ciclo([_pauta(1, dias[0], "primeira"), _pauta(2, dias[1], "segunda")])
    for dia in dias:
        banco.aprovar_ciclo(banco.ciclo_de(dia))
    assert [p["keyword"] for p in banco.resumo()["proximas"]] == ["primeira", "segunda"]


def test_resumo_de_fila_vazia_nao_quebra(banco):
    r = banco.resumo()
    assert r["por_status"]["proposta"] == 0
    assert r["proximas"] == []
    assert r["ciclo_atual"]["total"] == 0


# ── filtros da listagem ──────────────────────────────────────────────────

def test_listar_filtra_por_ciclo_e_status(banco):
    a, b = date(2026, 7, 27), date(2026, 8, 3)
    banco.gravar_ciclo([_pauta(1, a, "ciclo a")])
    banco.gravar_ciclo([_pauta(1, b, "ciclo b")])
    assert [p["keyword"] for p in banco.listar(ciclo="2026-07-27")] == ["ciclo a"]

    banco.aprovar_ciclo("2026-08-03")
    assert [p["keyword"] for p in banco.listar(status="aprovada")] == ["ciclo b"]


def test_limite_da_listagem_e_sanitizado(banco):
    banco.gravar_ciclo([_pauta(i + 1, date(2026, 7, 27)) for i in range(5)])
    assert len(banco.listar(limite=0)) == 1      # mínimo 1, nunca zero ou negativo
    assert len(banco.listar(limite=99999)) == 5  # teto não estoura a consulta


# ── cache de keywords: não pagar duas vezes pela mesma pergunta ──────────
# Pedido do Felipe: cada chamada ao DataForSEO custa, e uma rodada de research
# consome nove seeds. Volume de busca é média de 12 meses — reconsultar a
# mesma seed toda semana é dinheiro queimado para receber o mesmo número.

def _linhas(*termos: str) -> list[dict]:
    return [{"kw": t, "vol": 500, "kd": 20, "cpc": 1.5} for t in termos]


def test_seed_nova_precisa_ir_a_api(banco):
    conhecidas, faltando = banco.keywords_em_cache(["chatbot whatsapp"])
    assert conhecidas == {}
    assert faltando == ["chatbot whatsapp"]


def test_seed_ja_consultada_volta_do_cache(banco):
    banco.guardar_keywords("chatbot whatsapp", _linhas("chatbot whatsapp para empresas"))
    conhecidas, faltando = banco.keywords_em_cache(["chatbot whatsapp"])
    assert faltando == []
    assert "chatbot whatsapp para empresas" in conhecidas


def test_so_as_seeds_faltantes_sao_cobradas(banco):
    """Uma rodada que reusa três de nove seeds paga por seis, não por nove."""
    banco.guardar_keywords("seed-a", _linhas("kw a"))
    banco.guardar_keywords("seed-b", _linhas("kw b"))
    conhecidas, faltando = banco.keywords_em_cache(["seed-a", "seed-b", "seed-c"])
    assert faltando == ["seed-c"]
    assert set(conhecidas) == {"kw a", "kw b"}


def test_cache_vencido_e_reconsultado(banco, monkeypatch):
    from datetime import datetime, timedelta, timezone

    banco.guardar_keywords("seed-velha", _linhas("kw velha"))
    conn = banco.conectar()
    antigo = (datetime.now(timezone.utc) - timedelta(days=banco.DIAS_DE_CACHE + 1)).isoformat()
    conn.execute("UPDATE keywords_cache SET consultado_em=?", (antigo,))
    conn.commit()
    conn.close()

    _, faltando = banco.keywords_em_cache(["seed-velha"])
    assert faltando == ["seed-velha"]


def test_reconsultar_atualiza_em_vez_de_duplicar(banco):
    banco.guardar_keywords("seed", _linhas("antiga"))
    banco.guardar_keywords("seed", _linhas("nova"))
    conhecidas, _ = banco.keywords_em_cache(["seed"])
    assert set(conhecidas) == {"nova"}


def test_resultado_vazio_nao_e_cacheado(banco):
    """Cachear vazio mascararia uma falha da API como resposta legítima —
    e a seed ficaria 30 dias sem ser consultada de novo."""
    banco.guardar_keywords("seed", [])
    assert banco.keywords_em_cache(["seed"])[1] == ["seed"]


def test_cache_corrompido_manda_reconsultar(banco):
    banco.guardar_keywords("seed", _linhas("kw"))
    conn = banco.conectar()
    conn.execute("UPDATE keywords_cache SET linhas='{isso nao e json'")
    conn.commit()
    conn.close()
    assert banco.keywords_em_cache(["seed"])[1] == ["seed"]


def test_locales_diferentes_nao_se_misturam(banco):
    banco.guardar_keywords("seed", _linhas("kw br"), locale="2076/pt")
    assert banco.keywords_em_cache(["seed"], locale="2840/en")[1] == ["seed"]
