#!/usr/bin/env python3
"""Pipeline editorial: calendário YAML -> imagem -> draft no Ghost -> agendamento no Postiz.

Objetivo 4/5 (2026-07-25). Lê workspace/social/[C]calendario-editorial-34d.yaml e
executa, por post, as etapas que hoje são manuais. Cada etapa é idempotente e
registra estado em workspace/social/[C]pipeline-state.json, então rodar de novo
não duplica imagem nem draft — retoma de onde parou.

    python scripts/editorial_pipeline.py status                 # o que falta fazer
    python scripts/editorial_pipeline.py images --dias 1-8      # gera thumbnails
    python scripts/editorial_pipeline.py drafts --dias 1-8      # cria drafts no Ghost
    python scripts/editorial_pipeline.py schedule --dias 1-8    # agenda social no Postiz
    python scripts/editorial_pipeline.py run --dias 1-8         # as três em ordem

Regras que o script NÃO relaxa:
  - nada é publicado: o Ghost recebe `status=draft` e o Postiz recebe
    `type=draft` por padrão. Publicar continua sendo decisão humana.
  - `--schedule-mode schedule` só é aceito junto de `--confirmo-agendamento`,
    para que agendar de verdade seja sempre um ato explícito.
  - o corpo do artigo NÃO é gerado aqui. O calendário carrega tema, estrutura e
    ângulo; escrever é trabalho do Pixel/Quill com o briefing de marca na mão.
    O draft nasce com a estrutura e o checklist GEO como esqueleto.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

CAL = REPO / "workspace" / "social" / "[C]calendario-editorial-34d.yaml"
STATE = REPO / "workspace" / "social" / "[C]pipeline-state.json"
IMGDIR = REPO / "workspace" / "social" / "thumbs"

OK, FAIL, SKIP, INFO = "\033[92m✓\033[0m", "\033[91m✗\033[0m", "\033[90m·\033[0m", "\033[94m→\033[0m"


# ── env / estado ─────────────────────────────────────────────────────────

def load_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_state() -> dict:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def load_posts(spec: str | None) -> list[dict]:
    import yaml

    data = yaml.safe_load(CAL.read_text(encoding="utf-8"))
    posts = data["posts"]
    if not spec:
        return posts
    wanted: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            wanted.update(range(int(a), int(b) + 1))
        elif part:
            wanted.add(int(part))
    return [p for p in posts if p["dia"] in wanted]


# ── etapa 1: imagem ──────────────────────────────────────────────────────

def step_images(posts: list[dict], state: dict) -> int:
    IMGDIR.mkdir(parents=True, exist_ok=True)
    script = REPO / ".claude/skills/ai-image-creator/scripts/generate-image.py"
    provider = os.environ.get("EDITORIAL_IMAGE_PROVIDER", "openai")
    errors = 0
    for p in posts:
        key = f"dia{p['dia']}"
        st = state.setdefault(key, {})
        out = IMGDIR / f"dia-{p['dia']:02d}-{p['data']}.png"
        if st.get("image") and Path(st["image"]).is_file():
            print(f"  {SKIP} dia {p['dia']:>2}: imagem já existe")
            continue
        print(f"  {INFO} dia {p['dia']:>2}: gerando imagem…", flush=True)
        r = subprocess.run(
            [sys.executable, str(script), "-p", p["thumbnail_prompt"],
             "-o", str(out), "--provider", provider, "-a", "16:9"],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0 or not out.is_file():
            print(f"  {FAIL} dia {p['dia']:>2}: {(r.stderr or r.stdout)[-180:].strip()}")
            errors += 1
            continue
        st["image"] = str(out)
        save_state(state)
        print(f"  {OK} dia {p['dia']:>2}: {out.name}")
    return errors


# ── etapa 2: draft no Ghost ──────────────────────────────────────────────

def ghost_token() -> str:
    import jwt as pyjwt

    admin = os.environ["GHOST_ADMIN_API_KEY"]
    kid, secret = admin.split(":")
    iat = int(time.time())
    return pyjwt.encode(
        {"iat": iat, "exp": iat + 300, "aud": "/admin/"},
        bytes.fromhex(secret), algorithm="HS256", headers={"kid": kid, "alg": "HS256"},
    )


def build_skeleton(p: dict) -> list[dict]:
    """Esqueleto Lexical do draft: estrutura + checklist GEO como guia de escrita.

    Deliberadamente NÃO é o artigo final. Escrever com a voz da marca é trabalho
    do Pixel/Quill; o que o pipeline entrega é o andaime correto para isso,
    com a keyword, o ângulo e as regras GEO na frente de quem escreve.
    """
    children: list[dict] = []

    def para(text: str, fmt: int = 0) -> dict:
        return {"type": "paragraph", "children": [
            {"type": "extended-text", "text": text, "format": fmt, "detail": 0, "mode": "normal", "style": ""}
        ], "direction": "ltr", "format": "", "indent": 0, "version": 1}

    def head(text: str, tag: str = "h2") -> dict:
        return {"type": "heading", "tag": tag, "children": [
            {"type": "extended-text", "text": text, "format": 0, "detail": 0, "mode": "normal", "style": ""}
        ], "direction": "ltr", "format": "", "indent": 0, "version": 1}

    children.append(para(
        f"[BRIEFING — apagar antes de publicar]  Keyword: {p['keyword']} "
        f"(volume {p.get('volume', '?')}/mês, KD {p.get('kd', '?')}).  "
        f"Objetivo: {p['objetivo']}  Cluster: {p['cluster']}", fmt=2))
    children.append(para(
        "[CHECKLIST GEO]  1) responder a pergunta do título nos 2 primeiros "
        "parágrafos  2) todo número com fonte linkada — dado real ou nenhum dado  "
        "3) citar fonte externa inline  4) H2 em pergunta + resposta curta abaixo", fmt=2))
    children.append(para("[Abertura: responda a pergunta do título aqui, em 2 parágrafos.]"))
    for h in p["estrutura"]:
        children.append(head(h))
        children.append(para("[desenvolver]"))
    children.append(head("Próximo passo", "h3"))
    children.append(para(p["cta"]))
    return children


def step_drafts(posts: list[dict], state: dict) -> int:
    import requests

    url = os.environ["GHOST_URL"].rstrip("/")
    errors = 0
    for p in posts:
        key = f"dia{p['dia']}"
        st = state.setdefault(key, {})
        if st.get("ghost_id"):
            print(f"  {SKIP} dia {p['dia']:>2}: draft já criado ({st.get('ghost_url','')})")
            continue
        lexical = {"root": {"children": build_skeleton(p), "direction": "ltr",
                            "format": "", "indent": 0, "type": "root", "version": 1}}
        body = {"posts": [{
            "title": p["titulo"],
            "lexical": json.dumps(lexical, ensure_ascii=False),
            "status": "draft",                      # nunca published — decisão humana
            "custom_excerpt": p["meta_description"],
            "meta_description": p["meta_description"],
            "og_description": p["meta_description"],
            "twitter_description": p["meta_description"],
            "tags": [{"name": t} for t in p["tags"]],
        }]}
        try:
            # Sem query param: `?source=lexical` é recusado com
            # "Validation (AllowedValues) failed for source" neste Ghost (6.53).
            # O campo `lexical` no corpo já basta.
            r = requests.post(f"{url}/ghost/api/admin/posts/",
                              headers={"Authorization": f"Ghost {ghost_token()}",
                                       "Content-Type": "application/json"},
                              json=body, timeout=60)
        except Exception as exc:  # noqa: BLE001
            print(f"  {FAIL} dia {p['dia']:>2}: rede — {exc}")
            errors += 1
            continue
        if r.status_code >= 300:
            print(f"  {FAIL} dia {p['dia']:>2}: Ghost {r.status_code} {r.text[:160]}")
            errors += 1
            continue
        post = r.json()["posts"][0]
        st["ghost_id"] = post["id"]
        st["ghost_url"] = post.get("url", "")
        st["ghost_admin_url"] = f"{url}/ghost/#/editor/post/{post['id']}"
        save_state(state)
        print(f"  {OK} dia {p['dia']:>2}: {p['titulo'][:52]}")
    return errors


# ── etapa 3: agendamento social no Postiz ────────────────────────────────

def step_schedule(posts: list[dict], state: dict, mode: str) -> int:
    from postiz_client import PostizClient, PostizError, build_platform_settings

    client = PostizClient.from_env()
    if client is None:
        print(f"  {FAIL} POSTIZ_URL/POSTIZ_API_KEY não configurados.")
        return 1
    try:
        integrations = client.list_integrations()
    except PostizError as exc:
        print(f"  {FAIL} Postiz: {exc}")
        return 1

    errors = 0
    for p in posts:
        key = f"dia{p['dia']}"
        st = state.setdefault(key, {})
        sched = st.setdefault("social", {})
        link = st.get("ghost_url") or ""
        for plat in p["distribuicao"]:
            if sched.get(plat):
                print(f"  {SKIP} dia {p['dia']:>2} {plat}: já enviado")
                continue
            integration = client.select_integration(plat, integrations)
            if not integration:
                print(f"  {FAIL} dia {p['dia']:>2} {plat}: sem integração ativa")
                errors += 1
                continue
            # Texto curto e honesto; a versão final por rede é trabalho do
            # social-content-repurposer. Aqui garantimos que o slot exista.
            content = f"{p['titulo']}\n\n{p['meta_description']}"
            if link:
                content += f"\n\n{link}"
            try:
                settings = build_platform_settings(plat)
                if mode == "schedule":
                    created = client.schedule_post(
                        integration_id=integration["id"], content=content, media=[],
                        settings=settings, scheduled_at_utc=p["publish_at"].replace("Z", "+00:00"))
                else:
                    created = client.create_draft(
                        integration_id=integration["id"], content=content, media=[],
                        settings=settings,
                        now_iso_utc=datetime.now(timezone.utc).isoformat())
            except (PostizError, ValueError) as exc:
                print(f"  {FAIL} dia {p['dia']:>2} {plat}: {exc}")
                errors += 1
                continue
            pid = next((i.get("postId") for i in created if isinstance(i, dict) and i.get("postId")), None)
            sched[plat] = {"postId": pid, "mode": mode}
            save_state(state)
            print(f"  {OK} dia {p['dia']:>2} {plat}: {mode} ({pid})")
    return errors


# ── status ───────────────────────────────────────────────────────────────

def step_status(posts: list[dict], state: dict) -> int:
    print(f"{'dia':>4} {'data':<12} {'img':<4} {'draft':<6} {'social':<8} título")
    print("-" * 88)
    for p in posts:
        st = state.get(f"dia{p['dia']}", {})
        img = "ok" if st.get("image") else "-"
        draft = "ok" if st.get("ghost_id") else "-"
        social = f"{len(st.get('social', {}))}/{len(p['distribuicao'])}"
        print(f"{p['dia']:>4} {p['data']:<12} {img:<4} {draft:<6} {social:<8} {p['titulo'][:44]}")
    done = sum(1 for p in posts if state.get(f"dia{p['dia']}", {}).get("ghost_id"))
    print(f"\n{done}/{len(posts)} com draft criado.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etapa", choices=["status", "images", "drafts", "schedule", "run"])
    ap.add_argument("--dias", help="ex: 1-8 ou 1,3,5 (default: todos)")
    ap.add_argument("--schedule-mode", choices=["draft", "schedule"], default="draft",
                    help="draft (default, seguro) ou schedule (agenda de verdade)")
    ap.add_argument("--confirmo-agendamento", action="store_true",
                    help="obrigatório junto de --schedule-mode schedule")
    args = ap.parse_args()

    load_env()
    posts = load_posts(args.dias)
    if not posts:
        print("nenhum post selecionado.")
        return 1
    state = load_state()

    if args.schedule_mode == "schedule" and not args.confirmo_agendamento:
        print(f"{FAIL} --schedule-mode schedule exige --confirmo-agendamento "
              "(agendar de verdade é sempre ato explícito).")
        return 1

    print(f"\n\033[1m{args.etapa}\033[0m — {len(posts)} post(s)\n")
    errors = 0
    if args.etapa == "status":
        return step_status(posts, state)
    if args.etapa in ("images", "run"):
        errors += step_images(posts, state)
    if args.etapa in ("drafts", "run"):
        errors += step_drafts(posts, state)
    if args.etapa in ("schedule", "run"):
        errors += step_schedule(posts, state, args.schedule_mode)

    print(f"\n{OK if not errors else FAIL} concluído com {errors} erro(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
