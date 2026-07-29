#!/usr/bin/env python3
"""Coleta diária de gasto/impressões/cliques do Facebook/Meta Ads — Fase 4.

Nenhuma campanha está ativa em 29/07/2026 (confirmado via API nas duas
contas cadastradas) — esta rotina existe pra já estar medindo no dia em que
uma campanha entrar no ar, não pra descobrir isso depois que o gasto já
aconteceu sem registro.

Roda diariamente, junto de daily_growth_metrics.py — mesmo motivo (o número
do dia reflete o que aconteceu ontem).

Uso:
    python ADWs/routines/facebook_ads_pulse.py
    python ADWs/routines/facebook_ads_pulse.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def load_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="mostra sem gravar")
    args = ap.parse_args()

    load_env()
    from facebook_ads import AdsIndisponivel, coletar

    try:
        medicoes = coletar()
    except AdsIndisponivel as exc:
        log(f"coleta falhou: {exc}")
        return 1

    if not medicoes:
        log("nenhuma campanha ativa nas contas configuradas — nada a gravar hoje")
        return 0

    log(f"coletado: {len(medicoes)} medições em "
        f"{len({m['origem'] for m in medicoes})} campanha(s)")

    if args.dry_run:
        for m in medicoes:
            log(f"  {m['metrica']:<16} {m['origem']:<30} {m['valor']}")
        return 0

    # Grava pela API: o container do scheduler não monta o volume do banco.
    try:
        from sdk_client import evo

        r = evo.post("/api/metricas", {"medicoes": medicoes}) or {}
        log(f"gravadas {r.get('gravadas')} medições na série histórica")
    except Exception as exc:  # noqa: BLE001
        log(f"não consegui gravar: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
