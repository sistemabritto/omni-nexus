#!/usr/bin/env python3
"""Backup watchdog — alerta quando o backup diário para de produzir artefato.

O backup roda às 21:00 e devolvia `returncode 0` mesmo quando nada era
produzido: entre 24/07 e 28/07/2026 os artefatos (S3 e local) pararam de
existir sem nenhum erro visível — o `run_adw` do scheduler engolia o stderr e
o "✓" escondia o problema. Este watchdog torna a falha audível.

Roda todo dia às 20:00 (1h antes do backup): se o artefato mais recente
(local OU S3) tiver mais de 48h, manda alerta no Telegram. Silencioso quando
tudo está saudável.

Uso:
    python ADWs/routines/backup_watchdog.py                # roda e alerta se atrasado
    python ADWs/routines/backup_watchdog.py --max-horas 72
    python ADWs/routines/backup_watchdog.py --dry-run      # só imprime, não envia
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def load_env() -> None:
    for env in (REPO / ".env", REPO / "config" / ".env"):
        if env.is_file():
            for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _mais_recente_local() -> datetime | None:
    import backup as b
    if not b.BACKUPS_DIR.exists():
        return None
    zips = sorted(b.BACKUPS_DIR.glob("evonexus-backup-*.zip"), reverse=True)
    if not zips:
        return None
    return datetime.fromtimestamp(zips[0].stat().st_mtime, tz=timezone.utc)


def _mais_recente_s3() -> datetime | None:
    import backup as b
    try:
        boto3 = b._require_boto3()
        bucket, prefix = b._get_s3_config()
        s3 = boto3.client("s3")
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        zips = [c for c in (resp.get("Contents") or []) if c["Key"].endswith(".zip")]
        if not zips:
            return None
        novo = max(zips, key=lambda c: c["LastModified"])
        return novo["LastModified"].replace(tzinfo=timezone.utc)
    except Exception as exc:  # noqa: BLE001
        log(f"S3 indisponível na checagem: {exc}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-horas", type=int, default=48,
                    help="atraso máximo aceitável (default: 48h)")
    ap.add_argument("--dry-run", action="store_true", help="imprime sem enviar")
    args = ap.parse_args()

    load_env()

    local = _mais_recente_local()
    s3 = _mais_recente_s3()
    candidatos = [d for d in (local, s3) if d]
    novo = max(candidatos) if candidatos else None

    agora = datetime.now(timezone.utc)
    if novo is None:
        texto = "🚨 <b>Backup em risco</b>\nNenhum artefato de backup encontrado (local nem S3)."
        atrasado = True
    else:
        idade = (agora - novo).total_seconds() / 3600
        if idade <= args.max_horas:
            log(f"backup saudável — mais recente há {idade:.1f}h (local={local is not None}, s3={s3 is not None})")
            return 0
        texto = (
            f"🚨 <b>Backup atrasado</b>\n"
            f"Último artefato: {novo:%d/%m %H:%M} UTC "
            f"(há {idade:.1f}h, limite {args.max_horas}h)\n"
            f"Local: {'✓' if local else '—'} · S3: {'✓' if s3 else '—'}"
        )
        atrasado = True

    log(f"backup ATRASADO — {texto}")
    if args.dry_run:
        print(texto)
        return 0

    from notifications import send_telegram_alert
    ok = send_telegram_alert(texto)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
