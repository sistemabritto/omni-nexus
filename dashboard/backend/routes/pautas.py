"""API da fila de pautas — o estado da esteira de conteúdo.

Serve três consumidores diferentes, e é por isso que a fila precisava sair do
markdown: o research semanal escreve nela, a rotina diária lê dela, e o painel
mostra o funil a partir dela. Enquanto era um arquivo, cada um desses três
teria que reimplementar o parsing e nenhum saberia o que o outro fez.

Permissões seguem o recurso `goals` — pauta é trabalho planejado, mesma família
de Mission/Project/Goal/Ticket, e reaproveitar evita inventar um recurso novo
no RBAC só para isto.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request
from flask_login import current_user

from models import has_permission, audit

import pauta_fila

bp = Blueprint("pautas", __name__)


def _require(action: str):
    if not has_permission(current_user.role, "goals", action):
        return jsonify({"error": "Forbidden"}), 403
    return None


@bp.route("/api/pautas", methods=["GET"])
def listar_pautas():
    denied = _require("view")
    if denied:
        return denied
    return jsonify({"pautas": pauta_fila.listar(
        ciclo=request.args.get("ciclo"),
        status=request.args.get("status"),
        limite=int(request.args.get("limit", 100)),
    )})


@bp.route("/api/pautas/resumo", methods=["GET"])
def resumo_pautas():
    """O funil, para o painel de métricas."""
    denied = _require("view")
    if denied:
        return denied
    return jsonify(pauta_fila.resumo())


@bp.route("/api/pautas/hoje", methods=["GET"])
def pautas_de_hoje():
    """O que a rotina diária tem para escrever hoje."""
    denied = _require("view")
    if denied:
        return denied
    dia = request.args.get("dia")
    return jsonify({"pautas": pauta_fila.do_dia(
        date.fromisoformat(dia) if dia else None,
        status=request.args.get("status", "aprovada"),
    )})


@bp.route("/api/pautas", methods=["POST"])
def gravar_pautas():
    """Grava um ciclo inteiro — é assim que o research abastece a fila."""
    denied = _require("manage")
    if denied:
        return denied
    dados = request.get_json(silent=True) or {}
    pautas = dados.get("pautas")
    if not isinstance(pautas, list) or not pautas:
        return jsonify({"error": "pautas deve ser uma lista não vazia"}), 400
    try:
        resultado = pauta_fila.gravar_ciclo(pautas)
    except (KeyError, ValueError) as exc:
        return jsonify({"error": f"pauta malformada: {exc}"}), 400
    audit(current_user, "create", "pautas",
          f"gravou {resultado['gravadas']} pautas na fila")
    return jsonify(resultado), 201


@bp.route("/api/pautas/<int:pauta_id>", methods=["PATCH"])
def mover_pauta(pauta_id: int):
    denied = _require("manage")
    if denied:
        return denied
    dados = request.get_json(silent=True) or {}
    novo = dados.get("status")
    if novo not in pauta_fila.STATUS:
        return jsonify({"error": f"status inválido; aceita {list(pauta_fila.STATUS)}"}), 400
    ok = pauta_fila.mover(
        pauta_id, novo,
        ghost_post_id=dados.get("ghost_post_id"),
        ghost_url=dados.get("ghost_url"),
        titulo=dados.get("titulo"),
        motivo=dados.get("motivo"),
    )
    if not ok:
        return jsonify({"error": "pauta não encontrada"}), 404
    audit(current_user, "update", "pautas", f"pauta {pauta_id} -> {novo}")
    return jsonify({"id": pauta_id, "status": novo})


@bp.route("/api/pautas/ciclo/<ciclo>/aprovar", methods=["POST"])
def aprovar_ciclo(ciclo: str):
    """Libera a semana inteira — a decisão do humano é em lote."""
    denied = _require("manage")
    if denied:
        return denied
    n = pauta_fila.aprovar_ciclo(ciclo)
    audit(current_user, "update", "pautas", f"aprovou {n} pautas do ciclo {ciclo}")
    return jsonify({"ciclo": ciclo, "aprovadas": n})


@bp.route("/api/pautas/vencer", methods=["POST"])
def vencer_pautas():
    """Descarta o que passou da data — chamado pela rotina diária."""
    denied = _require("manage")
    if denied:
        return denied
    n = pauta_fila.vencer_atrasadas()
    return jsonify({"descartadas": n})
