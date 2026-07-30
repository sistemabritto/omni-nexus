#!/usr/bin/env python3
"""media-worker — polling loop that claims queued MediaJobs via the dashboard
API and runs the CPU-heavy pipeline (OpenCode composition -> HyperFrames
render -> ffprobe validation) locally, in this isolated container.

Never touches the SQLite DB directly. Like the scheduler/telegram services,
it talks to the dashboard exclusively through DASHBOARD_API_TOKEN +
/api/media/jobs/* (see dashboard/backend/routes/media_jobs.py) — a single
source of truth for state transitions (the state machine is enforced
server-side), matching the existing service-to-service pattern in this
project (no service other than the dashboard itself mounts the SQLite
volume).

Concurrency: exactly one job in flight per process (briefing Etapa 3), and
`replicas: 1` at the Swarm level makes that also the cluster-wide ceiling.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sdk_client import evo  # noqa: E402
from media_executor import run_opencode_media_job, MediaExecutionError  # noqa: E402
from media_render import render_composition, run_doctor, RenderError  # noqa: E402
from media_validation import validate_mp4, extract_metadata, ValidationError  # noqa: E402
from media_manifest import load_and_validate_manifest, ManifestValidationError  # noqa: E402
from media_workspace import job_dir, media_workspace_root, sha256_file  # noqa: E402
from media_audio import primeiro_corte, aplicar_corte_editorial, FalhaDeMidia  # noqa: E402
from transcricao import extrair_audio_16k, transcrever, transcrever_palavras  # noqa: E402
from corte_editorial import propor_cortes, gerar_pagina_revisao  # noqa: E402
from cortes_virais import propor_cortes_virais, renderizar_corte_viral  # noqa: E402

POLL_SECONDS = float(os.environ.get("MEDIA_WORKER_POLL_SECONDS", "10"))
JOB_TIMEOUT_SECONDS = int(os.environ.get("MEDIA_JOB_TIMEOUT_SECONDS", "3600"))
MAX_FILE_SIZE_BYTES = int(os.environ.get("MEDIA_MAX_FILE_SIZE_BYTES", str(1024 * 1024 * 1024)))
HEARTBEAT_FILE = Path(os.environ.get("MEDIA_WORKER_HEARTBEAT_FILE", "/tmp/media-worker.alive"))
AGENT_NAME = "media-worker"


def _touch_heartbeat() -> None:
    try:
        HEARTBEAT_FILE.write_text(str(time.time()))
    except OSError:
        pass


def _patch(job_id: str, **fields) -> dict:
    return evo.patch(f"/api/media/jobs/{job_id}", fields)


def _fail_job(job_id: str, error: str, terminal: bool = False) -> None:
    status = "failed" if terminal else "retryable_failure"
    try:
        _patch(job_id, status=status, last_error=error[:4000])
    except Exception:
        print(f"[media-worker] could not report failure for {job_id}: {traceback.format_exc()}", flush=True)


def _claim_next_job() -> dict | None:
    """Try queued jobs first, then jobs eligible for automatic retry.
    `/run` is the atomic claim (mirrors tickets.checkout_ticket) — if another
    process (or a human clicking "Iniciar") wins the race, `/run` 409s and we
    just move on to the next candidate.
    """
    for status in ("queued", "retryable_failure"):
        try:
            jobs = evo.get("/api/media/jobs", params={"status": status, "limit": 5})
        except Exception:
            print(f"[media-worker] failed to list {status} jobs: {traceback.format_exc()}", flush=True)
            continue
        for job in jobs or []:
            try:
                return evo.post(f"/api/media/jobs/{job['id']}/run", {"agent": AGENT_NAME})
            except Exception:
                continue
    return None


def process_job(job: dict) -> None:
    job_type = job.get("job_type") or "social_clip"
    if job_type == "corte_bruto":
        process_corte_bruto_job(job)
    elif job_type == "corte_editorial":
        process_corte_editorial_job(job)
    elif job_type == "aplicar_corte_editorial":
        process_aplicar_corte_editorial_job(job)
    elif job_type == "cortes_virais":
        process_cortes_virais_job(job)
    else:
        process_social_clip_job(job)


def _resolve_source_video(job: dict, base: Path) -> Path | None:
    """corte_bruto's input: an explicit `source_path` (already reachable
    inside this container), or fall back to whatever landed in the job's
    own input/ dir under the name `source.*` (e.g. dropped there by scp/ops
    after POST /api/media/jobs returned the job_id).
    """
    source_path = job.get("source_path")
    if source_path:
        p = Path(source_path)
        return p if p.is_file() else None
    for candidate in sorted((base / "input").glob("source.*")):
        if candidate.is_file():
            return candidate
    return None


def process_corte_bruto_job(job: dict) -> None:
    """Fase 1A da esteira de vídeo: extrair áudio -> denoise em blocos ->
    loudnorm 2 passes -> remux -> cortar silêncio -> concatenar. Sem
    OpenCode, sem Postiz — o resultado fica em ready_for_review para a
    aprovação humana da Fase 1B decidir o corte editorial.
    """
    job_id = job["id"]
    base = job_dir(job_id)
    print(f"[media-worker] processing corte_bruto job {job_id}", flush=True)

    source = _resolve_source_video(job, base)
    if source is None:
        _fail_job(
            job_id,
            f"Vídeo de origem não encontrado (source_path={job.get('source_path')!r}, "
            f"nem input/source.* em {base / 'input'})",
            terminal=True,
        )
        return

    inicio = time.monotonic()

    def progresso(etapa: str, detalhe: str = "") -> None:
        minutos = (time.monotonic() - inicio) / 60
        msg = f"[{minutos:.1f} min] {etapa} {detalhe}".rstrip()
        print(f"[media-worker] {job_id}: {msg}", flush=True)
        try:
            _patch(job_id, progress_message=msg)
        except Exception:
            pass

    try:
        origem_meta = extract_metadata(source)
    except ValidationError as exc:
        _fail_job(job_id, f"Vídeo de origem inválido: {exc}", terminal=True)
        return

    _patch(job_id, status="generating")
    output_path = base / "output" / "final.mp4"
    trabalho = base / "work"
    trabalho.mkdir(parents=True, exist_ok=True)
    try:
        resultado = primeiro_corte(source, output_path, trabalho=trabalho, progresso=progresso)
    except FalhaDeMidia as exc:
        _fail_job(job_id, f"Corte bruto falhou: {exc}")
        return

    # `generating` só permite ir para `rendering` na máquina de estados —
    # primeiro_corte já produziu o arquivo final, então isso é só o registro
    # formal de que a etapa de "render" (corte+concat) terminou.
    _patch(job_id, status="rendering")
    _patch(job_id, status="validating")
    try:
        meta = validate_mp4(
            output_path,
            expected_width=origem_meta.width, expected_height=origem_meta.height,
            expected_duration_seconds=float(resultado["duracao_final_s"]),
            expected_fps=round(origem_meta.fps),
            max_size_bytes=MAX_FILE_SIZE_BYTES, workspace_root=media_workspace_root(),
        )
    except ValidationError as exc:
        _fail_job(job_id, f"Validação falhou: {exc}")
        return

    checksum = sha256_file(output_path)
    _patch(
        job_id, status="ready_for_review", render_path=str(output_path), render_sha256=checksum,
        result_json=json.dumps(resultado, ensure_ascii=False), progress_message="concluído", **meta.to_dict(),
    )
    print(f"[media-worker] corte_bruto job {job_id} ready_for_review (sha256={checksum[:12]}...)", flush=True)


def process_corte_editorial_job(job: dict) -> None:
    """Fase 1B da esteira de vídeo: transcreve o vídeo já cortado (1A),
    propõe trechos adicionais a cortar (julgamento — via modelo, nunca
    Python puro) e publica uma página de revisão em /shares. Não corta nada
    sozinho: o corte real só acontece depois que um humano aprova a lista
    (ver .claude/rules/esteira-de-conteudo.md — mesma regra de gate da
    esteira de conteúdo).
    """
    job_id = job["id"]
    base = job_dir(job_id)
    print(f"[media-worker] processing corte_editorial job {job_id}", flush=True)

    source = _resolve_source_video(job, base)
    if source is None:
        _fail_job(
            job_id,
            f"Vídeo de origem não encontrado (source_path={job.get('source_path')!r}, "
            f"nem input/source.* em {base / 'input'})",
            terminal=True,
        )
        return

    inicio = time.monotonic()

    def progresso(etapa: str, detalhe: str = "") -> None:
        minutos = (time.monotonic() - inicio) / 60
        msg = f"[{minutos:.1f} min] {etapa} {detalhe}".rstrip()
        print(f"[media-worker] {job_id}: {msg}", flush=True)
        try:
            _patch(job_id, progress_message=msg)
        except Exception:
            pass

    _patch(job_id, status="generating")
    trabalho = base / "work"
    trabalho.mkdir(parents=True, exist_ok=True)

    try:
        audio_16k = extrair_audio_16k(source, trabalho / "audio16k.wav")
        segmentos = transcrever(audio_16k, trabalho=trabalho / "transcricao", progresso=progresso)
        audio_16k.unlink(missing_ok=True)
    except FalhaDeMidia as exc:
        _fail_job(job_id, f"Transcrição falhou: {exc}")
        return

    progresso("propondo_cortes", f"{len(segmentos)} blocos transcritos")
    try:
        cortes = propor_cortes(segmentos, cwd=base)
    except Exception as exc:
        _fail_job(job_id, f"Proposta de corte falhou: {exc}")
        return

    duracao_total = segmentos[-1].fim if segmentos else 0.0
    pagina = gerar_pagina_revisao(titulo=job.get("title") or job_id, cortes=cortes, duracao_original_s=duracao_total)
    output_dir = base / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    pagina_path = output_dir / "revisao.html"
    pagina_path.write_text(pagina, encoding="utf-8")

    # Caminho relativo à raiz do repo (REPO_ROOT em routes/shares.py) — é o
    # que /api/shares exige, e media/ é uma das duas raízes que ele aceita
    # (ver o comentário de MEDIA_WORKSPACE_DIR em routes/shares.py).
    caminho_relativo = f"media/jobs/{job_id}/output/revisao.html"
    try:
        share = evo.post("/api/shares", {"path": caminho_relativo, "expires_in": None})
        link = share.get("url", "")
    except Exception as exc:
        print(f"[media-worker] {job_id}: falha ao criar share: {exc}", flush=True)
        link = ""

    try:
        evo.post("/api/tickets", {
            "title": f"Aprovar corte editorial — {job.get('title') or job_id}",
            "description": (
                f"{len(cortes)} trecho(s) propostos pra corte, "
                f"revisão: {link or '(share falhou, ver logs do worker)'}\n\n"
                f"job_id: {job_id}"
            ),
            "priority": "medium",
        })
    except Exception as exc:
        print(f"[media-worker] {job_id}: falha ao criar ticket: {exc}", flush=True)

    # generating só permite ir pra rendering na máquina de estados — não há
    # "render" de fato aqui (o output é uma página, não vídeo), é só o
    # registro formal exigido pra chegar em ready_for_review (mesma nota do
    # corte_bruto, acima).
    _patch(job_id, status="rendering")
    _patch(job_id, status="validating")
    _patch(
        job_id, status="ready_for_review", progress_message="concluído",
        result_json=json.dumps({
            "cortes": cortes, "duracao_original_s": round(duracao_total, 2),
            "pagina_revisao": caminho_relativo, "share_url": link,
        }, ensure_ascii=False),
    )
    print(f"[media-worker] corte_editorial job {job_id} ready_for_review ({len(cortes)} cortes propostos)", flush=True)


def process_aplicar_corte_editorial_job(job: dict) -> None:
    """Executa o corte que já foi aprovado por um humano — a lista de
    trechos vem de `job["result"]["cortes"]`, gravada na criação do job
    (ver routes/media_jobs.py). Nunca decide o que cortar aqui, só aplica.
    """
    job_id = job["id"]
    base = job_dir(job_id)
    print(f"[media-worker] processing aplicar_corte_editorial job {job_id}", flush=True)

    source = _resolve_source_video(job, base)
    if source is None:
        _fail_job(
            job_id,
            f"Vídeo de origem não encontrado (source_path={job.get('source_path')!r})",
            terminal=True,
        )
        return

    cortes = ((job.get("result") or {}).get("cortes")) or []
    if not cortes:
        _fail_job(job_id, "job sem 'cortes' aprovados em result_json", terminal=True)
        return

    try:
        origem_meta = extract_metadata(source)
    except ValidationError as exc:
        _fail_job(job_id, f"Vídeo de origem inválido: {exc}", terminal=True)
        return

    inicio = time.monotonic()

    def progresso(etapa: str, detalhe: str = "") -> None:
        minutos = (time.monotonic() - inicio) / 60
        msg = f"[{minutos:.1f} min] {etapa} {detalhe}".rstrip()
        print(f"[media-worker] {job_id}: {msg}", flush=True)
        try:
            _patch(job_id, progress_message=msg)
        except Exception:
            pass

    _patch(job_id, status="generating")
    output_path = base / "output" / "final.mp4"
    (base / "output").mkdir(parents=True, exist_ok=True)
    try:
        resultado = aplicar_corte_editorial(source, cortes, output_path, progresso=progresso)
    except FalhaDeMidia as exc:
        _fail_job(job_id, f"Corte editorial falhou: {exc}")
        return

    _patch(job_id, status="rendering")
    _patch(job_id, status="validating")
    try:
        meta = validate_mp4(
            output_path,
            expected_width=origem_meta.width, expected_height=origem_meta.height,
            expected_duration_seconds=float(resultado["duracao_final_s"]),
            expected_fps=round(origem_meta.fps),
            max_size_bytes=MAX_FILE_SIZE_BYTES, workspace_root=media_workspace_root(),
        )
    except ValidationError as exc:
        _fail_job(job_id, f"Validação falhou: {exc}")
        return

    checksum = sha256_file(output_path)
    _patch(
        job_id, status="ready_for_review", render_path=str(output_path), render_sha256=checksum,
        result_json=json.dumps(resultado, ensure_ascii=False), progress_message="concluído", **meta.to_dict(),
    )
    print(f"[media-worker] aplicar_corte_editorial job {job_id} ready_for_review (sha256={checksum[:12]}...)", flush=True)


def process_cortes_virais_job(job: dict) -> None:
    """Fase 1C: transcreve por palavra, o modelo escolhe até N trechos que
    funcionam como corte curto independente (julgamento — via modelo), e
    cada um é renderizado em 9:16 com legenda karaokê e zoom (determinístico,
    ffmpeg puro). Cria um ticket de revisão em vez de publicar sozinho —
    mesma regra de gate do resto da esteira: o worker produz candidatos,
    nunca decide o que vai ao ar.
    """
    job_id = job["id"]
    base = job_dir(job_id)
    print(f"[media-worker] processing cortes_virais job {job_id}", flush=True)

    source = _resolve_source_video(job, base)
    if source is None:
        _fail_job(
            job_id,
            f"Vídeo de origem não encontrado (source_path={job.get('source_path')!r}, "
            f"nem input/source.* em {base / 'input'})",
            terminal=True,
        )
        return

    inicio = time.monotonic()

    def progresso(etapa: str, detalhe: str = "") -> None:
        minutos = (time.monotonic() - inicio) / 60
        msg = f"[{minutos:.1f} min] {etapa} {detalhe}".rstrip()
        print(f"[media-worker] {job_id}: {msg}", flush=True)
        try:
            _patch(job_id, progress_message=msg)
        except Exception:
            pass

    _patch(job_id, status="generating")
    trabalho = base / "work"
    trabalho.mkdir(parents=True, exist_ok=True)

    try:
        audio_16k = extrair_audio_16k(source, trabalho / "audio16k.wav")
        palavras = transcrever_palavras(audio_16k, trabalho=trabalho / "transcricao", progresso=progresso)
        audio_16k.unlink(missing_ok=True)
    except FalhaDeMidia as exc:
        _fail_job(job_id, f"Transcrição por palavra falhou: {exc}")
        return

    if not palavras:
        _fail_job(job_id, "transcrição não devolveu nenhuma palavra", terminal=True)
        return

    progresso("propondo_cortes_virais", f"{len(palavras)} palavras transcritas")
    max_cortes = int(job.get("platform_settings", {}).get("max_cortes", 10)) if isinstance(job.get("platform_settings"), dict) else 10
    try:
        cortes = propor_cortes_virais(palavras, cwd=base, max_cortes=max_cortes)
    except Exception as exc:
        _fail_job(job_id, f"Proposta de cortes virais falhou: {exc}")
        return

    if not cortes:
        _patch(
            job_id, status="ready_for_review", progress_message="concluído",
            result_json=json.dumps({"cortes": []}, ensure_ascii=False),
        )
        print(f"[media-worker] cortes_virais job {job_id}: nenhum trecho se qualificou", flush=True)
        return

    _patch(job_id, status="rendering")
    output_dir = base / "output" / "virais"
    output_dir.mkdir(parents=True, exist_ok=True)

    resultados = []
    for i, corte in enumerate(cortes):
        progresso("renderizando", f"corte {i + 1} de {len(cortes)}")
        destino = output_dir / f"corte{i:02d}.mp4"
        trabalho_corte = trabalho / f"corte{i:02d}"
        try:
            info = renderizar_corte_viral(source, corte, palavras, destino, trabalho=trabalho_corte, progresso=progresso)
        except FalhaDeMidia as exc:
            print(f"[media-worker] {job_id}: corte {i} falhou, pulando: {exc}", flush=True)
            continue

        caminho_relativo = f"media/jobs/{job_id}/output/virais/corte{i:02d}.mp4"
        try:
            share = evo.post("/api/shares", {"path": caminho_relativo, "expires_in": None})
            info["share_url"] = share.get("url", "")
        except Exception as exc:
            print(f"[media-worker] {job_id}: falha ao criar share do corte {i}: {exc}", flush=True)
            info["share_url"] = ""
        info["arquivo"] = caminho_relativo
        resultados.append(info)

    _patch(job_id, status="validating")

    if not resultados:
        _fail_job(job_id, "modelo propôs cortes mas nenhum renderizou com sucesso")
        return

    linhas_ticket = "\n".join(
        f"- {r['titulo']} ({r['duracao_s']:.0f}s): {r.get('share_url') or '(share falhou)'}"
        for r in resultados
    )
    try:
        evo.post("/api/tickets", {
            "title": f"Aprovar cortes virais — {job.get('title') or job_id}",
            "description": f"{len(resultados)} corte(s) renderizados:\n\n{linhas_ticket}\n\njob_id: {job_id}",
            "priority": "medium",
        })
    except Exception as exc:
        print(f"[media-worker] {job_id}: falha ao criar ticket: {exc}", flush=True)

    _patch(
        job_id, status="ready_for_review", progress_message="concluído",
        result_json=json.dumps({"cortes": resultados}, ensure_ascii=False),
    )
    print(f"[media-worker] cortes_virais job {job_id} ready_for_review ({len(resultados)} corte(s) renderizados)", flush=True)


def process_social_clip_job(job: dict) -> None:
    job_id = job["id"]
    base = job_dir(job_id)
    print(f"[media-worker] processing job {job_id} ({job.get('platform')}, {job.get('width')}x{job.get('height')})", flush=True)

    # ── 1. Composition via OpenCode/OmniRoute (never a direct model call) ──
    _patch(job_id, status="generating")
    try:
        run_opencode_media_job(base, timeout_seconds=min(JOB_TIMEOUT_SECONDS, 1800))
    except MediaExecutionError as exc:
        try:
            (base / "logs" / "opencode.ndjson").write_text(
                json.dumps(exc.result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        _fail_job(job_id, f"Composição falhou: {exc}")
        return

    # ── 2. Schema-validate the manifest the agent produced ─────────────
    try:
        load_and_validate_manifest(base)
    except ManifestValidationError as exc:
        _fail_job(job_id, f"Manifesto inválido: {exc}")
        return

    # ── 3. Deterministic render — worker-driven, never the agent ───────
    _patch(job_id, status="rendering")
    output_path = base / "output" / "final.mp4"
    try:
        render_composition(
            base / "project", output_path,
            fps=int(job["fps"]), quality="high", timeout_seconds=min(JOB_TIMEOUT_SECONDS, 1800),
        )
    except RenderError as exc:
        try:
            (base / "logs" / "render.log").write_text(exc.log, encoding="utf-8")
        except OSError:
            pass
        _fail_job(job_id, f"Render falhou: {exc}")
        return

    # ── 4. ffprobe validation — never trust exit 0 alone ────────────────
    _patch(job_id, status="validating")
    try:
        meta = validate_mp4(
            output_path,
            expected_width=int(job["width"]), expected_height=int(job["height"]),
            expected_duration_seconds=float(job["duration_seconds"]), expected_fps=int(job["fps"]),
            max_size_bytes=MAX_FILE_SIZE_BYTES, workspace_root=media_workspace_root(),
        )
    except ValidationError as exc:
        _fail_job(job_id, f"Validação falhou: {exc}")
        return

    checksum = sha256_file(output_path)
    _patch(job_id, status="ready_for_review", render_path=str(output_path), render_sha256=checksum, **meta.to_dict())
    print(f"[media-worker] job {job_id} ready_for_review (sha256={checksum[:12]}...)", flush=True)


def main() -> None:
    print(f"[media-worker] started, polling every {POLL_SECONDS}s (job timeout {JOB_TIMEOUT_SECONDS}s)", flush=True)
    doctor = run_doctor(Path.cwd())
    print(f"[media-worker] hyperframes doctor ok={doctor['ok']}", flush=True)
    while True:
        _touch_heartbeat()
        try:
            job = _claim_next_job()
        except Exception:
            print(f"[media-worker] poll error: {traceback.format_exc()}", flush=True)
            job = None
        if job is None:
            time.sleep(POLL_SECONDS)
            continue
        try:
            process_job(job)
        except Exception:
            print(f"[media-worker] unhandled error processing {job.get('id')}: {traceback.format_exc()}", flush=True)
            try:
                _fail_job(job["id"], f"Erro inesperado: {traceback.format_exc()[-2000:]}")
            except Exception:
                pass


if __name__ == "__main__":
    main()
