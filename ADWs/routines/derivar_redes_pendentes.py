#!/usr/bin/env python3
"""Varredor: artigo publicado que ainda não virou post de rede.

Existe porque o artigo AGENDADO não passava por código nosso na hora de ir ao
ar. O gate do blog aceita `publish_at`; quando o humano agenda, o Ghost devolve
`scheduled` e publica sozinho horas depois. A derivação das redes só acontecia
no caminho da publicação imediata, então todo artigo agendado ficava órfão — em
27/07/2026 os dois artigos do dia (13h e 18h BRT) foram publicados pelo Ghost e
nenhum post de X, LinkedIn ou Threads chegou a existir.

O webhook `post.published` cobriria o caso, mas depender dele é frágil: a chave
de Admin API não tem permissão para criar webhook (403 NoPermissionError no
endpoint de integrações), então é etapa manual no painel do Ghost. Este
varredor não depende de nada externo estar configurado.

Nada é publicado aqui. Cada rede continua abrindo o seu gate no Telegram.

A lógica mora em `dashboard/backend/ghost_social_bridge.derivar_pendentes`;
este arquivo é o ponto de entrada do scheduler.
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


def main() -> int:
    carregar_env()
    import ghost_social_bridge as bridge

    dry = "--dry-run" in sys.argv
    resultado = bridge.derivar_pendentes(dry_run=dry)

    # Só imprime o que exigiu ação. A rotina roda a cada 15 minutos e o caso
    # normal é não ter nada a fazer — logar "nada a fazer" 96 vezes por dia
    # afoga o log em que se procura o dia que deu errado.
    agiu = [a for a in resultado["artigos"] if a.get("acao") != "nada a fazer"]
    if agiu:
        print(json.dumps({"ok": resultado["ok"], "artigos": agiu},
                         indent=2, ensure_ascii=False))
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
