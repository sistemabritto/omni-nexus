#!/usr/bin/env python3
"""Run inside Hermes to align existing profiles; never print credentials."""
import json,shutil
from datetime import datetime,timezone
from pathlib import Path
import yaml
from dotenv import dotenv_values

def main():
    root=Path('/opt/data');stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=root/'backups'/('routing-'+stamp);backup.mkdir(parents=True,mode=0o700)
    for path in [root/'config.yaml',*sorted((root/'profiles').glob('*/config.yaml'))]:
        cfg=yaml.safe_load(path.read_text());profile=path.parent.name
        shutil.copy2(path,backup/(profile+'.yaml'))
        candidates=[x for x in cfg.get('custom_providers',[]) if x.get('name')=='omniroute']
        if not candidates:raise RuntimeError('Missing configured omniroute provider: '+profile)
        provider=candidates[0];provider['base_url']='http://evonexus_omniroute:20128/v1'
        key=provider.get('api_key') or cfg.get('model',{}).get('api_key') or dotenv_values(path.parent/'.env').get('OPENAI_API_KEY')
        if not key:raise RuntimeError('Missing existing credential: '+profile)
        cfg['model'].update({'provider':'custom:omniroute','default':'Britto-Core',
                             'base_url':provider['base_url']})
        cfg['fallback_model']=[{'model':m,'provider':'custom:omniroute'} for m in ['Britto-Heavy','Britto-Fast']]
        cfg.setdefault('auxiliary',{}).setdefault('vision',{}).update({
            'provider':'custom:omniroute','model':'Britto-Core','base_url':provider['base_url'],'api_key':key,'timeout':180})
        cfg.setdefault('stt',{}).update({'enabled':True,'provider':'openai'})
        cfg['stt'].setdefault('openai',{}).update({'model':'groq/whisper-large-v3-turbo',
            'base_url':provider['base_url'],'api_key':key})
        # Operator explicitly authorized unattended tool execution; preserve
        # allowlists and any explicit deny rules rather than opening the bot publicly.
        cfg.setdefault('approvals',{})['mode']='off'
        path.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False));path.chmod(0o600)
        print(json.dumps({'profile':profile,'model':'Britto-Core','vision':'Britto-Core',
                          'stt':'omniroute/groq','approvals':'off'}))
if __name__=='__main__':main()
