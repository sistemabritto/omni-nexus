"""Create only ephemeral fixture DB/config; never import application workers."""
from pathlib import Path
import sys
from flask import Flask
sys.path.insert(0, '/workspace/dashboard/backend')
from models import db, User, seed_roles
config = Path('/workspace/config')
config.mkdir(parents=True, exist_ok=True)
(config/'.env').write_text('EVONEXUS_SECRET_KEY=fixture-image-smoke-only\nBRAIN_REPO_MASTER_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\nKNOWLEDGE_MASTER_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\nDASHBOARD_API_TOKEN=fixture-agent-token\nGEMINI_LIVE_ENABLED=false\nGEMINI_FREE_TIER_VERIFIED=false\nGEMINI_API_KEY=\nGEMINI_LIVE_MODEL=\nTELEGRAM_CHAT_ID=\n')
(config/'heartbeats.yaml').write_text('heartbeats: []\n')
(config/'providers.json').write_text('{"active_provider":null,"providers":{}}\n')
app = Flask(__name__)
app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:////workspace/dashboard/data/evonexus.db', SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)
with app.app_context():
    db.create_all()
    seed_roles()
    assert User.query.count() == 0
    user = User(username='smoke-admin', role='admin', onboarding_state='completed')
    user.set_password('Fixture!Smoke42')
    db.session.add(user)
    db.session.commit()
print('EPHEMERAL_SUPERVISOR_FIXTURES_READY')
