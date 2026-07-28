"""
tests/goals/test_registro_de_rotinas.py

2026-07-27 — a faxina da página de Rotinas.

O Felipe olhou a tela e disse que não dava para entender nada, que tinha muita
"dummy data". Estava certo, e não era questão de gosto: eram três defeitos que
produziam números falsos com cara de números reais.

1. `/api/scheduler` lia `scheduler.py` com regex sobre o código-fonte. O regex
   casava também a linha do carregador de YAML dentro do próprio arquivo, e a
   tela listava uma rotina sem nome rodando "every interval_min min" — um
   trecho de código exibido como se fosse uma rotina agendada.
2. `/api/routines` inventava um id abreviado (`good_morning` → `morning`) que
   não é o id com que o runner grava métricas (`good-morning`). A mesma rotina
   aparecia duas vezes: uma com 25 execuções, outra zerada.
3. Os totais somavam `val["cost"]` e `val["tokens"]`, chaves que não existem.
   O painel dizia custo US$ 0,00 com US$ 27 gastos no arquivo.

Run:
    pytest tests/goals/test_registro_de_rotinas.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from routines_registry import (  # noqa: E402
    agendamento_real, descrever_frequencia, motor_do_script)


# ── o agendamento vem do agendador, não de regex ─────────────────────────

def test_le_o_agendador_de_verdade():
    jobs = agendamento_real(forcar=True)
    assert jobs, "sem isto a página cai no regex, que é o que produzia fantasma"
    assert all(j.get("next_run") for j in jobs), \
        "próxima execução é a informação que o regex nunca teve como dar"


def test_nao_traz_rotina_fantasma():
    """O regex lia o carregador de YAML como se fosse uma rotina agendada."""
    jobs = agendamento_real(forcar=True)
    nomes = [j["name"] for j in jobs]
    assert "" not in nomes, "rotina sem nome é linha de código lida como dado"
    assert not any("interval_min" in str(j) for j in jobs)


def test_toda_rotina_agendada_tem_nome_legivel():
    """`_hourly_report_safe` é nome de função, não de rotina."""
    jobs = agendamento_real(forcar=True)
    assert not any(j["name"].startswith("_") for j in jobs)


def test_a_rotina_do_agendado_aparece():
    jobs = agendamento_real(forcar=True)
    achada = [j for j in jobs if j["script"] == "derivar_redes_pendentes.py"]
    assert achada, "a rotina existe no scheduler.py e tem de aparecer na tela"
    assert achada[0]["unit"] == "minutes" and achada[0]["interval"] == 15


@pytest.mark.parametrize("job,esperado", [
    ({"unit": "days", "at_time": "06:00:00"}, "Todo dia às 06:00"),
    ({"unit": "minutes", "interval": 15}, "A cada 15 min"),
    ({"unit": "hours", "interval": 1}, "De hora em hora"),
    ({"unit": "weeks", "start_day": "sunday", "at_time": "08:00:00"}, "Domingo às 08:00"),
])
def test_frequencia_em_portugues(job, esperado):
    assert descrever_frequencia(job)[0] == esperado


# ── motor: quem gasta token e quem não gasta ─────────────────────────────

def test_backup_e_python_puro():
    """27 execuções e US$ 0,00 no histórico.

    A primeira heurística marcava qualquer `from runner import ...` como
    rotina de modelo, e o backup importa `run_script`, que roda função Python
    e não fala com modelo nenhum.
    """
    assert motor_do_script("backup.py") == "python"


def test_esteira_chama_modelo():
    assert motor_do_script("daily_content_pipeline.py") == "modelo"


def test_segue_o_import_para_achar_a_chamada():
    """`derivar_redes_pendentes.py` é um entrypoint de quatro linhas.

    Quem gasta token é o `ghost_social_bridge` que ele importa. Parar no
    arquivo de entrada classificaria a rotina que roda a cada 15 minutos como
    determinística — exatamente a que mais precisa do aviso.
    """
    assert motor_do_script("derivar_redes_pendentes.py") == "modelo"


def test_script_inexistente_nao_chuta():
    assert motor_do_script("nao_existe_isso.py") == ""
    assert motor_do_script("") == ""


# ── os endpoints ─────────────────────────────────────────────────────────

@pytest.fixture
def cliente(monkeypatch, tmp_path):
    """App Flask com um metrics.json controlado."""
    metrics = {
        "good-morning": {"runs": 25, "successes": 19, "total_cost_usd": 4.05,
                         "total_input_tokens": 1000, "total_output_tokens": 500,
                         "last_run": "2026-07-27T07:02:32"},
        "backup": {"runs": 27, "successes": 27, "total_cost_usd": 0.0,
                   "total_input_tokens": 0, "total_output_tokens": 0,
                   "last_run": "2026-07-27T21:03:17"},
    }
    arquivo = tmp_path / "metrics.json"
    arquivo.write_text(json.dumps(metrics), encoding="utf-8")

    import routes.routines as mod

    monkeypatch.setattr(mod, "METRICS_PATH", arquivo)

    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(mod.bp)
    return app.test_client()


def test_totais_somam_as_chaves_que_existem(cliente):
    """Somava `cost`/`tokens`; o runner grava `total_cost_usd`/`total_*_tokens`."""
    dados = cliente.get("/api/routines").get_json()
    assert dados["totals"]["total_cost"] == pytest.approx(4.05)
    assert dados["totals"]["total_tokens"] == 1500
    assert dados["totals"]["total_runs"] >= 52


def test_nao_duplica_rotina_com_id_abreviado(cliente):
    """`good_morning` → `morning` criava um gêmeo zerado de `good-morning`."""
    metricas = cliente.get("/api/routines").get_json()["metrics"]
    assert metricas["good-morning"]["runs"] == 25
    assert "morning" not in metricas, \
        "a mesma rotina em duas linhas, uma com histórico e outra vazia"


def test_rotina_carrega_o_motor(cliente):
    metricas = cliente.get("/api/routines").get_json()["metrics"]
    assert metricas["backup"]["engine"] == "python"
