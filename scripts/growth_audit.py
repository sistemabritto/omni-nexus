#!/usr/bin/env python3
"""Read-only normalized owned-Instagram snapshot for the Growth Audit skill.

This collector intentionally uses the official configured Instagram API. It does
not scrape, download media, publish, or access CRM conversations. It emits a
small JSON evidence artifact that later audit steps can correlate safely.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_json(base: str, path: str, params: dict[str, str]) -> dict:
    url = f"{base.rstrip('/')}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # report collection state, never a credential
        return {"error": type(exc).__name__}


def metric_value(payload: dict, name: str) -> int | str:
    if payload.get("error"):
        return "COLLECTION_FAILED"
    for item in payload.get("data", []):
        if item.get("name") == name and item.get("values"):
            return item["values"][0].get("value", "NOT_AVAILABLE")
    return "NOT_SUPPORTED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--account", default="", help="Instagram label; defaults to first configured account")
    parser.add_argument("--output", type=Path, help="optional evidence JSON path")
    args = parser.parse_args()
    if args.days < 1 or args.days > 365:
        parser.error("--days must be between 1 and 365")

    load_env()
    accounts: list[tuple[str, str, str]] = []
    for index in range(1, 10):
        label = os.getenv(f"SOCIAL_INSTAGRAM_{index}_LABEL", "")
        token = os.getenv(f"SOCIAL_INSTAGRAM_{index}_PAGE_TOKEN") or os.getenv(f"SOCIAL_INSTAGRAM_{index}_ACCESS_TOKEN", "")
        account_id = os.getenv(f"SOCIAL_INSTAGRAM_{index}_ACCOUNT_ID", "")
        if label and token and account_id:
            accounts.append((label, token, account_id))
    selected = next((a for a in accounts if a[0].lower() == args.account.lower()), accounts[0] if accounts else None)
    if not selected:
        print(json.dumps({"ok": False, "error": "Instagram professional account not configured"}))
        return 2
    label, token, account_id = selected
    ig_login = token.startswith("IG")
    base = "https://graph.instagram.com/v23.0" if ig_login else "https://graph.facebook.com/v25.0"
    cutoff = datetime.now(UTC) - timedelta(days=args.days)
    fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
    media = get_json(base, f"{account_id}/media", {"fields": fields, "limit": "100", "access_token": token})
    records = []
    for item in media.get("data", []):
        try:
            timestamp = datetime.fromisoformat(item.get("timestamp", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if timestamp < cutoff:
            continue
        insight = get_json(base, f"{item.get('id', '')}/insights", {
            "metric": "reach,likes,comments,saved,shares" if ig_login else "impressions,reach,engagement",
            "access_token": token,
        })
        records.append({
            "media_id": item.get("id", ""),
            "permalink": item.get("permalink", ""),
            "timestamp": item.get("timestamp", ""),
            "media_type": item.get("media_type", ""),
            "media_product_type": item.get("media_product_type", ""),
            "caption": item.get("caption", ""),
            "likes": metric_value(insight, "likes") if ig_login else item.get("like_count", "NOT_AVAILABLE"),
            "comments": metric_value(insight, "comments") if ig_login else item.get("comments_count", "NOT_AVAILABLE"),
            "reach": metric_value(insight, "reach"),
            "saved": metric_value(insight, "saved"),
            "shares": metric_value(insight, "shares"),
            "plays": "NOT_SUPPORTED",
            "watch_time": "NOT_SUPPORTED",
            "average_watch_time": "NOT_SUPPORTED",
            "retention": "NOT_SUPPORTED",
            "follows": "NOT_AVAILABLE",
            "profile_visits": "NOT_AVAILABLE",
            "link_clicks": "NOT_AVAILABLE",
        })
    evidence = {
        "ok": not bool(media.get("error")),
        "collector": "scripts/growth_audit.py",
        "collected_at": datetime.now(UTC).isoformat(),
        "days": args.days,
        "account": label,
        "records": records,
        "collection_state": "OK" if not media.get("error") else "COLLECTION_FAILED",
    }
    output = args.output or ROOT / "workspace" / "reports" / f"[C]growth-audit-instagram-evidence-{datetime.now().date()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        display_output = str(output.relative_to(ROOT))
    except ValueError:
        display_output = str(output)
    print(json.dumps({"ok": evidence["ok"], "records": len(records), "output": display_output}))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
