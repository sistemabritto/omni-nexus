#!/usr/bin/env python3
"""ADW: IG Reels Analysis — coleta incremental dos reels de @caiomktviral e gera relatório de métricas. Type: systematic"""

import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from runner import banner, run_script, summary  # noqa: E402

TARGET = 100
USER_ID = "74311000089"
PAGE_DELAY = 30
RETRY_WAIT = 180
MAX_RETRIES = 6
MAX_PAGES_PER_RUN = 6

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
# Sessão opcional via env IG_SESSIONID (formato "userid:tok:idx:hash"). Sem ela,
# usa endpoint público com rate-limit conservador (sujeito a 401 require_login).
SESSIONID = os.environ.get("IG_SESSIONID", "")

WORKSPACE = Path(__file__).resolve().parents[3]
OUT_DIR = WORKSPACE / "workspace" / "reach-caiomktviral-100"
CHECKPOINT = OUT_DIR / "reels_collected.json"
SHARES_DIR = WORKSPACE / "workspace" / "shares"


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _fetch(url: str) -> dict | None:
    for i in range(MAX_RETRIES):
        try:
            cmd = [
                "curl", "-s", "-m", "30",
                "-H", "x-ig-app-id: 936619743392459",
                "-H", f"User-Agent: {USER_AGENT}",
                "-H", "Accept: application/json",
            ]
            if SESSIONID:
                cmd += ["-H", f"Cookie: sessionid={SESSIONID}; ds_user_id={SESSIONID.split(':')[0]}"]
            cmd += [url]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if r.returncode != 0:
                raise RuntimeError(f"curl rc={r.returncode}")
            txt = r.stdout.strip()
            if not txt:
                raise RuntimeError("resposta vazia")
            d = json.loads(txt)
            if isinstance(d, dict) and (d.get("status") == "fail" or ("items" not in d and "message" in d)):
                raise RuntimeError(d.get("message") or "erro do IG")
            return d
        except Exception as e:
            wait = RETRY_WAIT + random.uniform(0, 20)
            _log(f"  retry {i + 1}/{MAX_RETRIES}: {e} -> espera {wait:.0f}s")
            time.sleep(wait)
    return None


def _save(reels: list, path: Path) -> None:
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reels, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def do_task() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHARES_DIR.mkdir(parents=True, exist_ok=True)

    reels = []
    seen = set()
    if CHECKPOINT.exists():
        reels = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        seen = {r["shortcode"] for r in reels}
        _log(f"checkpoint: {len(reels)} reels")

    pages_done = 0
    max_id = None
    while len(reels) < TARGET and pages_done < MAX_PAGES_PER_RUN:
        url = f"https://www.instagram.com/api/v1/feed/user/{USER_ID}/?count=12"
        if max_id:
            url += f"&max_id={max_id}"
        d = _fetch(url)
        if not d or "items" not in d:
            _log("FALHA definitiva na coleta (sem items)")
            break
        items = d.get("items", [])
        if not items:
            _log("fim do feed")
            break
        new = 0
        for it in items:
            sid = it.get("code")
            if not sid or sid in seen:
                continue
            if it.get("media_type") == 2:
                seen.add(sid)
                cap = it.get("caption")
                caption = cap.get("text", "") if isinstance(cap, dict) else (cap or "")
                reels.append({
                    "shortcode": sid,
                    "id": str(it.get("pk")),
                    "taken_at_timestamp": it.get("taken_at"),
                    "is_video": it.get("is_video"),
                    "product_type": it.get("product_type"),
                    "video_view_count": it.get("play_count"),
                    "likes": it.get("like_count") or 0,
                    "comments": it.get("comment_count") or 0,
                    "has_audio": it.get("has_audio"),
                    "video_url": (it.get("video_versions") or [{}])[0].get("url") if it.get("video_versions") else None,
                    "display_url": it.get("display_url") or ((it.get("image_versions2") or {}).get("candidates", [{}])[0].get("url") if it.get("image_versions2") else None),
                    "caption": caption,
                    "duration": it.get("video_duration"),
                    "clips_music": (it.get("clips_metadata") or {}).get("music_info"),
                })
                new += 1
        _save(reels, CHECKPOINT)
        more = d.get("more_available")
        max_id = d.get("next_max_id")
        pages_done += 1
        _log(f"[page {pages_done}] +{len(items)} posts (+{new} reels) | total={len(reels)}/{TARGET} | more={more}")
        if not more or not max_id:
            break
        time.sleep(PAGE_DELAY + random.uniform(0, 10))

    # Relatório de métricas parcial em workspace/shares
    if reels:
        rows = []
        for r in sorted(reels, key=lambda x: x.get("video_view_count") or 0, reverse=True):
            d = datetime.utcfromtimestamp(r["taken_at_timestamp"]).strftime("%Y-%m-%d") if r.get("taken_at_timestamp") else "-"
            rows.append(
                f"| [{r['shortcode']}](https://www.instagram.com/reel/{r['shortcode']}/) | {r.get('video_view_count') or 0} | "
                f"{r.get('likes') or 0} | {r.get('comments') or 0} | {d} | {'sim' if r.get('has_audio') else 'nao'} | {len(r.get('caption') or '')} chars |"
            )
        total_views = sum(r.get("video_view_count") or 0 for r in reels)
        total_likes = sum(r.get("likes") or 0 for r in reels)
        avg_views = total_views // len(reels)
        date_str = datetime.now().strftime("%Y-%m-%d")
        report = f"""# Relatório IG Reels — @caiomktviral

> Gerado automaticamente pela rotina `ig-reels-analysis` em {date_str}.

## Progresso
- Reels coletados: **{len(reels)}/{TARGET}**
- Feed total do perfil: 1.887 posts (bio: "100 reels por dia")

## Métricas agregadas (amostra {len(reels)})
| Métrica | Valor |
|---|---|
| Views totais | {total_views:,} |
| Likes totais | {total_likes:,} |
| Views médias | {avg_views:,} |
| Likes médios | {total_likes // len(reels):,} |

## Ranking por views
| Reel | Views | Likes | Comentários | Data | Áudio | Caption |
|---|---|---|---|---|---|---|
{chr(10).join(rows)}

## Notas
- Coleta via `feed/user/{USER_ID}` + paginação `max_id` (endpoint correto; `web_profile_info` tem paginação quebrada).
- Com `IG_SESSIONID` no env usa sessão autenticada (evita 401 require_login); sem ela usa rate-limit conservador.
- Pipeline de transcrição (Groq) e análise visual (OmniRoute Britto-Vision) validados em 105 reels — ver workspace/reports/[C]analise-105-reels-caiomktviral.md.
"""
        report_path = SHARES_DIR / f"[C]relatorio-ig-caiomktviral-{date_str}.md"
        report_path.write_text(report, encoding="utf-8")
        _log(f"relatório: {report_path}")

    return {
        "ok": True,
        "summary": f"{len(reels)}/{TARGET} reels coletados",
        "data": {"reels": len(reels), "target": TARGET},
    }


def main() -> None:
    banner("IG Reels Analysis", "coleta incremental @caiomktviral | systematic")
    results = []
    results.append(run_script(do_task, log_name="ig-reels-analysis", timeout=600))
    summary(results, "IG Reels Analysis")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
