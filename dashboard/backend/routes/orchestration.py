"""Orchestration routes — persistent multi-agent job queue.

Endpoints:
  POST    /api/orchestration-jobs    → Create a new orchestration job
  GET     /api/orchestration-jobs    → List all jobs (filtered by status/agent)
  GET     /api/orchestration-jobs/<id> → Get a single job with logs
  POST    /api/orchestration-jobs/<id>/cancel → Cancel a running job
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request

# `from models import ...`, não `from dashboard.backend.models import ...`:
# app.py sobe com `dashboard/backend` no sys.path (é o cwd do processo e o
# WORKDIR da imagem), então o pacote `dashboard` não é importável de dentro
# dele. Os outros 20 blueprints em routes/ já usam esta forma; a absoluta
# derrubava o boot inteiro com ModuleNotFoundError na linha de import.
from models import db, OrchestrationJob

logger = logging.getLogger(__name__)

ORCHESTRATION_WORKSPACE = Path(__file__).resolve().parent.parent.parent / "workspace"
WORKSPACE_ROOT = ORCHESTRATION_WORKSPACE if ORCHESTRATION_WORKSPACE.exists() else Path("/workspace/workspace")

# Sem mkdir do diretório de locks aqui: `provider_fallback._workspace_bash_lock`
# já cria o `.locks` no momento em que pega o lock. Fazer isso em tempo de
# import era escrita em disco durante o boot do Flask — falha em filesystem
# somente-leitura e derruba a aplicação inteira para proteger nada.

bp = Blueprint("orchestration", __name__, url_prefix="/api")


def _job_ou_404(job_id: str):
    """Devolve (job, None) ou (None, resposta_404).

    `get_or_404` responde com a página HTML de erro do Flask — numa API que o
    frontend consome via fetch().json(), isso vira um erro de parse em vez de
    um "não encontrei", que é bem mais difícil de debugar do lado do cliente.
    """
    job = OrchestrationJob.query.get(job_id)
    if job is None:
        return None, (jsonify({"error": f"job '{job_id}' não encontrado"}), 404)
    return job, None


# ── API: POST /api/orchestration-jobs ──────────────────────────────────

@bp.route("/orchestration-jobs", methods=["POST"])
def create_job():
    """Cria um novo job de orquestração e retorna o ID imediatamente.

    Espera JSON: { agent: string, prompt: string, telegram_chat_id?: string }
    O worker consumirá a fila e atualizará o status.
    """
    data = request.get_json(silent=True) or {}
    agent = data.get("agent", "unknown")
    prompt = data.get("prompt", "")
    telegram_chat_id = data.get("telegram_chat_id")

    if not prompt:
        return jsonify({"error": "prompt é obrigatório"}), 400

    # UUID, e não `os.environ.get("JOB_ID")`: ler uma variável de ambiente do
    # processo para gerar a CHAVE PRIMÁRIA de uma linha por requisição faz todo
    # job daquele container nascer com o mesmo id — o segundo POST estoura
    # IntegrityError. O padding com zeros até 36 chars, além disso, colava
    # sufixo falso num id que já era único.
    job_id = str(uuid.uuid4())

    job = OrchestrationJob(
        id=job_id,
        agent=agent,
        prompt=prompt,
        telegram_chat_id=telegram_chat_id,
        status="pending",
        stage="start",
    )
    db.session.add(job)
    db.session.commit()

    return jsonify({
        "id": job_id,
        "status": "pending",
        "message": "Job criado. Use /status <id> para acompanhar.",
    }), 201


# ── API: GET /api/orchestration-jobs ───────────────────────────────────

@bp.route("/orchestration-jobs", methods=["GET"])
def list_jobs():
    """Lista jobs, opcionalmente filtrados por status ou agente."""
    status_filter = request.args.get("status")
    agent_filter = request.args.get("agent")

    query = OrchestrationJob.query

    if status_filter:
        query = query.filter(OrchestrationJob.status == status_filter)
    if agent_filter:
        query = query.filter(OrchestrationJob.agent == agent_filter)

    jobs = query.order_by(OrchestrationJob.created_at.desc()).all()
    return jsonify({"jobs": [job.to_dict() for job in jobs]}), 200


# ── API: GET /api/orchestration-jobs/<id> ─────────────────────────────

@bp.route("/orchestration-jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    """Retorna o status de um job e seus logs (últimas linhas)."""
    job, erro = _job_ou_404(job_id)
    if erro:
        return erro
    # Lê logs do arquivo de stderr/stdout associado (se existir)
    log_path = WORKSPACE_ROOT / f"logs/orchestration-{job_id}.log"
    logs = ""
    if log_path.exists():
        try:
            logs = log_path.read_text(encoding="utf-8", errors="replace")
            # Mostrar apenas as últimas 20 linhas
            lines = logs.splitlines()
            logs = "\n".join(lines[-20:]) if lines else ""
        except Exception as e:
            logs = f"[erro ao ler logs: {e}]"

    return jsonify({
        "job": job.to_dict(),
        "logs": logs,
    }), 200


# ── API: POST /api/orchestration-jobs/<id>/cancel ─────────────────────

@bp.route("/orchestration-jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    """Solicita cancelamento de um job (melhor-effort)."""
    job, erro = _job_ou_404(job_id)
    if erro:
        return erro
    if job.status in ("success", "failed", "cancelled"):
        return jsonify({"error": f"Job já finalizado com status '{job.status}'"}), 400

    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        "id": job_id,
        "status": "cancelled",
        "message": "Cancelamento solicitado.",
    }), 200


# ── CLI: Iniciar worker de processamento ───────────────────────────────

def _run_agent_stage(job: OrchestrationJob) -> dict:
    """Executa uma etapa do agente dentro do job.

    Este é um esqueleto — o worker real está em chat_orchestrator.py.
    Retorna {"status": "success"|"failed", "output": "...", "error": "..."}.

    Import preguiçoso de propósito: chat_orchestrator puxa provider_fallback,
    que resolve a cadeia de providers inteira. Carregar isso no import do
    blueprint atrasaria o boot do Flask por algo usado só sob demanda.
    """
    from chat_orchestrator import run_orchestration_job
    return run_orchestration_job(job)