"""
tests/backend/test_share_publico.py

2026-07-27 — o share serve HTML na mesma origem do dashboard.

`_resolve_path_safe` está correto: não há path traversal. O problema é outro,
e a rule `.claude/rules/artifacts.md` o institucionaliza — todo relatório de
agente é HTML publicado por `/share/<token>`, endpoint público e sem
autenticação. Um agente com prompt injetado grava um `<script>` no relatório,
o superadmin abre o link logado, e o script faz `fetch('/api/...')` com a
sessão dele. `HttpOnly` não protege: o script não precisa ler o cookie, só que
o navegador o envie.

Run:
    pytest tests/backend/test_share_publico.py -v
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
    import models as _models

    _app = flask.Flask(__name__)
    _app.config.update(
        TESTING=True,
        SECRET_KEY="test-shares",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'shares.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    _models.db.init_app(_app)
    LoginManager().init_app(_app)

    with _app.app_context():
        _models.db.create_all()

    import routes.shares as _shares
    _app.register_blueprint(_shares.bp)

    yield _app

    for engine in (_models.db._app_engines.pop(_app, None) or {}).values():
        engine.dispose()


def _publicar(app, nome: str, conteudo: str) -> str:
    """Grava um arquivo no workspace e devolve o token do share."""
    import routes.shares as _shares
    from models import FileShare, User, db

    alvo = _shares.WORKSPACE_DIR / "reports" / nome
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(conteudo, encoding="utf-8")

    token = "tok" + "".join(c for c in nome if c.isalnum())
    with app.app_context():
        autor = User(username=f"autor-{token}", role="admin")
        autor.set_password("x")
        db.session.add(autor)
        db.session.flush()
        db.session.add(FileShare(
            token=token,
            path=str(alvo.relative_to(_shares.REPO_ROOT)),
            created_by_id=autor.id,
            created_at=datetime.now(timezone.utc),
            enabled=True,
        ))
        db.session.commit()
    return token, alvo


def test_html_publico_vem_com_csp(app):
    token, alvo = _publicar(app, "[C]teste-csp.html", "<h1>Relatório</h1>")
    try:
        r = app.test_client().get(f"/api/shares/{token}/view")
        assert r.status_code == 200
        csp = r.headers.get("Content-Security-Policy", "")
        assert csp, "share HTML sem CSP: o script roda na origem do dashboard"
        # A origem opaca é o que impede o fetch autenticado.
        assert "sandbox" in csp
        # E nada de script, nem inline nem externo.
        assert "default-src 'none'" in csp
        assert "script-src" not in csp
    finally:
        alvo.unlink(missing_ok=True)


def test_csp_nao_quebra_o_que_a_rule_de_artefatos_exige(app):
    """CSS inline e imagem em data: são exatamente o que artifacts.md pede."""
    token, alvo = _publicar(app, "[C]teste-estilo.html",
                            "<style>body{color:red}</style><img src='data:image/gif;base64,R0lGOD'>")
    try:
        csp = app.test_client().get(f"/api/shares/{token}/view").headers["Content-Security-Policy"]
        assert "style-src 'unsafe-inline'" in csp
        assert "img-src data:" in csp
    finally:
        alvo.unlink(missing_ok=True)


def test_link_do_relatorio_continua_clicavel(app):
    """`sandbox` puro mataria a navegação, e relatório sem link não serve.

    Os dois tokens permitidos são os que nenhum script consegue usar sozinho:
    abrir em nova aba, e navegar a partir de um clique do usuário.
    """
    token, alvo = _publicar(app, "[C]teste-link.html", "<a href='https://x.com/p'>post</a>")
    try:
        csp = app.test_client().get(f"/api/shares/{token}/view").headers["Content-Security-Policy"]
        assert "allow-popups" in csp
        assert "allow-top-navigation-by-user-activation" in csp
        # O que continua proibido é o que dá poder a um script injetado.
        assert "allow-scripts" not in csp
        assert "allow-same-origin" not in csp
        assert "allow-forms" not in csp
    finally:
        alvo.unlink(missing_ok=True)


def test_os_headers_que_ja_existiam_seguem_no_lugar(app):
    token, alvo = _publicar(app, "[C]teste-headers.html", "<p>oi</p>")
    try:
        h = app.test_client().get(f"/api/shares/{token}/view").headers
        assert h["Referrer-Policy"] == "no-referrer"
        assert h["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in h["Cache-Control"]
    finally:
        alvo.unlink(missing_ok=True)
