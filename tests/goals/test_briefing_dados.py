"""
tests/goals/test_briefing_dados.py

2026-07-27 — o briefing que navegava o workspace para montar uma lista.

`prod-good-morning` e `prod-end-of-day` são skills escritas para conversa,
rodando como cron. A matinal manda o agente ler CLAUDE.md, os três últimos
logs, o overview de cada projeto, consultar três integrações, gerar um HTML e
**perguntar ao usuário se ele quer entrar num projeto** — pergunta que às 07:00
ninguém responde. A do fim do dia manda coletar seis fontes antes de pensar,
uma delas sendo a conversa da sessão, que no cron não existe.

Juntas custavam US$ 11,89 acumulados, com 76% e 81% de acerto.

O que a coleta em Python resolve é a parte sem julgamento. Estes testes
guardam os detalhes que já saíram errados ao construí-la.

Run:
    pytest tests/goals/test_briefing_dados.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import briefing_dados as bd  # noqa: E402


class _Evo:
    def __init__(self, respostas: dict):
        self.respostas = respostas
        self.chamadas: list = []

    def get(self, rota, params=None):
        self.chamadas.append((rota, params))
        return self.respostas.get(rota, {})


@pytest.fixture
def evo(monkeypatch):
    dublê = _Evo({})
    monkeypatch.setattr(bd, "_evo", lambda: dublê)
    return dublê


# ── coleta do Nexus ──────────────────────────────────────────────────────

def test_gates_pendentes_saem_com_alvo(evo):
    evo.respostas["/api/approvals"] = {"approvals": [
        {"title": "Publicar em x: Artigo", "publish": {"target": "x"}},
    ]}
    g = bd.gates_pendentes()
    assert g == [{"titulo": "Publicar em x: Artigo", "alvo": "x", "criado": ""}]


def test_tickets_vem_por_prioridade(evo):
    evo.respostas["/api/tickets"] = {"tickets": [
        {"title": "baixa", "priority": "low"},
        {"title": "urgente", "priority": "urgent"},
        {"title": "media", "priority": "medium"},
    ]}
    assert [t["titulo"] for t in bd.tickets_abertos()] == ["urgente", "media", "baixa"]


def test_pauta_do_dia_usa_o_endpoint_que_filtra(evo):
    """`/api/pautas` ignora o parâmetro de dia e devolve a fila inteira.

    Listar as 24 pautas da semana esconde as três de hoje no meio do resto.
    """
    bd.pauta_do_dia()
    rotas = [c[0] for c in evo.chamadas]
    assert rotas and all(r == "/api/pautas/hoje" for r in rotas)


def test_pauta_do_dia_cobre_escrita_e_aprovada(evo):
    """Às 07:00 a esteira das 06:00 já rodou.

    O que ela escreveu está em `escrita` esperando o gate; pedir só o padrão
    da API mostraria a metade que já não exige nada de ninguém.
    """
    bd.pauta_do_dia()
    status = [c[1].get("status") for c in evo.chamadas]
    assert status == ["escrita", "aprovada"]


def test_api_fora_do_ar_nao_derruba_o_briefing(monkeypatch):
    def explode():
        raise RuntimeError("api fora")

    monkeypatch.setattr(bd, "_evo", explode)
    assert bd.gates_pendentes() == []
    assert bd.tickets_abertos() == []
    assert bd.pauta_do_dia() == []


def test_sem_token_do_todoist_devolve_vazio(monkeypatch):
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
    assert bd.tarefas_de_hoje() == []


# ── coleta do fim do dia ─────────────────────────────────────────────────

def test_rotinas_do_dia_le_o_campo_certo(monkeypatch, tmp_path):
    """O JSONL grava `run`; `log_name` é o nome do parâmetro do runner.

    A diferença fazia o dossiê listar seis rotinas chamadas "?".
    """
    logs = tmp_path / "ADWs" / "logs"
    logs.mkdir(parents=True)
    (logs / f"{bd._agora_brt().date().isoformat()}.jsonl").write_text(
        json.dumps({"run": "good-morning", "returncode": 0}) + "\n"
        + json.dumps({"run": "backup", "returncode": 1}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(bd, "_workspace", lambda: tmp_path)

    r = bd.rotinas_do_dia()
    assert [x["rotina"] for x in r] == ["good-morning", "backup"]
    assert [x["ok"] for x in r] == [True, False]


def test_linha_corrompida_nao_derruba_a_leitura(monkeypatch, tmp_path):
    logs = tmp_path / "ADWs" / "logs"
    logs.mkdir(parents=True)
    (logs / f"{bd._agora_brt().date().isoformat()}.jsonl").write_text(
        "{ isto não é json\n" + json.dumps({"run": "ok", "returncode": 0}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(bd, "_workspace", lambda: tmp_path)
    assert [x["rotina"] for x in bd.rotinas_do_dia()] == ["ok"]


def test_sem_log_do_dia_devolve_vazio(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "_workspace", lambda: tmp_path)
    assert bd.rotinas_do_dia() == []


def test_repositorio_sem_remote_nao_reporta_commit(monkeypatch):
    """Dentro do container `/workspace` é um volume com um repositório próprio.

    O único commit dele se chama "baseline (image build)". Listar aquilo como
    "commits de hoje" informa uma coisa que não aconteceu.
    """
    monkeypatch.setattr(bd, "_git", lambda *a: "")
    t = bd.trabalho_do_dia()
    assert t["sem_repo"] is True and t["commits"] == []


def test_com_remote_reporta_commit(monkeypatch):
    saidas = {("remote",): "origin", ("diff", "--stat"): " 2 files changed"}
    monkeypatch.setattr(bd, "_git",
                        lambda *a: saidas.get(a, "abc1234 fez algo" if a[0] == "log" else ""))
    t = bd.trabalho_do_dia()
    assert t["sem_repo"] is False and t["commits"] == ["abc1234 fez algo"]


def test_markdown_do_fim_do_dia_omite_commit_sem_repo(monkeypatch):
    monkeypatch.setattr(bd, "coletar_fim_do_dia", lambda: {
        "data": "27/07/2026", "dia_semana": "segunda-feira",
        "trabalho": {"commits": [], "alterado": [], "sem_repo": True},
        "rotinas": [], "arquivos_tocados": [], "tarefas_abertas": [],
        "gates_pendentes": [], "tickets": [],
    })
    texto = bd.fim_do_dia_em_markdown()
    assert "Commits de hoje" not in texto


# ── o dossiê vira prompt ─────────────────────────────────────────────────

def test_markdown_diz_quando_nao_ha_nada(monkeypatch):
    """Seção vazia precisa aparecer dizendo "nada".

    Omitir é ambíguo: quem lê não sabe se não havia gate pendente ou se a
    consulta falhou. Ausência é informação e tem de estar escrita.
    """
    monkeypatch.setattr(bd, "coletar", lambda: {
        "data": "27/07/2026", "dia_semana": "segunda-feira", "hora": "07:00",
        "gates_pendentes": [], "tarefas": [], "tickets": [],
        "rotinas_falhando": [], "pauta_do_dia": [],
    })
    texto = bd.em_markdown()
    assert texto.count("_nada_") == 5


def test_tarefa_atrasada_e_marcada(monkeypatch):
    monkeypatch.setattr(bd, "coletar", lambda: {
        "data": "27/07/2026", "dia_semana": "segunda-feira", "hora": "07:00",
        "gates_pendentes": [], "tickets": [], "rotinas_falhando": [], "pauta_do_dia": [],
        "tarefas": [{"titulo": "pagar boleto", "vencida": True, "prioridade": 4}],
    })
    assert "⚠ ATRASADA pagar boleto" in bd.em_markdown()


# ── as rotinas entregam o dossiê à skill ─────────────────────────────────

@pytest.mark.parametrize("rotina,funcao", [
    ("good_morning.py", "em_markdown"),
    ("end_of_day.py", "fim_do_dia_em_markdown"),
])
def test_rotina_coleta_antes_de_chamar_a_skill(rotina, funcao):
    fonte = (REPO_ROOT / "ADWs" / "routines" / rotina).read_text(encoding="utf-8")
    assert funcao in fonte, "sem a coleta, a skill volta a navegar o workspace"
    assert "--dossie-pronto" in fonte, "é a marca que a skill lê para pular a coleta"


@pytest.mark.parametrize("rotina", ["good_morning.py", "end_of_day.py"])
def test_falha_na_coleta_nao_impede_o_briefing(rotina):
    """Briefing sem dossiê ainda é briefing; nenhum briefing é manhã às cegas."""
    fonte = (REPO_ROOT / "ADWs" / "routines" / rotina).read_text(encoding="utf-8")
    trecho = fonte.split("def coletar_dossie")[1].split("def main")[0]
    assert "except Exception" in trecho and 'return ""' in trecho


@pytest.mark.parametrize("skill", ["prod-good-morning", "prod-end-of-day"])
def test_skill_sabe_pular_a_coleta(skill):
    texto = (REPO_ROOT / ".claude" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    assert "--dossie-pronto" in texto, \
        "sem instrução, a skill refaz a coleta e paga duas vezes pelo mesmo dado"
