"""Import from the actual Docker COPY allowlist, not the repository PYTHONPATH."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def test_recording_render_imports_from_worker_packaged_modules(tmp_path):
    root=Path(__file__).resolve().parents[2]
    text=(root/'Dockerfile.media-worker').read_text()
    prefix='COPY dashboard/backend/sdk_client.py'
    block=text.split(prefix,1)[1].split('/workspace/dashboard/backend/',1)[0]
    sources=['dashboard/backend/sdk_client.py']+re.findall(r'dashboard/backend/[\w.]+',block)
    target=tmp_path/'packaged';target.mkdir()
    for name in sources:shutil.copyfile(root/name,target/Path(name).name)
    code="import sys;sys.path.insert(0,sys.argv[1]);import recording_render;assert recording_render.video_trim({'start_seconds':0,'end_seconds':1})=={'start_seconds':0.0,'end_seconds':1.0}"
    result=subprocess.run([sys.executable,'-I','-c',code,str(target)],cwd=tmp_path,
        env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')},
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
