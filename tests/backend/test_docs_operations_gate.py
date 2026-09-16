"""Pentest finding #1 (2026-09-16): docs/operations/ (internal ops/incident
writeups — real VPS hostnames, SSH aliases, live share tokens) was reachable
through the same public /api/docs endpoint as product documentation
(getting-started, guides, agents, skills...). Fixed by excluding
docs/operations/ from the anonymous tree and gating its content behind auth,
while keeping the rest of docs/ public by design (routes/docs.py's own
docstring, and it's this OSS project's user-facing doc site).

Mirrors tests/backend/test_health_routes.py's isolated-app pattern — a
standalone Flask app with just the docs blueprint + LoginManager, never
`import app` (see memory: importing dashboard/backend/app.py starts real
dispatcher/janitor threads and can wake production heartbeats).
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
def docs_root(tmp_path):
    docs = tmp_path / "docs"
    (docs / "guides").mkdir(parents=True)
    (docs / "operations").mkdir(parents=True)

    (docs / "getting-started.md").write_text("# Getting Started\n\nPublic product docs.\n", encoding="utf-8")
    (docs / "guides" / "install.md").write_text("# Install\n\nHow to install.\n", encoding="utf-8")
    (docs / "operations" / "vps-incident.md").write_text(
        "# VPS incident\n\nHost: swissnode, SSH alias `evo-nexus-vps`. Share token: abc123.\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def app(docs_root, monkeypatch):
    import flask
    from flask_login import LoginManager
    import models as _models
    import routes.docs as _docs

    importlib.reload(_models)
    importlib.reload(_docs)
    monkeypatch.setattr(_docs, "WORKSPACE", docs_root)
    monkeypatch.setattr(_docs, "DOCS_DIR", docs_root / "docs")
    monkeypatch.setattr(_docs, "IMGS_DIR", docs_root / "docs" / "imgs")

    _app = flask.Flask(__name__)
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-secret-docs"
    _app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    _app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    _models.db.init_app(_app)

    login_manager = LoginManager()
    login_manager.init_app(_app)

    @login_manager.user_loader
    def load_user(user_id):
        return _models.User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        return flask.jsonify({"error": "Authentication required"}), 401

    _app.register_blueprint(_docs.bp)

    with _app.app_context():
        _models.db.create_all()
        _models.seed_roles()
        admin = _models.User(username="admin", email="admin@example.com", display_name="Admin", role="admin")
        admin.set_password("Strong!234")
        _models.db.session.add(admin)
        _models.db.session.commit()

    return _app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _login_as(client, username):
    with client.session_transaction() as session:
        from models import User
        user = User.query.filter_by(username=username).one()
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_anonymous_tree_excludes_operations(client):
    response = client.get("/api/docs")
    payload = response.get_json()

    assert response.status_code == 200
    slugs = {section["slug"] for section in payload["sections"]}
    assert "operations" not in slugs
    # Public sections must still be present — this is a carve-out, not a lockdown.
    assert "getting-started" in slugs
    assert "guides" in slugs


def test_authenticated_tree_includes_operations(client, app):
    with app.test_request_context():
        _login_as(client, "admin")
    response = client.get("/api/docs")
    payload = response.get_json()

    assert response.status_code == 200
    slugs = {section["slug"] for section in payload["sections"]}
    assert "operations" in slugs


def test_anonymous_cannot_read_operations_content(client):
    response = client.get("/api/docs/operations/vps-incident.md")
    assert response.status_code == 401


def test_authenticated_can_read_operations_content(client, app):
    with app.test_request_context():
        _login_as(client, "admin")
    response = client.get("/api/docs/operations/vps-incident.md")
    assert response.status_code == 200
    assert "swissnode" in response.get_data(as_text=True)


def test_anonymous_can_still_read_public_content(client):
    response = client.get("/api/docs/guides/install.md")
    assert response.status_code == 200
    assert "How to install" in response.get_data(as_text=True)
