"""API da série histórica de crescimento.

Existe porque a rotina de coleta roda no container do scheduler, que não monta
o volume do banco — escrever em sqlite direto de lá criaria um banco fantasma
na camada efêmera do container, exatamente como já aconteceu com a fila de
pautas. Uma fonte de verdade só, alcançável por HTTP.

Permissões seguem `goals`: métrica de crescimento é resultado de trabalho
planejado, mesma família de Mission/Project/Goal.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user

from models import has_permission, audit

import metricas_crescimento as mc

bp = Blueprint("metricas", __name__)


def _require(action: str):
    if not has_permission(current_user.role, "goals", action):
        return jsonify({"error": "Forbidden"}), 403
    return None


@bp.route("/api/metricas", methods=["POST"])
def gravar_metricas():
    denied = _require("manage")
    if denied:
        return denied
    dados = request.get_json(silent=True) or {}
    medicoes = dados.get("medicoes")
    if not isinstance(medicoes, list) or not medicoes:
        return jsonify({"error": "medicoes deve ser uma lista não vazia"}), 400
    try:
        gravadas = mc.gravar(medicoes)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"medição malformada: {exc}"}), 400
    audit(current_user, "create", "metricas", f"gravou {gravadas} medições")
    return jsonify({"gravadas": gravadas}), 201


@bp.route("/api/metricas/resumo", methods=["GET"])
def resumo_metricas():
    """O painel de crescimento — onde estamos e para onde está indo."""
    denied = _require("view")
    if denied:
        return denied
    return jsonify(mc.resumo())


@bp.route("/api/metricas/serie", methods=["GET"])
def serie_metrica():
    """Evolução de uma métrica — o que responde 'está crescendo?'."""
    denied = _require("view")
    if denied:
        return denied
    metrica = request.args.get("metrica")
    if not metrica:
        return jsonify({"error": "informe ?metrica="}), 400
    return jsonify({
        "metrica": metrica,
        "pontos": mc.serie(metrica, origem=request.args.get("origem"),
                           dias=int(request.args.get("dias", 30))),
        "variacao": mc.variacao(metrica, dias=int(request.args.get("dias", 30))),
    })
