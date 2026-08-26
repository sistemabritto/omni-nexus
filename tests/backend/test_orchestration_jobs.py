"""tests/backend/test_orchestration_jobs.py

Fila de jobs de orquestração multi-agente (26/08/2026).

Cada teste aqui trava um bug que existiu de verdade e que só apareceria em
produção:

  1. `routes/orchestration.py` e `chat_orchestrator.py` importavam
     `dashboard.backend.*`. O processo do dashboard sobe com
     `dashboard/backend` como cwd/WORKDIR, então o pacote `dashboard` não é
     importável de dentro dele: o boot inteiro do Flask morria com
     ModuleNotFoundError na linha de import do blueprint. Os outros 20
     blueprints em routes/ sempre usaram `from models import ...`.
  2. O blueprint fazia `mkdir` do diretório de locks em tempo de IMPORT —
     escrita em disco durante o boot, que derruba a aplicação em filesystem
     somente-leitura para proteger nada (provider_fallback já cria o diretório
     quando pega o lock).
  3. O id do job vinha de `os.environ.get("JOB_ID")`, uma variável de ambiente
     do processo, usada como CHAVE PRIMÁRIA de uma linha por requisição: com
     JOB_ID setado, o segundo POST estourava IntegrityError.
  4. `POST /cancel` gravava `status='cancelled'` e o worker seguia até o fim,
     sobrescrevendo com 'success'. O cancelamento aparecia por alguns segundos
     e sumia sozinho.

Run:
    pytest tests/backend/test_orchestration_jobs.py -v
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


# ── 1. o contrato de import que derrubava o boot ─────────────────────────

@pytest.mark.parametrize("modulo", ["routes.orchestration", "chat_orchestrator"])
def test_importa_sem_o_pacote_dashboard_no_path(modulo):
    """Importa como o processo real importa: cwd em dashboard/backend, e a
    raiz do repositório FORA do sys.path — que é o que torna `dashboard`
    inimportável. Um `from dashboard.backend.x import y` reprova aqui.

    Roda em subprocesso porque o teste precisa de um sys.path limpo; no
    processo do pytest a raiz do repo já está no path e o bug não aparece.
    """
    codigo = f"import {modulo}; print('OK')"
    proc = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
    )
    assert proc.returncode == 0, (
        f"{modulo} não importa isolado:\n{proc.stderr[-2000:]}"
    )


def test_import_do_blueprint_nao_escreve_em_disco():
    """Nenhum mkdir/open em modo de escrita durante o import do blueprint."""
    import importlib

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        sys.modules.pop("routes.orchestration", None)
        importlib.import_module("routes.orchestration")
        mock_mkdir.assert_not_called()


# ── app mínimo para exercitar as rotas ───────────────────────────────────

@pytest.fixture
def app_e_client(tmp_path):
    from flask import Flask
    from models import db
    from routes.orchestration import bp

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path/'t.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True
    db.init_app(app)
    app.register_blueprint(bp)
    with app.app_context():
        db.create_all()
        yield app, app.test_client()


# ── 2. id do job ─────────────────────────────────────────────────────────

def test_dois_jobs_recebem_ids_diferentes_mesmo_com_JOB_ID_no_ambiente(
    app_e_client, monkeypatch
):
    """O bug: `os.environ.get("JOB_ID")` fazia todo job do container nascer
    com a mesma chave primária."""
    monkeypatch.setenv("JOB_ID", "um-id-fixo-do-ambiente")
    _, client = app_e_client

    r1 = client.post("/api/orchestration-jobs", json={"agent": "ops", "prompt": "a"})
    r2 = client.post("/api/orchestration-jobs", json={"agent": "ops", "prompt": "b"})

    assert r1.status_code == 201 and r2.status_code == 201
    id1, id2 = r1.get_json()["id"], r2.get_json()["id"]
    assert id1 != id2
    # e são UUIDs de verdade, como o comentário do model sempre prometeu
    uuid.UUID(id1)
    uuid.UUID(id2)


def test_prompt_vazio_e_recusado(app_e_client):
    _, client = app_e_client
    r = client.post("/api/orchestration-jobs", json={"agent": "ops", "prompt": ""})
    assert r.status_code == 400


# ── 3. 404 em JSON, nunca a página HTML do Flask ─────────────────────────

@pytest.mark.parametrize("rota,metodo", [
    ("/api/orchestration-jobs/nao-existe", "get"),
    ("/api/orchestration-jobs/nao-existe/cancel", "post"),
])
def test_job_inexistente_responde_json_e_nao_html(app_e_client, rota, metodo):
    _, client = app_e_client
    r = getattr(client, metodo)(rota)
    assert r.status_code == 404
    assert r.is_json, "get_or_404 devolvia HTML e quebrava o .json() do frontend"
    assert "error" in r.get_json()


# ── 4. cancelamento é honrado, não sobrescrito por 'success' ─────────────

def test_worker_para_no_cancelamento_e_nao_marca_sucesso(app_e_client):
    """Simula o humano cancelando entre duas etapas: o worker tem de parar e
    o status final tem de continuar 'cancelled'."""
    import chat_orchestrator as co
    from models import db, OrchestrationJob

    app, client = app_e_client
    job_id = client.post(
        "/api/orchestration-jobs", json={"agent": "ops", "prompt": "x"}
    ).get_json()["id"]

    chamadas = {"n": 0}

    def fake_invoke(**kwargs):
        # cancela "de fora" durante a primeira etapa, como faria o humano
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            job = OrchestrationJob.query.get(job_id)
            job.status = "cancelled"
            db.session.commit()
        return {"status": "success", "output": "saida", "error": None}

    worker = co.OrchestrationWorker(app)
    with patch.object(co, "invoke_with_fallback", side_effect=fake_invoke):
        worker._process_next_job()

    job = OrchestrationJob.query.get(job_id)
    assert job.status == "cancelled", (
        f"cancelamento foi sobrescrito por '{job.status}' — o worker seguiu "
        "até o fim ignorando o pedido do humano"
    )
    # 'ops' tem 3 etapas; parou cedo em vez de rodar as três
    assert chamadas["n"] < 3, "worker não parou: gastou chamada de modelo depois do cancel"


def test_falha_de_etapa_marca_job_como_failed(app_e_client):
    import chat_orchestrator as co
    from models import OrchestrationJob

    app, client = app_e_client
    job_id = client.post(
        "/api/orchestration-jobs", json={"agent": "ops", "prompt": "x"}
    ).get_json()["id"]

    worker = co.OrchestrationWorker(app)
    with patch.object(co, "invoke_with_fallback",
                      return_value={"status": "failed", "error": "provider morreu"}):
        worker._process_next_job()

    job = OrchestrationJob.query.get(job_id)
    assert job.status == "failed"
    assert "provider morreu" in job.error


def test_caminho_feliz_percorre_todas_as_etapas(app_e_client):
    import chat_orchestrator as co
    from models import OrchestrationJob

    app, client = app_e_client
    job_id = client.post(
        "/api/orchestration-jobs", json={"agent": "ops", "prompt": "x"}
    ).get_json()["id"]

    worker = co.OrchestrationWorker(app)
    with patch.object(co, "invoke_with_fallback",
                      return_value={"status": "success", "output": "ok", "error": None}) as m:
        worker._process_next_job()

    job = OrchestrationJob.query.get(job_id)
    assert job.status == "success"
    assert job.stage == "done"
    assert m.call_count == len(co.AGENT_STAGES["ops"])
