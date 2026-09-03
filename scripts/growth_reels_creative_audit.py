#!/usr/bin/env python3
"""Read-only creative evidence batch for owned Instagram Reels.

Uses official Graph media URLs for the account owner, ffprobe/ffmpeg for
deterministic processing and the existing Groq transcription module. It makes
no publication or CRM mutations. Outputs only local audit artifacts.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard" / "backend"))
from transcricao import extrair_audio_16k, transcrever_palavras  # noqa: E402


def load_env() -> None:
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if raw and not raw.startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def get_json(base: str, path: str, params: dict[str, str]) -> dict:
    url = f"{base}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=45) as response:
            return json.loads(response.read().decode())
    except Exception as exc:
        return {"error": type(exc).__name__}


def ffprobe(video: Path) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(video)], capture_output=True, text=True)
    if result.returncode:
        return {"error": "FFPROBE_FAILED"}
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video_stream = next((x for x in streams if x.get("codec_type") == "video"), {})
    audio_stream = next((x for x in streams if x.get("codec_type") == "audio"), {})
    return {
        "duration_s": float(data.get("format", {}).get("duration") or 0),
        "format": data.get("format", {}).get("format_name"),
        "bitrate": data.get("format", {}).get("bit_rate"),
        "video": {k: video_stream.get(k) for k in ("codec_name", "width", "height", "r_frame_rate", "bit_rate")},
        "audio": {k: audio_stream.get(k) for k in ("codec_name", "sample_rate", "channels", "bit_rate")},
    }


def frame_times(duration: float) -> list[float]:
    return [t for t in (0.0, 0.5, 1.0, 2.0, 3.0, 5.0) if t <= duration]


def extract_frames(video: Path, destination: Path, duration: float) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    produced = []
    for seconds in frame_times(duration):
        name = destination / f"t-{seconds:05.1f}.jpg"
        result = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(seconds), "-i", str(video), "-frames:v", "1", "-q:v", "3", str(name)], capture_output=True, text=True)
        if result.returncode == 0 and name.exists():
            produced.append(name.name)
    return produced


def words_to_segments(words: list) -> list[dict]:
    # A word timestamp is the authoritative granular source. Grouping avoids a
    # huge JSON while retaining a timestamped complete transcript.
    output, bucket = [], []
    start = end = 0.0
    for word in words:
        if not bucket:
            start = word.inicio
        bucket.append(word.texto)
        end = word.fim
        if len(bucket) >= 18 or word.texto.endswith((".", "?", "!")):
            output.append({"start": round(start, 2), "end": round(end, 2), "text": " ".join(bucket)})
            bucket = []
    if bucket:
        output.append({"start": round(start, 2), "end": round(end, 2), "text": " ".join(bucket)})
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0, help="0 means every Reel in the period")
    parser.add_argument("--workdir", type=Path, default=Path("/tmp/omni-growth-reels"))
    args = parser.parse_args()
    load_env()
    token = os.getenv("SOCIAL_INSTAGRAM_1_PAGE_TOKEN") or os.getenv("SOCIAL_INSTAGRAM_1_ACCESS_TOKEN", "")
    account = os.getenv("SOCIAL_INSTAGRAM_1_ACCOUNT_ID", "")
    if not token or not account:
        print(json.dumps({"ok": False, "error": "INSTAGRAM_NOT_CONFIGURED"}))
        return 2
    base = "https://graph.instagram.com/v23.0" if token.startswith("IG") else "https://graph.facebook.com/v25.0"
    media = get_json(base, f"{account}/media", {"fields": "id,permalink,timestamp,media_type,media_product_type,caption,media_url", "limit": "100", "access_token": token})
    if media.get("error"):
        print(json.dumps({"ok": False, "error": "MEDIA_COLLECTION_FAILED"}))
        return 1
    cutoff = datetime.now(UTC) - timedelta(days=args.days)
    reels = []
    for item in media.get("data", []):
        timestamp = datetime.fromisoformat(item.get("timestamp", "").replace("Z", "+00:00"))
        if timestamp >= cutoff and item.get("media_product_type") == "REELS":
            reels.append(item)
    reels.sort(key=lambda item: item.get("timestamp", ""))
    if args.limit:
        reels = reels[:args.limit]
    args.workdir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, item in enumerate(reels, 1):
        short = item["id"][-8:]
        job = args.workdir / short
        job.mkdir(parents=True, exist_ok=True)
        video = job / "reel.mp4"
        outcome = {"media_id": item["id"], "permalink": item.get("permalink"), "timestamp": item.get("timestamp"), "caption": item.get("caption", ""), "status": "OK"}
        try:
            with urllib.request.urlopen(item["media_url"], timeout=90) as source:
                video.write_bytes(source.read())
            outcome["ffprobe"] = ffprobe(video)
            duration = outcome["ffprobe"].get("duration_s", 0)
            outcome["early_frames"] = extract_frames(video, job / "frames", duration)
            audio = extrair_audio_16k(video, job / "audio.wav")
            words = transcrever_palavras(audio, trabalho=job / "transcription")
            outcome["transcript"] = words_to_segments(words)
            outcome["transcript_word_count"] = len(words)
        except Exception as exc:
            outcome["status"] = "COLLECTION_FAILED"
            outcome["error"] = type(exc).__name__
        results.append(outcome)
        print(json.dumps({"progress": f"{index}/{len(reels)}", "status": outcome["status"], "media_id_suffix": short}), flush=True)
    output = args.workdir / "creative-evidence.json"
    output.write_text(json.dumps({"collected_at": datetime.now(UTC).isoformat(), "days": args.days, "reels": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "reels": len(results), "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
