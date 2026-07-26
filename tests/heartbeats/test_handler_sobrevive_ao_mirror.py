"""
tests/heartbeats/test_handler_sobrevive_ao_mirror.py

2026-07-26 — heartbeat in-process criado pela API nascia morto.

`POST /api/heartbeats` validava, escrevia o YAML com `handler` correto,
respondia 201, e o espelho no banco descartava justamente o `handler`. O
dispatcher lê do banco, não do YAML (heartbeat_runner.py, "if hb['agent'] ==
'system' and not hb.get('handler')"), então a primeira execução morria com
`no script for <id>` — com o YAML na tela dizendo que estava tudo certo.

Descoberto ao criar `confirmar-publicacoes` na VPS. Vale para a UI também:
o wizard usa o mesmo endpoint.

Run:
    pytest tests/heartbeats/test_handler_sobrevive_ao_mirror.py -v
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture
def app(tmp_path, monkeypatch):
    import flask
    from flask_login import LoginManager
    import models as _models
    importlib.reload(_models)

    _app = flask.Flask(__name__)
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-handler-mirror"
    _app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    _app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    _models.db.init_app(_app)

    login_manager = LoginManager()
    login_manager.init_app(_app)

    @login_manager.user_loader
    def _load_user(user_id):
        return _models.User.query.get(int(user_id))

    with _app.app_context():
        _models.db.create_all()
        admin = _models.User(username="admin", role="admin")
        admin.set_password("password")
        _models.db.session.add(admin)
        _models.db.session.commit()

    import routes.heartbeats as _hb_routes
    importlib.reload(_hb_routes)

    # YAML isolado: o teste não pode escrever no config real do workspace.
    yaml_path = tmp_path / "heartbeats.yaml"
    yaml_path.write_text("heartbeats: []\n", encoding="utf-8")
    import heartbeat_schema

    monkeypatch.setattr(heartbeat_schema, "HEARTBEATS_YAML", yaml_path, raising=False)
    monkeypatch.setattr(_hb_routes, "_load_yaml_config",
                        lambda: heartbeat_schema.HeartbeatsFile(heartbeats=[]))
    salvos = []
    monkeypatch.setattr(_hb_routes, "_save_yaml_config", lambda cfg: salvos.append(cfg))

    # Cinto e suspensório. A rota já não re-registra sob TESTING, mas
    # register_interval_jobs lê o banco REAL do workspace e dispara catch-up
    # do que estiver vencido — num PATCH de teste isso acordou o
    # nexus-orchestrator, que invocou o hawk-debugger de verdade. Um teste
    # jamais pode custar token nem mexer em ticket de produção.
    import heartbeat_dispatcher

    monkeypatch.setattr(heartbeat_dispatcher, "register_interval_jobs", lambda: None)

    _app.register_blueprint(_hb_routes.bp)
    _app._salvos = salvos
    return _app


@pytest.fixture
def admin_client(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["_user_id"] = "1"
            sess["_fresh"] = True
        yield c


CORPO = {
    "id": "confirmar-publicacoes",
    "agent": "system",
    "interval_seconds": 1200,
    "max_turns": 0,
    "timeout_seconds": 120,
    "lock_timeout_seconds": 1800,
    "wake_triggers": ["interval", "manual"],
    "enabled": True,
    "goal_id": None,
    "required_secrets": [],
    "handler": "publicacoes.tick",
    "decision_prompt": "",
}


def test_handler_chega_ao_banco(app, admin_client):
    """O dispatcher lê do banco. Handler perdido aqui = heartbeat morto."""
    resposta = admin_client.post("/api/heartbeats", json=CORPO)
    assert resposta.status_code == 201, resposta.get_json()

    import models as _models

    with app.app_context():
        gravado = _models.Heartbeat.query.get("confirmar-publicacoes")
        assert gravado.handler == "publicacoes.tick"


def test_resposta_da_api_mostra_o_handler(admin_client):
    """Sem o handler no corpo, um 201 não distingue heartbeat vivo de morto."""
    resposta = admin_client.post("/api/heartbeats", json=CORPO)
    assert resposta.get_json()["handler"] == "publicacoes.tick"


def test_heartbeat_sem_handler_continua_sem_handler(app, admin_client):
    """Heartbeat de agente Claude não tem handler — e não pode ganhar um."""
    corpo = {**CORPO, "id": "atlas-teste", "agent": "atlas-project", "max_turns": 5,
             "decision_prompt": "Checa o Linear e decide se age agora ou espera."}
    corpo.pop("handler")
    assert admin_client.post("/api/heartbeats", json=corpo).status_code == 201

    import models as _models

    with app.app_context():
        assert _models.Heartbeat.query.get("atlas-teste").handler is None


def test_edicao_preserva_o_handler(app, admin_client):
    """PATCH no intervalo não pode zerar o handler pelo caminho."""
    admin_client.post("/api/heartbeats", json=CORPO)
    resposta = admin_client.patch("/api/heartbeats/confirmar-publicacoes",
                                  json={"interval_seconds": 900})
    assert resposta.status_code == 200, resposta.get_json()

    import models as _models

    with app.app_context():
        gravado = _models.Heartbeat.query.get("confirmar-publicacoes")
        assert gravado.handler == "publicacoes.tick"
        assert gravado.interval_seconds == 900
