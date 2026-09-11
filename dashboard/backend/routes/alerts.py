"""Ingresso de alerta pra serviço externo que não tem (e não deveria ter)
credencial de Telegram própria.

Existe porque o site (`sistemabritto/site`, Vercel) precisava avisar quando
`POST /api/leads` falha nos dois destinos (Supabase e EvoCRM) — hoje isso vira
silêncio total, já que o frontend dispara `fetch` sem checar resposta. A
primeira versão desse alerta mandava direto pro Telegram a partir do próprio
site, com TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID como env var da Vercel. Errado:
o Nexus já É o canal único de notificação (`notifications.py`, ver o
docstring do módulo) — duplicar a credencial do bot numa segunda plataforma
não ganha nada e só multiplica onde um secret pode vazar.

Este endpoint é o ponto de entrada certo: o site manda o fato ("isso falhou"),
o Nexus decide como avisar (Telegram, hoje; o que for amanhã, sem o site
precisar saber). Autenticado por SITE_ALERT_TOKEN — token dedicado, não
DASHBOARD_API_TOKEN, mesmo raciocínio de APPROVAL_BRIDGE_TOKEN em
`routes/_helpers.py::valid_site_alert_token`.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from routes._helpers import valid_site_alert_token

bp = Blueprint("alerts", __name__)


@bp.route("/api/alerts/site", methods=["POST"])
def alerta_do_site():
    # Redundante com o check em app.py::auth_middleware (que é quem deixa a
    # requisição chegar até aqui sem sessão de usuário) — mas não confia só
    # nele: se algum dia essa rota for tirada da lista de bypass por engano,
    # ela ainda recusa sozinha.
    if not valid_site_alert_token(request.headers.get("Authorization")):
        return jsonify({"error": "Forbidden"}), 403

    dados = request.get_json(silent=True) or {}
    titulo = str(dados.get("titulo") or "Alerta do site").strip()[:200]
    mensagem = str(dados.get("mensagem") or "").strip()[:2000]
    if not mensagem:
        return jsonify({"error": "mensagem é obrigatória"}), 400

    # Import local: notifications.py carrega .env e monta o cliente Telegram
    # no import — mesmo padrão de uso do resto do backend (ex.: heartbeat_runner).
    import notifications

    enviado = notifications.notify_info(titulo, mensagem)
    return jsonify({"enviado": enviado}), 200
