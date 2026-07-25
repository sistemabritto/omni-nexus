#!/usr/bin/env python3
"""Verificação ponta a ponta do pipeline de agendamento via Postiz.

Objetivo 1 (2026-07-25). Roda a cadeia inteira — configuração → autenticação →
integrações conectadas → payload por plataforma → agendamento real →
confirmação — e diz exatamente em que elo ela quebra. Existe porque "está
funcionando" sem evidência foi justamente a falha que originou o gate de
publicação (ADR SPEC 3f).

Uso:
    python scripts/verify_postiz_pipeline.py                  # só leitura (seguro)
    python scripts/verify_postiz_pipeline.py --platform x     # foca numa plataforma
    python scripts/verify_postiz_pipeline.py --live-schedule  # AGENDA um post de teste real

Sem --live-schedule nada é escrito no Postiz: o script só lê integrações e
valida payloads localmente. Com --live-schedule ele cria UM post agendado para
daqui a 24h (conteúdo marcado como teste) e confirma que entrou na fila —
use para provar o caminho completo antes de confiar o calendário editorial a ele.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

OK, FAIL, WARN, INFO = "\033[92m✓\033[0m", "\033[91m✗\033[0m", "\033[93m!\033[0m", "·"


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Report:
    def __init__(self) -> None:
        self.failed = False

    def ok(self, msg: str) -> None:
        print(f"  {OK} {msg}")

    def fail(self, msg: str, fix: str = "") -> None:
        self.failed = True
        print(f"  {FAIL} {msg}")
        if fix:
            print(f"      → {fix}")

    def warn(self, msg: str) -> None:
        print(f"  {WARN} {msg}")

    def info(self, msg: str) -> None:
        print(f"  {INFO} {msg}")


def step(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", default=None, help="verifica só esta plataforma (ex: x, linkedin, threads)")
    parser.add_argument("--live-schedule", action="store_true",
                        help="AGENDA um post de teste real daqui a 24h e confirma na fila")
    args = parser.parse_args()

    _load_dotenv()
    r = Report()

    from postiz_client import (  # noqa: E402
        PLATFORM_SETTINGS_BUILDERS,
        PostizClient,
        PostizError,
        build_platform_settings,
    )

    # ── 1. Configuração ────────────────────────────────────────────────
    step("1. Configuração")
    url = os.environ.get("POSTIZ_URL", "").strip()
    key = os.environ.get("POSTIZ_API_KEY", "").strip()
    if not url:
        r.fail("POSTIZ_URL ausente", "defina POSTIZ_URL no .env / stack do dashboard")
    else:
        r.ok(f"POSTIZ_URL = {url}")
        if not url.startswith("https://"):
            r.fail("POSTIZ_URL não é HTTPS", "o cliente recusa URL não-HTTPS por design")
    if not key:
        r.fail("POSTIZ_API_KEY ausente", "pegue em Postiz → Settings → Public API")
    else:
        r.ok(f"POSTIZ_API_KEY presente ({len(key)} chars)")

    hosts = os.environ.get("POSTIZ_ALLOWED_MEDIA_HOSTS", "").strip()
    if hosts:
        r.ok(f"POSTIZ_ALLOWED_MEDIA_HOSTS = {hosts}")
    else:
        r.warn("POSTIZ_ALLOWED_MEDIA_HOSTS vazio — qualquer publish_media será recusado "
               "(posts só-texto continuam funcionando)")

    client = PostizClient.from_env()
    if client is None:
        r.fail("PostizClient.from_env() retornou None — configuração incompleta")
        return 1

    # ── 2. Autenticação ────────────────────────────────────────────────
    step("2. Autenticação e integrações conectadas")
    try:
        integrations = client.list_integrations()
        r.ok(f"autenticado — {len(integrations)} integração(ões) retornada(s)")
    except PostizError as exc:
        detail = str(exc)
        r.fail(f"não autenticou: {detail}")
        if "401" in detail:
            r.info("401 = a chave foi lida mas recusada. Gere uma nova em "
                   "Postiz → Settings → Public API e atualize POSTIZ_API_KEY "
                   "no .env local E na stack do dashboard (são valores separados).")
        return 1

    connected: dict[str, str] = {}
    for item in integrations:
        identifier = item.get("identifier")
        if identifier and not item.get("disabled"):
            connected[identifier] = item.get("id", "")
            r.ok(f"{identifier}: {item.get('name') or '(sem nome)'} [id={item.get('id')}]")
    for item in integrations:
        if item.get("disabled"):
            r.warn(f"{item.get('identifier')}: desabilitada no Postiz")
    if not connected:
        r.fail("nenhuma integração ativa", "conecte ao menos uma conta na UI do Postiz")

    # ── 3. Payload por plataforma ──────────────────────────────────────
    step("3. Payloads por plataforma (validação local)")
    targets = [args.platform] if args.platform else sorted(PLATFORM_SETTINGS_BUILDERS)
    for platform in targets:
        if platform not in PLATFORM_SETTINGS_BUILDERS:
            r.warn(f"{platform}: sem builder dedicado — usaria o shape genérico {{'__type': '{platform}'}}")
            continue
        try:
            kwargs = {"title": "Post de verificação"} if platform == "youtube" else {}
            settings = build_platform_settings(platform, **kwargs)
            required = " ".join(f"{k}={v!r}" for k, v in settings.items() if k != "__type")
            r.ok(f"{platform}: {settings['__type']} {required}".rstrip())
        except Exception as exc:
            r.fail(f"{platform}: builder falhou — {exc}")
        if platform not in connected:
            r.warn(f"{platform}: builder OK, mas não há conta conectada no Postiz")

    # ── 4. Agendamento real (opt-in) ───────────────────────────────────
    step("4. Agendamento ponta a ponta")
    if not args.live_schedule:
        r.info("pulado (somente leitura). Rode com --live-schedule para agendar um post de teste real.")
        print()
        return 1 if r.failed else 0

    platform = args.platform or next(
        (p for p in ("x", "threads", "linkedin") if p in connected), None
    )
    if not platform or platform not in connected:
        r.fail(f"sem conta conectada para agendar (--platform={args.platform!r})")
        return 1

    when = datetime.now(timezone.utc) + timedelta(hours=24)
    content = (
        "[TESTE OmniNexus] Verificação automática do pipeline de agendamento via Postiz. "
        f"Agendado para {when.isoformat()}. Pode apagar."
    )
    kwargs = {"title": "Teste OmniNexus"} if platform == "youtube" else {}
    try:
        created = client.schedule_post(
            integration_id=connected[platform],
            content=content,
            media=[],
            settings=build_platform_settings(platform, **kwargs),
            scheduled_at_utc=when.isoformat(),
        )
    except PostizError as exc:
        r.fail(f"Postiz recusou o agendamento: {exc}")
        return 1

    post_ids = [i.get("postId") for i in created if isinstance(i, dict) and i.get("postId")]
    if not post_ids:
        r.fail(f"Postiz não retornou postId: {created!r}")
        return 1
    r.ok(f"agendado em {platform} para {when.isoformat()} (postId={', '.join(post_ids)})")

    confirmation = client.confirm_scheduled(
        post_ids, window=((when - timedelta(days=1)).isoformat(), (when + timedelta(days=1)).isoformat())
    )
    if confirmation.get("scheduled"):
        r.ok(confirmation["detail"])
        r.info("apague o post de teste na UI do Postiz antes que ele saia.")
    else:
        r.fail(f"agendamento não confirmado: {confirmation.get('detail')}")

    print()
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
