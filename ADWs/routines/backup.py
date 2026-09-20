#!/usr/bin/env python3
"""ADW: Daily Backup — Export workspace gitignored data to local ZIP (+ S3 if configured)"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from runner import run_script, banner, summary

# Import backup logic from root backup.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import backup as backup_module


# Falhas TRANSITÓRIAS do backup (upload S3 lento, rede derrubando no meio do
# PUT, disco travando) — vale tentar de novo em vez de falhar o dia inteiro.
_RETRYABLE_BACKUP = ("timed out", "timeout", "network is unreachable", "connection reset",
                     "read operation timed", "temporarily overloaded", "slowdown",
                     "retryable", "connection aborted")


def _do_backup():
    """Run backup and return structured result for runner.

    Se S3 configurado: só p/ S3 e apaga o ZIP local depois do upload.
    Senão: local (fallback). Retry interno (3x, backoff) p/ falha transitória —
    antes UMA oscilação de rede matava o backup e ele ficava "fantasma" por
    dias seguidos (10/11 de setembro).
    """
    last_err = None
    for attempt in range(3):
        try:
            files = backup_module.collect_files()
            if not files:
                return {"ok": True, "summary": "No files to backup"}

            s3_bucket = os.environ.get("BACKUP_S3_BUCKET")
            if s3_bucket:
                zip_path = backup_module.backup_local(s3_upload=True)
                size_str = backup_module._format_size(zip_path.stat().st_size)
                zip_path.unlink(missing_ok=True)
                return {"ok": True, "summary": f"{len(files)} files → s3://{s3_bucket}/{zip_path.name} ({size_str})"}
            else:
                zip_path = backup_module.backup_local(s3_upload=False)
                size_str = backup_module._format_size(zip_path.stat().st_size)
                return {"ok": True, "summary": f"{len(files)} files → {zip_path.name} ({size_str}) [local]"}
        except Exception as exc:  # noqa: BLE001 — decide se é transitório
            msg = str(exc).lower()
            last_err = str(exc)
            if not any(k in msg for k in _RETRYABLE_BACKUP) or attempt >= 2:
                raise
            delay = 20.0 * (2 ** attempt)
            print(f"[backup] tentativa {attempt+1} falhou ({type(exc).__name__}) — retry em {delay:.0f}s", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"backup falhou após 3 tentativas: {last_err}")


def main():
    banner("💾 Daily Backup", "Workspace data export | systematic")
    results = []
    results.append(run_script(_do_backup, log_name="backup", timeout=600))
    summary(results, "Daily Backup")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠ Cancelado.")
