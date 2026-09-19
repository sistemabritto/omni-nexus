"""Routes /api/reels — coprodutor de reels (P1 revamp).

Auth: Bearer DASHBOARD_API_TOKEN resolvido pelo before_request global de app.py
(_try_api_token_auth) — mesmo contrato que /api/tickets usa para o bridge.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user
from models import has_permission
from reels_copilot import (
    tick, generate_reel, decide, mirror_posted,
    pipeline_summary, list_recent, get_in_flight, _connect,
    _ensure_reels_table,
)

bp = Blueprint("reels", __name__)


def _deny():
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401
    if not has_permission(current_user.role, "goals", "manage"):
        return jsonify({"error": "Forbidden"}), 403
    return None


@bp.route("/api/reels")
def list_reels():
    denied = _deny()
    if denied:
        return denied
    conn = _connect()
    try:
        _ensure_reels_table(conn)
        rows = [dict(r) for r in list_recent(conn)]
        in_flight = get_in_flight(conn)
        if in_flight:
            in_flight = dict(in_flight)
    finally:
        conn.close()
    return jsonify({"reels": rows, "in_flight": in_flight, "summary": pipeline_summary()})


@bp.route("/api/reels/tick", methods=["POST"])
def trigger_tick():
    denied = _deny()
    if denied:
        return denied
    return jsonify(tick())


@bp.route("/api/reels/generate", methods=["POST"])
def trigger_generate():
    denied = _deny()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    res = generate_reel(theme_hint=data.get("theme_hint"))
    return jsonify(res), (201 if res.get("ok") else 400)


@bp.route("/api/reels/<reel_id>/decide", methods=["POST"])
def reel_decide(reel_id):
    denied = _deny()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    res = decide(reel_id, data.get("decision", ""), feedback=data.get("feedback", ""))
    return jsonify(res), (200 if res.get("ok") else 400)


@bp.route("/api/reels/<reel_id>/mirror", methods=["POST"])
def reel_mirror(reel_id):
    denied = _deny()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    res = mirror_posted(reel_id, ig_url=data.get("ig_url"))
    return jsonify(res), (200 if res.get("ok") else 400)
