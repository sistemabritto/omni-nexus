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
import feedback_audio

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


@bp.route("/api/pautas/<int:pauta_id>/keyword", methods=["PATCH"])
def editar_keyword(pauta_id: int):
    """Troca a keyword — devolve pra 'proposta' se estava 'aprovada' (ver pauta_fila.editar_keyword)."""
    denied = _require("manage")
    if denied:
        return denied
    dados = request.get_json(silent=True) or {}
    nova = (dados.get("keyword") or "").strip()
    if not nova:
        return jsonify({"error": "keyword obrigatória"}), 400
    ok = pauta_fila.editar_keyword(pauta_id, nova)
    if not ok:
        return jsonify({"error": "pauta não encontrada"}), 404
    audit(current_user, "update", "pautas", f"pauta {pauta_id} keyword -> {nova}")
    return jsonify({"id": pauta_id, "keyword": nova})


@bp.route("/api/pautas/<int:pauta_id>/feedback-audio", methods=["POST"])
def feedback_audio_pauta(pauta_id: int):
    """Grava feedback falado como `motivo` da pauta, sem mudar o status dela."""
    denied = _require("manage")
    if denied:
        return denied
    arquivo = request.files.get("audio")
    if not arquivo:
        return jsonify({"error": "audio obrigatório (multipart, campo 'audio')"}), 400
    pauta = pauta_fila.buscar(pauta_id)
    if not pauta:
        return jsonify({"error": "pauta não encontrada"}), 404
    try:
        texto = feedback_audio.transcrever_audio(arquivo.stream, arquivo.filename or "audio.webm")
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    pauta_fila.mover(pauta_id, pauta["status"], motivo=texto)
    audit(current_user, "update", "pautas", f"pauta {pauta_id} feedback em áudio")
    return jsonify({"id": pauta_id, "motivo": texto})


@bp.route("/api/pautas/ciclo/<ciclo>/aprovar", methods=["POST"])
def aprovar_ciclo(ciclo: str):
    """Libera a semana inteira — a decisão do humano é em lote."""
    denied = _require("manage")
    if denied:
        return denied
    n = pauta_fila.aprovar_ciclo(ciclo)
    audit(current_user, "update", "pautas", f"aprovou {n} pautas do ciclo {ciclo}")
    return jsonify({"ciclo": ciclo, "aprovadas": n})


@bp.route("/api/pautas/keywords", methods=["POST"])
def keywords_cache():
    """Consulta o cache de keywords e diz quais seeds ainda precisam da API.

    Existe para o research não pagar duas vezes pela mesma pergunta: volume de
    busca do DataForSEO é média de 12 meses e não muda de uma semana para a
    outra. `guardar` no corpo grava o resultado de uma seed recém-consultada.
    """
    denied = _require("manage")
    if denied:
        return denied
    dados = request.get_json(silent=True) or {}

    guardar = dados.get("guardar")
    if isinstance(guardar, dict):
        for seed, linhas in guardar.items():
            if isinstance(linhas, list):
                pauta_fila.guardar_keywords(seed, linhas)
        return jsonify({"guardadas": len(guardar)})

    seeds = dados.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        return jsonify({"error": "informe seeds (lista) ou guardar (objeto)"}), 400
    conhecidas, faltando = pauta_fila.keywords_em_cache([s for s in seeds if isinstance(s, str)])
    return jsonify({"linhas": list(conhecidas.values()), "faltando": faltando,
                    "em_cache": len(seeds) - len(faltando)})


@bp.route("/api/pautas/vencer", methods=["POST"])
def vencer_pautas():
    """Descarta o que passou da data — chamado pela rotina diária."""
    denied = _require("manage")
    if denied:
        return denied
    n = pauta_fila.vencer_atrasadas()
    return jsonify({"descartadas": n})
