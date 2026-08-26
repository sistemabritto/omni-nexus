"""Orchestration routes — persistent multi-agent job queue.

Endpoints:
  POST    /api/orchestration-jobs    → Create a new orchestration job
  GET     /api/orchestration-jobs    → List all jobs (filtered by status/agent)
  GET     /api/orchestration-jobs/<id> → Get a single job with logs
  POST    /api/orchestration-jobs/<id>/cancel → Cancel a running job
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request

from dashboard.backend.models import db, OrchestrationJob

logger = logging.getLogger(__name__)

ORCHESTRATION_WORKSPACE = Path(__file__).resolve().parent.parent.parent / "workspace"
WORKSPACE_ROOT = ORCHESTRATION_WORKSPACE if ORCHESTRATION_WORKSPACE.exists() else Path("/workspace/workspace")

# Ensure the workspace-level lock directory exists
(ORCHESTRATION_WORKSPACE / ".locks").mkdir(parents=True, exist_ok=True)

bp = Blueprint("orchestration", __name__, url_prefix="/api")


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

    job_id = os.environ.get("JOB_ID") or f"job-{int(time.time()*1000)}-{os.getpid()}"
    # Tornar mais legível se desejar, mas UUID seria melhor. Mantendo compat.
    job_id = job_id[:36] if len(job_id) > 36 else job_id + "0" * (36 - len(job_id))

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
    job = OrchestrationJob.query.get_or_404(job_id)
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
    job = OrchestrationJob.query.get_or_404(job_id)
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
    """
    from dashboard.backend.chat_orchestrator import run_orchestration_job
    return run_orchestration_job(job)


# Hook para garantir que o worker pode ser importado via `python -m dashboard.backend.chat_orchestrator`
# (importação preguiçosa para evitar circular imports)
if __name__ == "__main__":
    pass