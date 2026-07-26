#!/usr/bin/env python3
"""Coleta diária das métricas de crescimento.

Fecha o laço da esteira: ela produz e publica, isto mede o que aconteceu
depois. Sem esta rotina o sistema sabia quantos posts saíram e nada sobre
quantas pessoas chegaram.

Lê o analytics do próprio site (sistemabritto.com.br já registra pageviews com
utm_source, cliques de CTA e o pipeline de leads em Supabase) e grava um ponto
por dia na série histórica do Nexus.

Roda às 05:30, antes da esteira de conteúdo das 06:00: assim o número do dia
reflete o que o conteúdo de ontem produziu, sem contar a publicação de hoje que
ainda nem saiu.

Uso:
    python ADWs/routines/daily_growth_metrics.py
    python ADWs/routines/daily_growth_metrics.py --janela 30d
    python ADWs/routines/daily_growth_metrics.py --dry-run
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
    ap.add_argument("--janela", default="7d", help="7d | 30d | 90d (default: 7d)")
    ap.add_argument("--dry-run", action="store_true", help="mostra sem gravar")
    args = ap.parse_args()

    load_env()
    from site_analytics import SiteIndisponivel, coletar

    try:
        medicoes = coletar(janela=args.janela)
    except SiteIndisponivel as exc:
        log(f"coleta falhou: {exc}")
        _alertar(f"⚠️ <b>Métricas de crescimento</b>\nColeta falhou: {exc}")
        return 1

    totais = {m["metrica"]: m["valor"] for m in medicoes if m.get("origem") is None
              or m.get("origem") == "total"}
    log(f"coletado ({args.janela}): " + " · ".join(f"{k}={v:.0f}" for k, v in totais.items()))

    if args.dry_run:
        for m in medicoes:
            log(f"  {m['metrica']:<16} {m.get('origem', 'total'):<14} {m['valor']}")
        return 0

    # Grava pela API: o container do scheduler não monta o volume do banco, e
    # escrever no arquivo criaria um banco fantasma na camada efêmera — a
    # mesma armadilha que já engoliu a fila de pautas uma vez.
    try:
        from sdk_client import evo

        r = evo.post("/api/metricas", {"medicoes": medicoes}) or {}
        log(f"gravadas {r.get('gravadas')} medições na série histórica")
    except Exception as exc:  # noqa: BLE001
        log(f"não consegui gravar: {exc}")
        _alertar(f"⚠️ <b>Métricas de crescimento</b>\nColetei mas não gravei: {exc}")
        return 1

    return 0


def _alertar(texto: str) -> None:
    """Só falha vira alerta. Coleta bem-sucedida aparece no painel — avisar
    todo dia que deu certo ensina a ignorar o canal."""
    try:
        from notifications import send_telegram_alert

        send_telegram_alert(texto)
    except Exception:  # noqa: BLE001 — alerta não derruba rotina
        pass


if __name__ == "__main__":
    sys.exit(main())
