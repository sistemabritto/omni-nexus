"""Boot the real image's Flask application with an ephemeral fixture user.

The CI container has --network none, no production mounts and no credentials.
The production entrypoint/supervisor isn't invoked: this isolates Flask boot
without launching terminal CLIs or the main-only chat/task polling workers.
"""
import contextlib
import os
from pathlib import Path
import sys

assert os.environ['GEMINI_LIVE_ENABLED'] == 'false'
assert os.environ['GEMINI_FREE_TIER_VERIFIED'] == 'false'
assert not os.environ.get('GEMINI_API_KEY')
assert not Path('/workspace/.env').exists(), 'unexpected environment file in image'
sys.path.insert(0, '/workspace/dashboard/backend')
Path('/workspace/dashboard/data').mkdir(parents=True, exist_ok=True)
try:
    # Keep boot logs private inside the ephemeral container. Never upload them.
    with open('/tmp/app-boot.log', 'w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        import app as application
        from models import User, db
        with application.app.app_context():
            assert User.query.count() == 0, 'fixture data mount must start empty'
            user = User(username='smoke-admin', display_name='Isolated smoke', role='admin', onboarding_state='completed')
            user.set_password('Fixture!Smoke42')
            db.session.add(user)
            db.session.commit()
except Exception as error:
    print('IMAGE_BOOT_FAILED: ' + type(error).__name__, flush=True)
    raise SystemExit(1) from None
print('IMAGE_FLASK_BOOT_READY', flush=True)
application.app.run(host='127.0.0.1', port=8080, threaded=True, use_reloader=False)
