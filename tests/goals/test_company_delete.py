"""Company deletion uses isolated SQLite fixtures, never production data."""
import importlib
import sys
from pathlib import Path

import pytest
from flask import Flask
from flask_login import LoginManager

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
NOW = '2026-10-15T00:00:00.000000Z'

@pytest.fixture(params=[False, True], ids=['fk-off', 'fk-on'])
def app(request, tmp_path, monkeypatch):
    import models
    importlib.reload(models)
    import routes.goals as routes
    importlib.reload(routes)
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='fixture', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    models.db.init_app(app)
    manager = LoginManager(app)
    @manager.user_loader
    def user(uid):return models.db.session.get(models.User, int(uid))
    monkeypatch.setattr(routes, 'WORKSPACE', tmp_path)
    app.register_blueprint(routes.bp)
    with app.app_context():
        models.db.create_all()
        models.db.session.execute(models.db.text('PRAGMA foreign_keys='+('ON' if request.param else 'OFF')))
        models.seed_roles()
        models.db.session.add_all([models.User(id=1,username='fixture-admin',role='admin',password_hash='fixture-unusable'), models.User(id=2,username='fixture-viewer',role='viewer',password_hash='fixture-unusable')])
        models.db.session.add_all([models.Company(id=1,name='Fixture A',slug='a',created_at=NOW,updated_at=NOW),models.Company(id=2,name='Fixture B',slug='b',created_at=NOW,updated_at=NOW)])
        models.db.session.commit()
    return app


def client(app, uid=1):
    c = app.test_client()
    with c.session_transaction() as s:s.update(_user_id=str(uid),_fresh=True)
    return c


def test_empty_company_deleted_without_nonexistent_goal_column(app):
    import models
    c=client(app)
    assert c.delete('/api/companies/2').status_code == 200
    with app.app_context():
        assert models.db.session.get(models.Company,2) is None
        assert models.db.session.get(models.Company,1) is not None
    assert c.delete('/api/companies/2').status_code == 404


@pytest.mark.parametrize('table', ['projects','tickets','media_jobs'])
def test_owned_records_are_not_detached_or_deleted(app,table):
    import models
    with app.app_context():
        if table=='projects':row=models.GoalProject(slug='p',title='Project',company_id=2,created_at=NOW,updated_at=NOW)
        elif table=='tickets':row=models.Ticket(id='t',title='Ticket',company_id=2,status='open',priority='medium',created_at=NOW,updated_at=NOW)
        else:row=models.MediaJob(id='m',title='Fixture media',width=1080,height=1920,duration_seconds=15,brief='fixture',platform='instagram',company_id=2,status='failed',created_at=NOW,updated_at=NOW)
        models.db.session.add(row);models.db.session.commit()
    response=client(app).delete('/api/companies/2')
    assert response.status_code==409
    assert response.json['code']=='company_has_dependencies'
    assert response.json['dependencies'][table]==1
    with app.app_context():
        assert models.db.session.get(models.Company,2) is not None
        assert models.db.session.execute(models.db.text('SELECT company_id FROM '+table)).scalar()==2


def test_viewer_cannot_delete(app):
    assert client(app,2).delete('/api/companies/2').status_code==403
    with app.app_context():
        import models
        assert models.db.session.get(models.Company,2) is not None


def test_database_failure_preserves_company_and_logo(app, monkeypatch, tmp_path):
    import models
    from sqlalchemy.exc import SQLAlchemyError
    logo=tmp_path/'workspace/assets/company-logos/fixture.png'
    logo.parent.mkdir(parents=True);logo.write_bytes(b'fixture')
    with app.app_context():
        company=models.db.session.get(models.Company,2)
        company.logo_path=str(logo.relative_to(tmp_path));models.db.session.commit()
    with monkeypatch.context() as m:
        def fail():raise SQLAlchemyError('fixture commit failure')
        m.setattr(models.db.session,'commit',fail)
        with pytest.raises(SQLAlchemyError):client(app).delete('/api/companies/2')
    assert logo.exists()
    with app.app_context():assert models.db.session.get(models.Company,2) is not None


def test_company_delete_does_not_remove_file_outside_logo_directory(app,tmp_path):
    import models
    unrelated=tmp_path/'unrelated.txt';unrelated.write_text('fixture')
    with app.app_context():
        models.db.session.get(models.Company,2).logo_path='unrelated.txt'
        models.db.session.commit()
    assert client(app).delete('/api/companies/2').status_code==200
    assert unrelated.exists()
