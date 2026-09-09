#!/usr/bin/env python3
"""Remove credentials from a repository provider config, preserving a private copy.

Does not touch a production volume or revoke/rotate credentials. Repository
history must be audited separately when credentials were already committed.
"""
import argparse,json,os,shutil,tempfile
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('path',type=Path);args=parser.parse_args()
    data=json.loads(args.path.read_text());changed=0
    for provider in data.get('providers',{}).values():
        for key,value in provider.get('env_vars',{}).items():
            if any(word in key for word in ('API_KEY','SECRET','TOKEN')) and value and value!='REDACTED':
                provider['env_vars'][key]='REDACTED';changed+=1
    if not changed:print('No non-empty provider credentials to sanitize');return
    backup=Path(tempfile.mkdtemp(prefix='omni-provider-private-'))/'providers.json'
    shutil.copy2(args.path,backup);backup.chmod(0o600)
    args.path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(f'Sanitized {changed} fields; private backup: {backup}')
if __name__=='__main__':main()
