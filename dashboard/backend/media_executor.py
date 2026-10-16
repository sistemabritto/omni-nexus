"""OpenCodeMediaExecutor — runs OpenCode (via OmniRoute) against a MediaJob's
isolated workspace to produce a HyperFrames composition + publication manifest.

Deliberately thin: all subprocess mechanics (env allowlist/denylist, timeout +
process-group SIGKILL, cross-platform lock semantics, NDJSON parsing, provider
fallback chain) live in provider_fallback.py and are reused as-is (ADR-5 in
workspace/development/features/social-media-production/[C]architecture-*.md)
— this module only builds the prompt and interprets the result.

The OpenCode process NEVER performs the final render or ffprobe validation
(briefing Etapa 6): those are deterministic steps the worker runs itself
after this function returns, via media_render.py. This function's only job
is getting the agent to produce ./project (the composition) and
./output/publication_manifest.json inside the job's isolated workspace.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from provider_fallback import invoke_with_fallback

# Hard ceiling regardless of caller-provided timeout — MEDIA_JOB_TIMEOUT_SECONDS
# governs the whole job (composition + render + validation + upload); the
# composition step alone must leave room for the rest.
MAX_COMPOSITION_TIMEOUT_SECONDS = 1800
REQUIRED_SKILL_DOCUMENTS = (
    '.claude/skills/social-media-production/SKILL.md',
    '.claude/skills/hyperframes/SKILL.md',
)


def _skill_preflight(job_workspace: Path) -> dict:
    """Verify the scoped read pointers before any potentially paid invocation.

    The existing scaffold deliberately links this catalog outside the job.
    Read only these fixed documents; never install/fetch a missing skill or
    claim that availability proves the model read/applied its instructions.
    """
    documents = []
    for relative in REQUIRED_SKILL_DOCUMENTS:
        try:
            with (job_workspace / relative).open('rb') as stream:
                data = stream.read(131073)
            text = data.decode('utf-8')
            if not text.strip() or len(data) > 131072:
                raise ValueError('empty or oversized document')
        except (OSError, UnicodeError, ValueError) as exc:
            raise MediaExecutionError(
                f'Skill de produção indisponível: {relative}',
                result={'status': 'fail', 'stage': 'skill_preflight',
                        'document': relative, 'model_invoked': False},
            ) from exc
        documents.append({'path': relative, 'sha256': hashlib.sha256(data).hexdigest()})
    return {'status': 'documents_available', 'documents': documents,
            'model_read_status': 'not_verified', 'application_status': 'not_verified'}


class MediaExecutionError(Exception):
    """Raised when OpenCode fails to produce a usable composition step.

    Carries the raw provider_fallback result dict so callers can persist
    `last_error`/`attempt_count` on the MediaJob without re-deriving it.
    """

    def __init__(self, message: str, result: dict | None = None):
        super().__init__(message)
        self.result = result or {}


def build_composition_prompt(manifest_relpath: str) -> str:
    """The prompt intentionally references a manifest FILE PATH, never inlines
    the brief/brand assets/secrets (briefing Etapa 6: 'O prompt do OpenCode
    deve apontar para arquivos de manifesto, em vez de incluir grandes
    quantidades de dados e segredos na linha de comando').
    """
    return (
        "Você está operando dentro do workspace isolado deste job de produção de mídia social. "
        f"Leia o manifesto de entrada em '{manifest_relpath}' (caminho relativo ao seu diretório de "
        "trabalho atual — não é um caminho absoluto do host).\n\n"
        "Leia '.claude/skills/social-media-production/SKILL.md' do início ao fim; "
        "esse é o contrato local deste job. Para selecionar o workflow, leia "
        "'.claude/skills/hyperframes/SKILL.md' e os documentos locais pertinentes. "
        "Se não puder ler uma referência necessária, reporte a lacuna sem instalar nada "
        "ou alegar aplicação da skill.\n"
        "1. Leia o manifesto do job e o contexto de projeto/campanha nele referenciado.\n"
        "2. Leia a identidade visual disponível em './input/brand/' (se houver).\n"
        "3. Selecione a skill HyperFrames apropriada para o formato/plataforma pedidos.\n"
        "4. Crie o projeto da composição em './project/' (diretório isolado deste job).\n"
        "5. Use apenas os assets disponíveis em './input/assets/' e './input/brand/' — nunca busque "
        "mídia externa.\n"
        "6. Respeite resolução, duração e fps exatos declarados no manifesto; produza legendas "
        "legíveis em celular quando houver texto na tela.\n"
        "7. NÃO renderize o vídeo final e NÃO rode ffprobe — o worker faz isso depois, de forma "
        "determinística.\n"
        "8. Produza './output/publication_manifest.json' de acordo com o schema documentado na "
        "skill.\n"
        "9. Encerre sem publicar nada e sem jamais buscar ou usar credenciais do Postiz.\n"
    )


def run_opencode_media_job(
    job_workspace: Path,
    *,
    manifest_relpath: str = "input/job.json",
    timeout_seconds: int = 900,
    force_provider: str | None = None,
    force_model: str | None = None,
) -> dict:
    """Invoke OpenCode (via the OmniRoute-backed provider chain) to produce the
    composition + publication_manifest.json for one MediaJob.

    Returns the raw provider_fallback result dict on status="success". Raises
    MediaExecutionError otherwise — callers decide the MediaJob state
    transition (usually -> retryable_failure, or -> failed after enough
    attempts).
    """
    job_workspace = Path(job_workspace).resolve()
    manifest_path = job_workspace / manifest_relpath
    if not manifest_path.is_file():
        raise MediaExecutionError(f"Manifesto de entrada não encontrado: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("esperado objeto JSON")
    except (ValueError, UnicodeError) as exc:
        raise MediaExecutionError(f"Manifesto de entrada inválido: {exc}") from exc

    effective_timeout = min(int(timeout_seconds), MAX_COMPOSITION_TIMEOUT_SECONDS)
    skill_evidence = _skill_preflight(job_workspace)
    prompt = build_composition_prompt(manifest_relpath)

    result = invoke_with_fallback(
        prompt=prompt,
        timeout_seconds=effective_timeout,
        agent="",  # no .claude/agents persona — the social-media-production skill IS the instructions
        force_provider=force_provider,
        force_model=force_model,
        cwd=job_workspace,
    )
    result = {**result, 'skill_preflight': skill_evidence}

    status = result.get("status")
    if status != "success":
        raise MediaExecutionError(
            f"OpenCode falhou ao gerar a composição (status={status}): {result.get('error')}",
            result=result,
        )

    manifest_output = job_workspace / "output" / "publication_manifest.json"
    if not manifest_output.is_file():
        raise MediaExecutionError(
            "OpenCode terminou com sucesso mas não produziu output/publication_manifest.json.",
            result=result,
        )

    return result
