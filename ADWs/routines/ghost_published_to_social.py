#!/usr/bin/env python3
"""Trigger `post.published` do Ghost -> aprovações de publicação nas redes.

Mora aqui, e não em `scripts/`, porque o executor de triggers só roda script
dentro de `ADWs/routines/` (`routes/triggers.py`) — é uma fronteira de
segurança deliberada, para um trigger não conseguir executar qualquer arquivo
do repositório. Apontar um trigger para `scripts/algo.py` resolve em
`ADWs/routines/scripts/algo.py`, que não existe, e o trigger falha calado.

A lógica de verdade mora em `dashboard/backend/ghost_social_bridge.py`; este
arquivo é só o ponto de entrada. `scripts/ghost_published_to_social.py` é a
mesma coisa para uso manual na linha de comando.

O payload do webhook chega por stdin. Sem payload utilizável, sai com erro em
vez de inventar um post — um trigger que "funciona" sem saber o que publicar é
pior que um trigger que falha.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))


def carregar_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        return
    for linha in env.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ler_evento() -> dict:
    bruto = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not bruto.strip():
        return {}
    try:
        evento = json.loads(bruto)
    except json.JSONDecodeError:
        return {}
    return evento if isinstance(evento, dict) else {}


def main() -> int:
    evento = ler_evento()
    if not evento:
        print(json.dumps({"ok": False, "erro": "trigger sem payload no stdin"},
                         ensure_ascii=False))
        return 1

    carregar_env()
    import ghost_social_bridge as bridge

    # `em_horas` dá folga entre publicar no blog e o post da rede sair: tempo de
    # rever o artigo publicado antes de apontar tráfego para ele.
    horas = float(os.environ.get("GHOST_SOCIAL_DELAY_HOURS", "2"))
    resultado = bridge.distribuir_do_webhook(evento, em_horas=horas)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    return 0 if resultado.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
