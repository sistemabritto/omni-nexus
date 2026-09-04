"""
tests/backend/test_share_click_e_gate_publico.py

`/api/shares/<token>/click` precisa passar pelo gate público em
`app.py::auth_middleware` — a mesma exceção que já existia só para `/view`.
Achado ao vivo em 04/09/2026: a rota funcionava sozinha (ver
test_share_click_tracking.py, que monta um Flask app isolado sem o
middleware real) e devolvia 401 em produção, porque
`auth_middleware` só liberava caminhos com `"/view" in path`.

Este teste não importa `app.py` inteiro — fazer isso acorda o scheduler e os
heartbeats de produção (ver LEARNINGS.md / memória "Importar app.py acorda
heartbeat", o import nunca termina por design). Em vez disso, confere
estaticamente que a condição do gate público inclui `/click`, o que é
suficiente pra pegar a regressão exata que aconteceu aqui sem pagar o custo
de rodar a aplicação inteira. A verificação end-to-end de verdade é o curl
contra a VPS depois do deploy — isso aqui é a rede de segurança pro próximo
PR que mexer nessa linha sem saber da história.

Run:
    pytest tests/backend/test_share_click_e_gate_publico.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PY = REPO_ROOT / "dashboard" / "backend" / "app.py"


def _trecho_do_gate_publico() -> str:
    """Isola só a condição de PUBLIC_PATHS dentro de auth_middleware, sem
    importar o módulo — regex sobre o texto, não execução."""
    texto = APP_PY.read_text(encoding="utf-8")
    m = re.search(
        r"def auth_middleware\(\):.*?return jsonify\(\{\"error\": \"Authentication required\"\}\), 401",
        texto, re.S,
    )
    assert m, "não achei o corpo de auth_middleware em app.py — função foi renomeada ou movida?"
    return m.group(0)


def test_gate_publico_libera_view_e_click_mas_nao_events():
    corpo = _trecho_do_gate_publico()
    assert '"/api/shares/"' in corpo, "app.py não referencia mais /api/shares/ no gate público"
    assert '"/view" in path' in corpo
    assert '"/click" in path' in corpo, (
        "regressão: /click precisa estar no gate público igual /view, senão "
        "o redirect de CTA do artefato devolve 401 antes de chegar na rota"
    )
    # /events é intencionalmente autenticado (routes/shares.py::list_share_events
    # já carrega @login_required + @require_permission) — não deve ganhar um
    # passe livre aqui por engano numa futura edição desta condição.
    assert '"/events" in path' not in corpo


def test_rota_click_nao_tem_login_required_proprio():
    """A rota em si não pode duplicar @login_required — senão o gate público
    do app.py libera a requisição e o decorator da rota barra de novo,
    voltando ao mesmo 401 que este teste existe para prevenir."""
    shares_py = (REPO_ROOT / "dashboard" / "backend" / "routes" / "shares.py").read_text(encoding="utf-8")
    m = re.search(
        r'@bp\.route\("/api/shares/<token>/click".*?\ndef click_share',
        shares_py, re.S,
    )
    assert m, "rota /click não encontrada em routes/shares.py"
    assert "login_required" not in m.group(0)


def test_rota_events_continua_autenticada():
    """O inverso do teste acima: /events tem que continuar exigindo login,
    porque só é liberado no gate público condicionalmente — se alguém tirar
    o decorator daqui achando que o gate público já cobre, os cliques de
    todo mundo ficam legíveis por qualquer visitante anônimo do link."""
    shares_py = (REPO_ROOT / "dashboard" / "backend" / "routes" / "shares.py").read_text(encoding="utf-8")
    m = re.search(
        r'@bp\.route\("/api/shares/<token>/events".*?\ndef list_share_events',
        shares_py, re.S,
    )
    assert m, "rota /events não encontrada em routes/shares.py"
    assert "login_required" in m.group(0)
    assert 'require_permission("workspace", "manage")' in m.group(0)
