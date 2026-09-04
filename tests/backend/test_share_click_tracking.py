"""
tests/backend/test_share_click_tracking.py

Um artefato público (`/share/<token>`) roda com CSP `default-src 'none'`
(ver test_share_publico.py) — nenhum `fetch()` de JS embutido sobrevive a
isso, de propósito, contra prompt injection lendo a sessão do superadmin.

Então o CTA de um artefato não pode medir clique via JS. `/api/shares/<token>
/click` é a alternativa: um `<a href>` puro, sem script, que registra o
evento no servidor antes de redirecionar. O ponto sensível é que essa rota
é pública (mesma razão de `/view`: quem lê o artefato é anônimo) — e uma
rota pública que redireciona para onde o parâmetro mandar, sem allowlist, é
um open redirect a partir de um domínio confiável, útil para phishing.

Run:
    pytest tests/backend/test_share_click_tracking.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))


@pytest.fixture
def app(tmp_path):
    import flask
    from flask_login import LoginManager
    import importlib
    import models as _models
    importlib.reload(_models)

    _app = flask.Flask(__name__)
    _app.config.update(
        TESTING=True,
        SECRET_KEY="test-shares",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'shares.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    _models.db.init_app(_app)
    login_manager = LoginManager()
    login_manager.init_app(_app)

    @login_manager.user_loader
    def _load_user(user_id):
        return _models.User.query.get(int(user_id))

    with _app.app_context():
        _models.db.create_all()

    import routes.shares as _shares
    importlib.reload(_shares)
    _app.register_blueprint(_shares.bp)

    yield _app

    for engine in (_models.db._app_engines.pop(_app, None) or {}).values():
        engine.dispose()


def _share(app, token: str = "tokclick01"):
    from models import FileShare, User, db
    with app.app_context():
        autor = User(username=f"autor-{token}", role="admin")
        autor.set_password("x")
        db.session.add(autor)
        db.session.flush()
        db.session.add(FileShare(
            token=token,
            path="reports/[C]exemplo.html",
            created_by_id=autor.id,
            created_at=datetime.now(timezone.utc),
            enabled=True,
        ))
        db.session.commit()
    return token


def test_clique_redireciona_e_registra_evento(app):
    token = _share(app)
    r = app.test_client().get(
        f"/api/shares/{token}/click",
        query_string={"to": "https://sistemabritto.com.br/desafio-monetizar-com-ia", "label": "cta-desafio"},
    )
    assert r.status_code == 302
    assert r.headers["Location"] == "https://sistemabritto.com.br/desafio-monetizar-com-ia"

    with app.app_context():
        from models import ShareEvent
        eventos = ShareEvent.query.filter_by(token=token).all()
        assert len(eventos) == 1
        assert eventos[0].event_type == "cta_click"
        assert eventos[0].meta == "cta-desafio"


def test_host_fora_do_allowlist_e_recusado_sem_redirecionar(app):
    token = _share(app)
    r = app.test_client().get(
        f"/api/shares/{token}/click",
        query_string={"to": "https://evil.example.com/phish"},
    )
    assert r.status_code == 400
    with app.app_context():
        from models import ShareEvent
        assert ShareEvent.query.filter_by(token=token).count() == 0


@pytest.mark.parametrize("destino", [
    "http://sistemabritto.com.br/whatsapp",          # sem https
    "https://sistemabritto.com.br.evil.com/x",         # host parecido, domínio diferente
    "javascript:alert(1)",                              # esquema não-http
    "https://blog.sistemabritto.com.br@evil.com/",      # userinfo pra confundir parser
])
def test_variantes_de_bypass_do_allowlist_sao_recusadas(app, destino):
    token = _share(app)
    r = app.test_client().get(f"/api/shares/{token}/click", query_string={"to": destino})
    assert r.status_code == 400, destino
    with app.app_context():
        from models import ShareEvent
        assert ShareEvent.query.filter_by(token=token).count() == 0


def test_token_inexistente_devolve_404_sem_redirecionar(app):
    r = app.test_client().get(
        "/api/shares/nao-existe/click",
        query_string={"to": "https://sistemabritto.com.br/whatsapp"},
    )
    assert r.status_code == 404


def test_sem_login_a_leitura_de_eventos_e_recusada(app):
    token = _share(app)
    r = app.test_client().get(f"/api/shares/{token}/events")
    assert r.status_code in (302, 401, 403)


def test_to_dict_inclui_click_count_pra_aparecer_na_interface(app):
    """A tabela de Links de Compartilhamento no Nexus (ShareLinks.tsx) lê
    click_count do JSON de /api/shares — sem isso no to_dict(), a coluna
    "Cliques" da interface fica sempre vazia mesmo com clique registrado."""
    token = _share(app)
    with app.app_context():
        from models import FileShare, ShareEvent, db
        db.session.add(ShareEvent(token=token, event_type="cta_click", meta="cta-x"))
        db.session.add(ShareEvent(token=token, event_type="cta_click", meta="cta-y"))
        db.session.commit()
        share = FileShare.query.filter_by(token=token).first()
        assert share.to_dict()["click_count"] == 2


def test_to_dict_nao_conta_outros_tipos_de_evento_como_clique(app):
    token = _share(app)
    with app.app_context():
        from models import FileShare, ShareEvent, db
        db.session.add(ShareEvent(token=token, event_type="algo_futuro_nao_cta", meta="x"))
        db.session.commit()
        share = FileShare.query.filter_by(token=token).first()
        assert share.to_dict()["click_count"] == 0
