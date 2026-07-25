#!/usr/bin/env python3
"""Instala (ou atualiza) o OpenSEO como plugin do OmniNexus.

Objetivo 2 (2026-07-25). O OpenSEO (github.com/every-app/open-seo, MIT) não é
um plugin EvoNexus nativo — é uma aplicação TypeScript/Cloudflare completa que
expõe um MCP server e um conjunto de agent skills. A integração aqui tem três
partes, e só uma delas é reproduzida por este script:

  1. serviço self-hosted  -> docker-compose.yml (service `open-seo`, versionado)
  2. MCP server           -> .mcp.json (`plugin-open-seo-openseo`, versionado)
  3. agent skills         -> .claude/skills/plugin-open-seo-* (ESTE SCRIPT)

Os artefatos do item 3 são deliberadamente gitignored: o repositório trata
plugin instalado como estado por máquina (.gitignore, seção "Plugins"). Por
isso o fork guarda o *instalador pinado* em vez dos arquivos copiados — o
resultado é o mesmo em qualquer máquina, e o `git status` continua limpo.

Uso:
    python scripts/install_open_seo_plugin.py            # instala/atualiza
    python scripts/install_open_seo_plugin.py --check    # só verifica
    python scripts/install_open_seo_plugin.py --ref <sha>  # outra versão upstream
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/every-app/open-seo.git"

# Pinned upstream commit — troque junto com uma revisão das skills, nunca
# silenciosamente. Este é o commit que o fork declara refletir.
UPSTREAM_REF = "f56972639f14e7e766498a8a2f6441913eb83c0c"

SLUG = "open-seo"

# Só as skills de SEO. `openseo-review-web-content` (guia editorial do site do
# próprio OpenSEO) e as de tooling interno do repo deles (deslop, merge-ready,
# papercuts, webapp-testing, maintain-greptile-rules, openseo-release-notes)
# ficam de fora de propósito: não fazem sentido fora daquele repositório.
SKILLS = [
    "seo-project-setup",
    "keyword-research",
    "keyword-clustering",
    "competitor-analysis",
    "competitive-landscape",
    "link-prospecting",
    "seo-coach",
]

OK, FAIL, INFO = "\033[92m✓\033[0m", "\033[91m✗\033[0m", "·"


def _namespaced(bare: str) -> str:
    """Mesma convenção do instalador nativo (plugin_file_ops._enforce_namespace)."""
    return f"plugin-{SLUG}-{bare}"


def _render(bare: str, text: str, ref: str) -> str:
    """Aplica o namespace no frontmatter e carimba a procedência."""
    name = _namespaced(bare)
    text = re.sub(r"^name:\s*.*$", f"name: {name}", text, count=1, flags=re.M)
    return text + (
        f"\n---\n\n_Vendored from [every-app/open-seo]"
        f"(https://github.com/every-app/open-seo) @ `{ref[:7]}` (MIT). "
        f"Upstream skill: `{bare}`. Requires the OpenSEO MCP server "
        f"(`plugin-open-seo-openseo`) — see `plugins/open-seo/README.md`._\n"
    )


def check() -> int:
    missing = [b for b in SKILLS if not (REPO_ROOT / ".claude/skills" / _namespaced(b) / "SKILL.md").is_file()]
    for bare in SKILLS:
        print(f"  {FAIL if bare in missing else OK} .claude/skills/{_namespaced(bare)}/SKILL.md")
    mcp = (REPO_ROOT / ".mcp.json").read_text(encoding="utf-8")
    has_mcp = "plugin-open-seo-openseo" in mcp
    print(f"  {OK if has_mcp else FAIL} .mcp.json → plugin-open-seo-openseo")
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    has_svc = "open-seo:" in compose
    print(f"  {OK if has_svc else FAIL} docker-compose.yml → service open-seo")
    if missing or not has_mcp or not has_svc:
        print(f"\n{FAIL} instalação incompleta — rode sem --check para corrigir.")
        return 1
    print(f"\n{OK} OpenSEO instalado ({len(SKILLS)} skills).")
    return 0


def install(ref: str) -> int:
    plugin_dir = REPO_ROOT / "plugins" / SLUG
    skills_src_root = plugin_dir / "skills"

    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "open-seo"
        print(f"{INFO} clonando {UPSTREAM} @ {ref[:7]}")
        subprocess.run(
            ["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", UPSTREAM, str(clone)],
            check=True,
        )
        subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", ref], check=True)

        upstream_skills = clone / ".agents" / "skills"
        if not upstream_skills.is_dir():
            print(f"{FAIL} upstream não tem .agents/skills — layout mudou, revise este script.")
            return 1

        plugin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(clone / "LICENSE", plugin_dir / "LICENSE")

        for bare in SKILLS:
            src = upstream_skills / bare / "SKILL.md"
            if not src.is_file():
                print(f"{FAIL} skill ausente no upstream: {bare} (renomeada/removida?)")
                return 1
            text = src.read_text(encoding="utf-8")

            # cópia-fonte, sem namespace (o que o plugin "empacota")
            staged = skills_src_root / bare
            staged.mkdir(parents=True, exist_ok=True)
            (staged / "SKILL.md").write_text(text, encoding="utf-8")

            # cópia instalada, com namespace (o que os agentes enxergam)
            dst = REPO_ROOT / ".claude" / "skills" / _namespaced(bare)
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "SKILL.md").write_text(_render(bare, text, ref), encoding="utf-8")
            print(f"  {OK} {bare} → .claude/skills/{_namespaced(bare)}/")

    print(f"\n{OK} {len(SKILLS)} skills instaladas a partir de {ref[:7]}.")
    print(f"{INFO} falta: DATAFORSEO_API_KEY no .env e `docker compose up -d open-seo`.")
    print(f"{INFO} detalhes em plugins/open-seo/README.md")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="só verifica o estado da instalação")
    parser.add_argument("--ref", default=UPSTREAM_REF, help=f"commit/tag upstream (default: {UPSTREAM_REF[:7]})")
    args = parser.parse_args()
    return check() if args.check else install(args.ref)


if __name__ == "__main__":
    sys.exit(main())
