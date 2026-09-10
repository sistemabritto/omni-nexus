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


def retention_status(average_watch_time, duration_s) -> str | float:
    """Approximate completion rate: average_watch_time / video duration.

    Not a real Graph API metric — the API never returns "retention" directly.
    growth_audit.py doesn't have duration_s (it never downloads media, per this
    collector's own contract), so this only resolves when called with a
    duration sourced elsewhere (e.g. ffprobe output from
    scripts/growth_reels_creative_audit.py, keyed by media_id). Returns a
    marker string when duration is unavailable instead of silently claiming
    the platform doesn't support retention — it does, approximately; this
    collector just doesn't have the other half of the fraction.
    """
    if not isinstance(average_watch_time, (int, float)) or not duration_s:
        return "NOT_COMPUTED_HERE:needs duration_s (see growth_reels_creative_audit.py ffprobe output)"
    return round(average_watch_time / duration_s, 4)


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
        is_reel = item.get("media_product_type") == "REELS"
        # `plays` was deprecated Jul 2024 in favor of `views`. Watch-time
        # metrics only exist for Reels — requesting them on a photo/carousel
        # makes the whole /insights call error out, which would wipe
        # reach/likes/etc for that item too (metric_value returns
        # COLLECTION_FAILED for everything when payload.get("error")).
        if ig_login:
            base_metrics = "reach,likes,comments,saved,shares"
            metric_param = f"{base_metrics},views,ig_reels_avg_watch_time,ig_reels_video_view_total_time" if is_reel else base_metrics
        else:
            metric_param = "impressions,reach,engagement"
        insight = get_json(base, f"{item.get('id', '')}/insights", {
            "metric": metric_param,
            "access_token": token,
        })
        average_watch_time = metric_value(insight, "ig_reels_avg_watch_time") if (ig_login and is_reel) else "NOT_SUPPORTED"
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
            "plays": metric_value(insight, "views") if (ig_login and is_reel) else "NOT_SUPPORTED",
            "watch_time": metric_value(insight, "ig_reels_video_view_total_time") if (ig_login and is_reel) else "NOT_SUPPORTED",
            "average_watch_time": average_watch_time,
            # Real API metric, approximated (average_watch_time / duration) — this
            # collector has no duration_s (never downloads media). Pass one in
            # from ffprobe evidence (growth_reels_creative_audit.py) downstream
            # if you need the actual ratio; see retention_status() docstring.
            "retention": retention_status(average_watch_time, None),
            # follows/profile_visits/link_clicks: real platform ceiling, not a
            # missing-parameter bug. These are ACCOUNT-level insights
            # (profile_views, follower_count, website_clicks on
            # /{ig-user-id}/insights) — the API never attributes them to a
            # single Reel. No token/permission/version change unlocks this.
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
