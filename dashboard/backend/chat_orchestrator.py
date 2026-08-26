"""Chat Orchestrator — processa jobs de orquestração disparados via Telegram/Chat.

Este worker roda em background (thread ou processo separado) e:
  1. Pega jobs com status 'pending' da fila.
  2. Executa as etapas definidas para o agente (ex: research → draft → review).
  3. Após cada etapa, salva artefato parcial e atualiza o job no banco (checkpoint).
  4. Se falhar, marca erro e permite retry manual via /cancel + novo POST.
  5. Se completar, marca success.

Integra com o motor resiliente existente (provider_fallback.invoke_with_fallback)
para ter fallback automático entre modelos/providers (NVIDIA → OpenRouter → Anthropic).

Uso:
  from chat_orchestrator import start_orchestration_worker
  start_orchestration_worker(app)  # dentro do contexto Flask
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# Carrega .env do workspace
WORKSPACE = Path(__file__).resolve().parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except Exception:
    pass

# Imports locais, não `dashboard.backend.*`: o processo sobe com
# `dashboard/backend` como cwd/WORKDIR, então o pacote `dashboard` não é
# importável de dentro dele. Ver o comentário gêmeo em routes/orchestration.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from provider_fallback import invoke_with_fallback, PER_ATTEMPT_TIMEOUT_CAP  # noqa: E402
from models import db, OrchestrationJob  # noqa: E402

logger = logging.getLogger(__name__)

# ── Configuração de estágios por agente ─────────────────────────────────

# Cada agente define sua cadeia de estágios. O worker executa em ordem.
# O retorno de cada estágio vira o `stage_result` do job e alimenta o próximo.
AGENT_STAGES: dict[str, list[dict]] = {
    "ops": [
        {"name": "research", "prompt_template": "{prompt}\n\n--- CONTEXTO ---\n{context}\n\n--- TAREFA ---\nFaça uma pesquisa completa e estruturada sobre o tema acima. Retorne apenas os achados principais em formato de tópicos organizados."},
        {"name": "draft", "prompt_template": "{prompt}\n\n--- PESQUISA (etapa anterior) ---\n{context}\n\n--- TAREFA ---\nCom base na pesquisa, produza o entregável final (relatório, plano, código, etc.). Seja completo e acionável."},
        {"name": "review", "prompt_template": "{prompt}\n\n--- ENTREGÁVEL (etapa anterior) ---\n{context}\n\n--- TAREFA ---\nRevise criticamente o entregável. Liste problemas, melhorias e aprove se estiver pronto. Se não, diga o que falta."},
    ],
    "projects": [
        {"name": "plan", "prompt_template": "{prompt}\n\n--- CONTEXTO ---\n{context}\n\n--- TAREFA ---\nCrie um plano de projeto estruturado: objetivos, marcos, tarefas, riscos, responsáveis."},
        {"name": "breakdown", "prompt_template": "{prompt}\n\n--- PLANO (etapa anterior) ---\n{context}\n\n--- TAREFA ---\nQuebre o plano em tickets acionáveis para a esteira (título, descrição, prioridade, agente sugerido)."},
    ],
    "community": [
        {"name": "analyze", "prompt_template": "{prompt}\n\n--- CONTEXTO ---\n{context}\n\n--- TAREFA ---\nAnalise o pulso da comunidade: sentimentos, temas quentes, perguntas frequentes, oportunidades."},
        {"name": "respond", "prompt_template": "{prompt}\n\n--- ANÁLISE (etapa anterior) ---\n{context}\n\n--- TAREFA ---\nProponha ações de engajamento, respostas prioritárias e conteúdo para os próximos dias."},
    ],
    # Agentes genéricos usam fallback simples
    "default": [
        {"name": "execute", "prompt_template": "{prompt}\n\n--- CONTEXTO ---\n{context}\n\n--- TAREFA ---\nExecute a tarefa descrita acima da melhor forma possível."},
    ],
}

# Timeout por job (total) — mais curto que o default do fallback para Telegram
DEFAULT_JOB_TIMEOUT = int(os.environ.get("ORCHESTRATION_JOB_TIMEOUT", "300"))  # 5 min


# ── Worker principal ────────────────────────────────────────────────────

class OrchestrationWorker:
    def __init__(self, app, poll_interval: int = 5):
        self.app = app
        self.poll_interval = poll_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._current_job_id: Optional[str] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("[orchestration] Worker já está rodando")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="orchestration-worker", daemon=True)
        self._thread.start()
        logger.info("[orchestration] Worker iniciado")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        logger.info("[orchestration] Worker parado")

    def _run(self) -> None:
        """Loop principal: a cada poll_interval, checa por jobs pendentes."""
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    self._process_next_job()
            except Exception as exc:
                logger.exception(f"[orchestration] Erro no loop do worker: {exc}")
            # Sleep com interrupção responsiva
            for _ in range(self.poll_interval * 2):
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)

    def _process_next_job(self) -> None:
        """Pega o próximo job pendente e processa até o fim (ou falha)."""
        job = OrchestrationJob.query.filter_by(status="pending").order_by(OrchestrationJob.created_at.asc()).first()
        if not job:
            return

        self._current_job_id = job.id
        logger.info(f"[orchestration] Iniciando job {job.id} (agente={job.agent})")

        try:
            # Marca como running
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db.session.commit()

            # Executa as etapas
            stages = AGENT_STAGES.get(job.agent, AGENT_STAGES["default"])
            context = ""  # contexto acumulado entre estágios

            for i, stage in enumerate(stages):
                if self._stop_event.is_set():
                    break

                # Cancelamento pedido pelo humano enquanto o job já rodava.
                # `POST /cancel` só grava `status='cancelled'` na linha — sem
                # esta releitura entre etapas, o worker seguia até o fim e
                # sobrescrevia com 'success'. O cancelamento aparecia na API
                # por alguns segundos e depois sumia sozinho: a pior forma de
                # falhar, porque o humano vê o pedido ser aceito e ignorado.
                db.session.refresh(job)
                if job.status == "cancelled":
                    logger.info(f"[orchestration] Job {job.id} cancelado — parando antes da etapa {stage['name']}")
                    return

                stage_name = stage["name"]
                job.stage = stage_name
                job.updated_at = datetime.now(timezone.utc)
                db.session.commit()

                logger.info(f"[orchestration] Job {job.id} → etapa {stage_name} ({i+1}/{len(stages)})")

                # Monta prompt da etapa com contexto acumulado
                prompt = stage["prompt_template"].format(prompt=job.prompt, context=context or "(nenhum)")

                # Executa via fallback engine (resiliente, com rotação de providers)
                result = invoke_with_fallback(
                    prompt=prompt,
                    max_turns=10,
                    timeout_seconds=DEFAULT_JOB_TIMEOUT,
                    agent=job.agent,
                    per_attempt_timeout_cap=PER_ATTEMPT_TIMEOUT_CAP,
                )

                if result.get("status") == "success":
                    output = result.get("output", "").strip()
                    context = output  # passa para próxima etapa
                    job.stage_result = output
                    job.updated_at = datetime.now(timezone.utc)
                    db.session.commit()
                    logger.info(f"[orchestration] Job {job.id} etapa {stage_name} OK ({len(output)} chars)")
                else:
                    # Falha na etapa — marca job como failed e para
                    error = result.get("error", "Erro desconhecido")
                    job.status = "failed"
                    job.error = f"Etapa '{stage_name}': {error}"
                    job.completed_at = datetime.now(timezone.utc)
                    db.session.commit()
                    logger.error(f"[orchestration] Job {job.id} FALHOU na etapa {stage_name}: {error}")
                    return

            # Uma última checagem: o cancelamento pode ter chegado durante a
            # chamada de modelo da etapa final, que é justamente a mais longa.
            db.session.refresh(job)
            if job.status == "cancelled":
                logger.info(f"[orchestration] Job {job.id} cancelado na última etapa — não marca sucesso")
                return

            # Todas etapas completaram com sucesso
            job.status = "success"
            job.stage = "done"
            job.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.info(f"[orchestration] Job {job.id} CONCLUÍDO com sucesso")

        except Exception as exc:
            logger.exception(f"[orchestration] Job {job.id} erro inesperado: {exc}")
            # Já estamos dentro do app_context aberto por `_run` — abrir outro
            # aqui empilhava contexto à toa. O que este bloco precisa de fato é
            # desfazer a sessão: se o erro veio de um commit, a sessão está em
            # estado inválido e o commit seguinte (o que grava 'failed') falha
            # também, deixando o job preso em 'running' para sempre.
            job_id = job.id
            db.session.rollback()
            try:
                job = OrchestrationJob.query.get(job_id)
                if job and job.status not in ("success", "failed", "cancelled"):
                    job.status = "failed"
                    job.error = f"Erro interno: {exc}"
                    job.completed_at = datetime.now(timezone.utc)
                    db.session.commit()
            except Exception:  # noqa: BLE001
                logger.exception(f"[orchestration] não consegui marcar {job_id} como failed")
        finally:
            self._current_job_id = None


# ── Função de conveniência para execução síncrona (testes, CLI) ──────────

def run_orchestration_job(job: OrchestrationJob) -> dict:
    """Executa um job completo de forma síncrona (para testes ou CLI direto).

    Retorna dict com status/output/error igual ao invoke_with_fallback.
    """
    stages = AGENT_STAGES.get(job.agent, AGENT_STAGES["default"])
    context = ""

    for stage in stages:
        prompt = stage["prompt_template"].format(prompt=job.prompt, context=context or "(nenhum)")
        result = invoke_with_fallback(
            prompt=prompt,
            max_turns=10,
            timeout_seconds=DEFAULT_JOB_TIMEOUT,
            agent=job.agent,
            per_attempt_timeout_cap=PER_ATTEMPT_TIMEOUT_CAP,
        )
        if result.get("status") != "success":
            return result
        context = result.get("output", "").strip()

    return {"status": "success", "output": context, "error": None, "duration_ms": 0}


# ── Inicialização no Flask app ──────────────────────────────────────────

_worker_instance: Optional[OrchestrationWorker] = None


def start_orchestration_worker(app) -> OrchestrationWorker:
    """Inicializa e inicia o worker de orquestração no contexto do Flask app.

    Deve ser chamado uma vez no startup (ex: no app.py após create_app).
    """
    global _worker_instance
    if _worker_instance:
        return _worker_instance
    _worker_instance = OrchestrationWorker(app)
    _worker_instance.start()
    return _worker_instance


def stop_orchestration_worker() -> None:
    global _worker_instance
    if _worker_instance:
        _worker_instance.stop()
        _worker_instance = None


# ── CLI direto ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Rodar de dentro de dashboard/backend: python chat_orchestrator.py <job_id>
    import argparse

    # `app.py` não expõe factory — o Flask app é criado no nível do módulo.
    # A versão anterior importava `create_app`, que nunca existiu: este CLI
    # falhava com ImportError na primeira linha, sempre.
    from app import app  # noqa: E402

    parser = argparse.ArgumentParser(description="Processa um job de orquestração específico")
    parser.add_argument("job_id", help="ID do job a processar")
    args = parser.parse_args()

    with app.app_context():
        job = OrchestrationJob.query.get(args.job_id)
        if not job:
            print(f"Job {args.job_id} não encontrado", file=sys.stderr)
            sys.exit(1)
        result = run_orchestration_job(job)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("status") == "success" else 1)