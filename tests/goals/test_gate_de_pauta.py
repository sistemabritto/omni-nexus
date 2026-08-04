"""
tests/goals/test_gate_de_pauta.py

O gate que faltava na esteira de conteúdo (2026-08-03).

`weekly_content_research` gravava 21 pautas em `proposta` e terminava em
silêncio: a única forma de liberá-las era alguém lembrar de abrir a tela
`/pautas` e clicar. O ticket que ele criava ia para o inbox do @pixel, não para
o Felipe. Em 01/08 e 03/08/2026 a fila estava cheia, a esteira das 06:00 não
achou nada `aprovada`, e o dia saiu em branco — sem erro em lugar nenhum,
porque não havia erro. Havia um gate que nunca pedia nada.

O que este arquivo trava:
  1. o card do Telegram mostra as pautas agrupadas por dia, não uma lista crua
  2. o gate é UM por ciclo — rodar o research de novo não abre um segundo
  3. aprovar libera a fila de verdade (`proposta` -> `aprovada`)
  4. rejeitar não descarta pauta nenhuma
  5. o briefing matinal enxerga `proposta` (era o que dizia "hoje: nada")
  6. o scheduler recupera a janela semanal que um redeploy fez perder

Run:
    pytest tests/goals/test_gate_de_pauta.py -v
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dashboard" / "backend"))
sys.path.insert(0, str(ROOT))


# ── 1. o card ────────────────────────────────────────────────────────────

def test_card_agrupa_as_pautas_por_dia():
    """Agrupado por dia porque é assim que a decisão é tomada: o calendário
    fatia a fila em blocos de três e o que se aprova é a semana."""
    from routes.approvals import _render_structured_items

    texto = _render_structured_items("pauta_ciclo", {"pautas": [
        {"keyword": "plataforma de whatsapp", "data_alvo": "2026-08-03",
         "volume": 210, "funil": "whatsapp"},
        {"keyword": "funil de vendas", "data_alvo": "2026-08-03", "volume": 590},
        {"keyword": "crm integrado", "data_alvo": "2026-08-04", "volume": 90},
    ]})

    assert "3 pautas propostas" in texto
    assert "03/08" in texto and "04/08" in texto
    assert "plataforma de whatsapp" in texto
    # Volume e funil são os dois critérios que fazem alguém trocar uma pauta
    # antes de liberar; sem eles o card pede um "sim" sobre o que ninguém
    # consegue avaliar pelo celular.
    assert "210/mês" in texto
    assert "/whatsapp" in texto


def test_card_vazio_quando_nao_ha_pauta():
    from routes.approvals import _render_structured_items

    assert _render_structured_items("pauta_ciclo", {}) == ""
    assert _render_structured_items("pauta_ciclo", {"pautas": []}) == ""


def test_card_ignora_item_sem_keyword():
    """Payload malformado não pode virar bullet vazio no Telegram."""
    from routes.approvals import _render_structured_items

    texto = _render_structured_items("pauta_ciclo", {"pautas": [
        {"data_alvo": "2026-08-03"}, {"keyword": "a que vale", "data_alvo": "2026-08-03"},
    ]})
    assert "a que vale" in texto
    assert texto.count("•") == 1


def test_outros_gates_nao_mudaram():
    """O render de pauta é um ramo novo, não uma reescrita do que existia."""
    from routes.approvals import _render_structured_items

    texto = _render_structured_items("project_suggestion",
                                     {"projects": [{"title": "Evo AI"}]})
    assert "Evo AI" in texto


# ── 2. um gate por ciclo ─────────────────────────────────────────────────

def test_chave_de_idempotencia_nunca_usa_contador_de_tentativa():
    """Os outros gates reabrem a cada retentativa; este NÃO pode.

    O research roda semanalmente e o catch-up de boot reexecuta o mesmo ciclo.
    Com `attempt` na chave, cada reexecução abriria um card novo das mesmas 21
    pautas — e card repetido ensina a ignorar o canal que sustenta o
    human-in-the-loop. Quem diferencia é o conteúdo, não a contagem: ver
    test_chave_carrega_a_assinatura_do_conteudo.
    """
    fonte = (ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(encoding="utf-8")
    assert 'idempotency_key = f"pauta:{ciclo}:{attempt}"' not in fonte
    trecho = fonte.split("else:  # pauta_ciclo")[1].split("now = _now()")[0]
    assert "attempt = 0" in trecho


def test_chave_carrega_a_assinatura_do_conteudo():
    """O ciclo sozinho na chave travava o caso legítimo.

    Rodar o research de novo com pautas DIFERENTES — o que acontece a cada
    ajuste de seed ou de filtro — fazia o `INSERT OR IGNORE` engolir o card novo
    em silêncio, e o humano ficava com um card apontando para pautas que já não
    existiam na fila. Aconteceu de verdade em 04/08/2026, ao regravar o ciclo
    2026-08-03.
    """
    fonte = (ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(encoding="utf-8")
    assert 'idempotency_key = f"pauta:{ciclo}:{assinatura}"' in fonte
    # A assinatura é do CONTEÚDO (keyword + dia), não um contador: mesma fila
    # reproposta tem de dar a mesma chave.
    assert 'p.get("keyword"), p.get("data_alvo")' in fonte
    assert "hashlib.sha256" in fonte


def test_card_anterior_do_mesmo_ciclo_expira():
    """Dois cards vivos do mesmo ciclo dariam ao humano a chance de aprovar o
    velho — liberando uma fila que já foi substituída."""
    fonte = (ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(encoding="utf-8")
    trecho = fonte.split("else:  # pauta_ciclo")[1].split("now = _now()")[0]
    assert "UPDATE pending_approvals SET status='expired'" in trecho
    assert "idempotency_key != :atual" in trecho, "não pode expirar o card que acabou de nascer"


def test_gate_type_aceito_em_todo_lugar_que_valida():
    """CHECK do SQLite, CheckConstraint do ORM e a allowlist da rota têm de
    concordar — se um deles esquecer, o gate falha só em produção."""
    for caminho in ("dashboard/backend/app.py", "dashboard/backend/models.py",
                    "dashboard/backend/routes/approvals.py"):
        fonte = (ROOT / caminho).read_text(encoding="utf-8")
        assert "pauta_ciclo" in fonte, caminho


def test_migracao_copia_as_colunas_da_tabela_antiga():
    """A versão hardcoded do rebuild omitia mission_id/project_id.

    Adicionar um gate_type dispara o rebuild; com a lista fixa, todo vínculo de
    aprovação de hierarquia iria para o ralo no caminho. A cópia agora é a
    interseção entre as colunas velhas e as novas.
    """
    fonte = (ROOT / "dashboard" / "backend" / "app.py").read_text(encoding="utf-8")
    assert "PRAGMA table_info(pending_approvals)" in fonte
    assert "_pa_copy = " in fonte
    assert "INSERT INTO pending_approvals ({_pa_copy})" in fonte


# ── 3 e 4. o efeito de aprovar e de rejeitar ─────────────────────────────

def test_aprovar_chama_aprovar_ciclo():
    fonte = (ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(encoding="utf-8")
    trecho = fonte.split('elif row.gate_type == "pauta_ciclo":')[1]
    assert "pauta_fila.aprovar_ciclo(ciclo)" in trecho
    # Fail-loud: consumir a aprovação sem liberar a fila é o pior desfecho —
    # o humano acha que decidiu e o dia sai em branco assim mesmo.
    assert "send_telegram_alert" in trecho


def test_rejeitar_nao_descarta_pauta():
    """Rejeitar devolve o ciclo para edição na tela; quem descarta é `vencer`,
    pela data. Um "não" no card não pode apagar o trabalho do research."""
    fonte = (ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(encoding="utf-8")
    trecho = fonte.split('elif row.gate_type == "pauta_ciclo":')[1].split("return jsonify")[0]
    assert 'if new_status == "approved":' in trecho
    for proibido in ("descartada", "DELETE FROM pautas"):
        assert proibido not in trecho


def test_aprovar_ciclo_move_proposta_para_aprovada(tmp_path, monkeypatch):
    """O contrato de verdade, contra o banco: `proposta` -> `aprovada`."""
    import pauta_fila

    monkeypatch.setattr(pauta_fila, "DB_PATH", tmp_path / "t.db", raising=False)
    conn = pauta_fila.conectar()
    try:
        pauta_fila.criar_tabela(conn) if hasattr(pauta_fila, "criar_tabela") else None
        amanha = date.today() + timedelta(days=1)
        pauta_fila.gravar_ciclo([{
            "prioridade": 1, "data": amanha.isoformat(), "slot": "09:00 BRT",
            "publish_at": f"{amanha.isoformat()}T12:00:00Z",
            "keyword": "teste de ciclo", "volume": 100, "kd": 10,
        }], conn=conn)
        ciclo = conn.execute("SELECT ciclo FROM pautas LIMIT 1").fetchone()[0]

        assert conn.execute("SELECT status FROM pautas").fetchone()[0] == "proposta"
        assert pauta_fila.aprovar_ciclo(ciclo, conn=conn) == 1
        assert conn.execute("SELECT status FROM pautas").fetchone()[0] == "aprovada"
        # Idempotente: aprovar de novo não tem o que mover.
        assert pauta_fila.aprovar_ciclo(ciclo, conn=conn) == 0
    finally:
        conn.close()


# ── 5. o briefing matinal ────────────────────────────────────────────────

def test_briefing_enxerga_pauta_em_proposta():
    """Dizia "pauta de hoje: nada" com 11 pautas paradas esperando aprovação —
    o único lugar que podia avisar estava olhando para o lado errado."""
    fonte = (ROOT / "dashboard" / "backend" / "briefing_dados.py").read_text(encoding="utf-8")
    assert 'for status in ("escrita", "aprovada", "proposta"):' in fonte


# ── 6. a janela semanal perdida ──────────────────────────────────────────

class _JobFalso:
    """O mínimo de `schedule.Job` que o catch-up lê: unit, start_day, at_time
    e o partial com (nome, script) em `.args`."""

    def __init__(self, unit, start_day, at_time, args, erro=None):
        self.unit, self.start_day, self.at_time = unit, start_day, at_time
        self.rodou = False

        def func():
            if erro:
                raise erro
            self.rodou = True

        func.args = args  # type: ignore[attr-defined]
        self.job_func = func


# Horários de referência que não dependem da hora em que a suíte roda.
#
# A primeira versão destes testes montava a janela passada com
# `(datetime.now() - timedelta(hours=2)).time()`. Depois da meia-noite isso
# devolve um horário de ONTEM que, lido como hora do dia de hoje, está no
# FUTURO — e o teste falhava sozinho entre 00:00 e 02:00. Custou uma
# investigação de "regressão" que não existia: o código estava certo o tempo
# todo. Teste que depende do relógio de parede só falha quando ninguém está
# olhando.
JA_PASSOU = time(0, 0)      # meia-noite: anterior a qualquer instante do dia
AINDA_VEM = time(23, 59)    # último minuto: posterior a qualquer instante útil


def _job(unit, start_day, at_time, args, erro=None):
    return _JobFalso(unit, start_day, at_time, args, erro)


@pytest.fixture
def scheduler_isolado(tmp_path, monkeypatch):
    import scheduler

    monkeypatch.setattr(scheduler, "MARCAS_DIR", tmp_path / "marcas")
    return scheduler


def test_roda_semanal_que_perdeu_a_janela_de_hoje(scheduler_isolado, monkeypatch):
    """O caso real: redeploy domingo 12:15 mata o research das 08:00 e a
    semana inteira se perde em silêncio."""
    import schedule as _schedule

    agora = datetime.now()
    dia = list(scheduler_isolado.DIAS_DA_SEMANA)[agora.weekday()]
    job = _job("weeks", dia, JA_PASSOU, ("Research Semanal", "weekly_content_research.py"))
    monkeypatch.setattr(_schedule, "get_jobs", lambda: [job])

    scheduler_isolado.recuperar_janelas_perdidas()
    assert job.rodou, "a janela passou e ninguém rodou — é o bug de 02/08"


def test_nao_roda_o_que_ainda_vai_acontecer(scheduler_isolado, monkeypatch):
    import schedule as _schedule

    agora = datetime.now()
    dia = list(scheduler_isolado.DIAS_DA_SEMANA)[agora.weekday()]
    job = _job("weeks", dia, AINDA_VEM, ("Research Semanal", "weekly_content_research.py"))
    monkeypatch.setattr(_schedule, "get_jobs", lambda: [job])

    scheduler_isolado.recuperar_janelas_perdidas()
    assert not job.rodou, "o schedule roda no horário; catch-up aqui seria execução dupla"


def test_nao_repete_o_que_ja_rodou_hoje(scheduler_isolado, monkeypatch):
    """Redeploy no mesmo dia não pode reexecutar o research."""
    import schedule as _schedule

    agora = datetime.now()
    dia = list(scheduler_isolado.DIAS_DA_SEMANA)[agora.weekday()]
    job = _job("weeks", dia, JA_PASSOU,
               ("Research Semanal", "weekly_content_research.py"))
    monkeypatch.setattr(_schedule, "get_jobs", lambda: [job])

    scheduler_isolado._marcar_execucao("weekly_content_research.py")
    scheduler_isolado.recuperar_janelas_perdidas()
    assert not job.rodou


def test_diario_nao_entra_no_catch_up(scheduler_isolado, monkeypatch):
    """Diário perdido espera algumas horas; semanal espera sete dias. Só o
    segundo justifica rodar fora de hora no boot."""
    import schedule as _schedule

    job = _job("days", None, JA_PASSOU, ("Good Morning", "good_morning.py"))
    monkeypatch.setattr(_schedule, "get_jobs", lambda: [job])

    scheduler_isolado.recuperar_janelas_perdidas()
    assert not job.rodou


def test_semanal_de_outro_dia_da_semana_nao_roda(scheduler_isolado, monkeypatch):
    import schedule as _schedule

    agora = datetime.now()
    outro = list(scheduler_isolado.DIAS_DA_SEMANA)[(agora.weekday() + 3) % 7]
    job = _job("weeks", outro, JA_PASSOU,
               ("Memory Lint", "memory_lint.py"))
    monkeypatch.setattr(_schedule, "get_jobs", lambda: [job])

    scheduler_isolado.recuperar_janelas_perdidas()
    assert not job.rodou


def test_falha_no_catch_up_nao_derruba_o_boot(scheduler_isolado, monkeypatch):
    """Um catch-up que explode não pode impedir o scheduler de subir — sem ele
    de pé, NENHUMA rotina roda."""
    import schedule as _schedule

    agora = datetime.now()
    dia = list(scheduler_isolado.DIAS_DA_SEMANA)[agora.weekday()]
    job = _job("weeks", dia, JA_PASSOU,
               ("Explode", "explode.py"), erro=RuntimeError("boom"))
    monkeypatch.setattr(_schedule, "get_jobs", lambda: [job])

    scheduler_isolado.recuperar_janelas_perdidas()  # não levanta


def test_marca_so_e_gravada_no_sucesso(scheduler_isolado):
    """Execução que falhou tem de ser retentada pelo catch-up do próximo boot,
    não considerada feita."""
    assert not scheduler_isolado._rodou_hoje("qualquer.py")
    scheduler_isolado._marcar_execucao("qualquer.py")
    assert scheduler_isolado._rodou_hoje("qualquer.py")

    fonte = (ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert "if result.returncode == 0:\n            _marcar_execucao(script)" in fonte


# ── o research abre o gate ───────────────────────────────────────────────

def test_research_abre_o_gate_no_telegram():
    fonte = (ROOT / "ADWs" / "routines" / "weekly_content_research.py").read_text(encoding="utf-8")
    assert "def abrir_gate_no_telegram" in fonte
    assert "abrir_gate_no_telegram(pautas, ciclo, args.dry_run)" in fonte
    assert '"gate_type": "pauta_ciclo"' in fonte


@pytest.fixture
def research(monkeypatch):
    """O módulo do research com o SDK trocado por um espião — nenhum teste
    daqui pode encostar na API de verdade."""
    import importlib.util
    import types

    chamadas: list[tuple[str, dict]] = []
    falso = types.ModuleType("sdk_client")
    falso.evo = types.SimpleNamespace(  # type: ignore[attr-defined]
        post=lambda rota, corpo=None: chamadas.append((rota, corpo or {})),
        get=lambda rota, params=None: {},
        patch=lambda rota, corpo=None: None,
    )
    monkeypatch.setitem(sys.modules, "sdk_client", falso)

    spec = importlib.util.spec_from_file_location(
        "wcr", ROOT / "ADWs" / "routines" / "weekly_content_research.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, chamadas


PAUTAS = [{"keyword": "plataforma de whatsapp", "data": "2026-08-03", "volume": 210}]


def test_research_abre_um_gate_com_o_ciclo(research):
    mod, chamadas = research
    mod.abrir_gate_no_telegram(PAUTAS, "2026-08-03", False)

    gates = [c for c in chamadas if c[0] == "/api/approvals"]
    assert len(gates) == 1
    corpo = gates[0][1]
    assert corpo["gate_type"] == "pauta_ciclo"
    assert corpo["payload"]["ciclo"] == "2026-08-03"
    assert corpo["payload"]["pautas"][0]["keyword"] == "plataforma de whatsapp"
    # data_alvo, não "data": é o campo que o card agrupa e o que a fila usa.
    assert corpo["payload"]["pautas"][0]["data_alvo"] == "2026-08-03"


def test_research_nao_abre_gate_em_dry_run(research):
    """`--dry-run` existe para rodar o research sem tocar em nada; abrir card
    no Telegram é tocar."""
    mod, chamadas = research
    mod.abrir_gate_no_telegram(PAUTAS, "2026-08-03", True)
    assert chamadas == []


def test_research_sem_ciclo_nao_abre_gate(research):
    """Sem ciclo não há o que aprovar — o card viraria um botão que não liga
    em nada."""
    mod, chamadas = research
    mod.abrir_gate_no_telegram(PAUTAS, None, False)
    assert chamadas == []


def test_gate_indisponivel_nao_derruba_o_research(research, monkeypatch):
    """A fila e o markdown já estão salvos quando o gate é aberto — falhar
    aqui não pode perder o trabalho da rodada inteira."""
    mod, _ = research

    def explodir(*a, **k):
        raise RuntimeError("dashboard fora do ar")

    monkeypatch.setattr(sys.modules["sdk_client"].evo, "post", explodir)
    mod.abrir_gate_no_telegram(PAUTAS, "2026-08-03", False)  # não levanta
