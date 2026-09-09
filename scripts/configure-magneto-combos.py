#!/usr/bin/env python3
"""Align the configured gateway with existing named combos; preserve secrets."""
import json,shutil
from datetime import datetime,timezone
from pathlib import Path
p=Path('/workspace/config/providers.json')
cfg=json.loads(p.read_text());provider=cfg['providers']['omnirouter']
backup=p.with_name('providers.before-combos-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
shutil.copy2(p,backup);backup.chmod(0o600)
cfg['active_provider']='omnirouter'
cfg['telegram_follow_dashboard']=True
cfg.pop('telegram_provider',None)
provider['default_model']='Britto-Core'
provider['cli_command']='opencode'
provider['name']='OpenCode (via OmniRoute)'
provider['fallback_providers']=[]
provider['model_chain']=['Britto-Core','Britto-Coding','Britto-Heavy','Britto-Fast']
provider['default_base_url']='http://evonexus_omniroute:20128/v1'
provider.setdefault('env_vars',{})['OPENAI_BASE_URL']=provider['default_base_url']
provider['env_vars']['OPENAI_MODEL']='Britto-Core'
p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
print('OmniRoute canonical service name and four existing named combos configured')
