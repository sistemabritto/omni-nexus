"""Verify immutable Swarm image legal metadata and exact upstream file bytes offline."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

image, revision = sys.argv[1:]
assert re.fullmatch(r'excarplex/evo-nexus-(dashboard|runtime)@sha256:[a-f0-9]{64}', image)
assert re.fullmatch(r'[a-f0-9]{40}', revision)
labels = json.loads(subprocess.check_output([
    'docker', 'image', 'inspect', '--format', '{{json .Config.Labels}}', image
], text=True))
assert labels['org.opencontainers.image.revision'] == revision
assert labels['org.opencontainers.image.licenses'] == 'LicenseRef-EvoNexus'
names = ['LICENSE', 'NOTICE', 'NOTICE.md', 'TRADEMARKS.md']
root = Path(__file__).resolve().parents[2]
expected = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}
code = ('import hashlib,json,pathlib;names=' + repr(names) +
        ';print(json.dumps({n:hashlib.sha256((pathlib.Path("/workspace")/n).read_bytes()).hexdigest() for n in names}))')
actual = json.loads(subprocess.check_output([
    'docker', 'run', '--rm', '--network', 'none', '--cpus', '1', '--memory', '512m',
    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only',
    '--entrypoint', '/workspace/.venv/bin/python', image, '-c', code
], text=True))
assert actual == expected, 'Legal files differ from reviewed source'
print(json.dumps({'image': image, 'revision': revision, 'license_label': labels['org.opencontainers.image.licenses'],
                  'legal_file_hashes': actual, 'external_network': False}))
