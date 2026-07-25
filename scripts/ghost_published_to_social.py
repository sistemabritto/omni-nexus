#!/usr/bin/env python3
"""CLI para a ponte Ghost -> redes sociais.

A lógica mora em dashboard/backend/ghost_social_bridge.py, que é o que a imagem
do dashboard embarca — este arquivo é só a casca de linha de comando para rodar
manualmente ou testar. Ver o docstring do módulo para o porquê da separação.

    python scripts/ghost_published_to_social.py --post-id <id>
    python scripts/ghost_published_to_social.py --post-id <id> --dry-run
    python scripts/ghost_published_to_social.py --payload evento.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))


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
    ap.add_argument("--post-id", help="id do post no Ghost")
    ap.add_argument("--payload", help="arquivo JSON do webhook post.published")
    ap.add_argument("--em-horas", type=float, default=2.0,
                    help="daqui a quantas horas agendar a 1ª rede (default 2)")
    ap.add_argument("--dry-run", action="store_true", help="mostra os textos, não abre aprovação")
    ap.add_argument("--aprovar-artigo", action="store_true",
                    help="estágio 1: abre o gate do ARTIGO (revisar texto, CTAs e capa) "
                         "em vez de derivar as redes. Aprovar publica no Ghost, o que "
                         "dispara o webhook e só então deriva.")
    ap.add_argument("--publicar-em", help="ISO-8601 UTC para agendar o artigo (com --aprovar-artigo)")
    args = ap.parse_args()

    load_env()
    import ghost_social_bridge as bridge

    if args.aprovar_artigo:
        if not args.post_id:
            ap.error("--aprovar-artigo exige --post-id")
        r = bridge.aprovar_artigo(args.post_id, publicar_em=args.publicar_em,
                                  dry_run=args.dry_run)
    elif args.payload:
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        r = bridge.distribuir_do_webhook(payload, em_horas=args.em_horas, dry_run=args.dry_run)
    elif args.post_id:
        r = bridge.distribuir(args.post_id, em_horas=args.em_horas, dry_run=args.dry_run)
    else:
        ap.error("informe --post-id ou --payload")
        return 1

    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
