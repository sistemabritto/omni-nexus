#!/usr/bin/env python3
"""Publica um artefato HTML no Nexus e devolve o link de /shares.

Padrão do workspace (ver .claude/rules/artifacts.md): relatório, análise e
qualquer documento visual entregável vai para o **próprio Nexus**, nunca para
artefato de ferramenta externa. O OmniNexus é o produto — um relatório
hospedado fora dele é um relatório que o Felipe não controla nem versiona.

    python scripts/publish_artifact.py workspace/reports/[C]relatorio.html
    python scripts/publish_artifact.py <arquivo> --expires 7d
    python scripts/publish_artifact.py <arquivo> --force-novo

Reaproveita o share existente do mesmo caminho por padrão: republicar gera token
novo e invalida o link que já foi mandado no Telegram. Para atualizar o
conteúdo, sobrescreva o arquivo — o link antigo passa a servir a versão nova.

Roda de fora da VPS: copia o arquivo para dentro do container do dashboard
(o `/api/shares` só aceita caminho dentro do workspace) e chama a API.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NEXUS = os.environ.get("NEXUS_URL", "https://nexus.workflowapi.com.br")
SSH_HOST = os.environ.get("NEXUS_SSH_HOST", "evo-nexus-vps")

# A Cloudflare na frente do Nexus bloqueia user-agent de script (erro 1010).
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

OK, FAIL, INFO = "\033[92m✓\033[0m", "\033[91m✗\033[0m", "·"


def token_do_dashboard() -> str:
    """O token da VPS é diferente do .env local — sempre ler do container."""
    env = (os.environ.get("DASHBOARD_API_TOKEN_VPS") or "").strip()
    if env:
        return env
    r = subprocess.run(
        ["ssh", SSH_HOST,
         "docker exec $(docker ps -q --filter name=evonexus_evonexus_dashboard | head -1) "
         "printenv DASHBOARD_API_TOKEN"],
        capture_output=True, text=True, timeout=90)
    return r.stdout.strip()


def api(metodo: str, caminho: str, token: str, corpo: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{NEXUS}{caminho}",
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": UA},
        method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"_erro": e.code, "_detalhe": e.read().decode()[:300]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arquivo", help="caminho do HTML, relativo à raiz do repo")
    ap.add_argument("--expires", default=None,
                    help="1h | 24h | 7d | 30d (default: sem expirar)")
    ap.add_argument("--force-novo", action="store_true",
                    help="cria token novo mesmo se já existir share para o caminho")
    args = ap.parse_args()

    rel = args.arquivo.replace("\\", "/").lstrip("./")
    local = REPO / rel
    if not local.is_file():
        print(f"{FAIL} arquivo não encontrado: {local}")
        return 1
    if not rel.startswith("workspace/"):
        print(f"{FAIL} o share só aceita caminho dentro de workspace/ — mova o arquivo.")
        return 1

    token = token_do_dashboard()
    if not token:
        print(f"{FAIL} não consegui ler DASHBOARD_API_TOKEN do container.")
        return 1

    # reaproveita o link existente, senão o que já foi enviado vira lixo
    if not args.force_novo:
        existente = api("GET", f"/api/shares/by-path?path={urllib.parse.quote(rel)}", token)
        if existente.get("url"):
            print(f"{OK} share já existe (conteúdo atualizado no lugar)")
            print(f"   {existente['url']}")
            return 0

    print(f"{INFO} enviando para o container do dashboard…")
    remoto = f"/root/.artifact-upload-{local.name}"
    if subprocess.run(["scp", "-q", str(local), f"{SSH_HOST}:{remoto}"], timeout=180).returncode:
        print(f"{FAIL} scp falhou.")
        return 1
    destino = f"/workspace/{rel}"
    cmd = (f'DC=$(docker ps -q --filter name=evonexus_evonexus_dashboard | head -1); '
           f'docker exec $DC mkdir -p "$(dirname \'{destino}\')" && '
           f'docker cp "{remoto}" $DC:"{destino}" && rm -f "{remoto}"')
    if subprocess.run(["ssh", SSH_HOST, cmd], timeout=180).returncode:
        print(f"{FAIL} não consegui colocar o arquivo no container.")
        return 1

    r = api("POST", "/api/shares", token, {"path": rel, "expires_in": args.expires})
    if r.get("_erro"):
        print(f"{FAIL} /api/shares devolveu {r['_erro']}: {r.get('_detalhe')}")
        return 1
    print(f"{OK} publicado no Nexus")
    print(f"   {r['url']}")
    print(f"   expira: {r.get('expires_at') or 'nunca'}  ·  aparece em {NEXUS}/shares")
    return 0


if __name__ == "__main__":
    sys.exit(main())
