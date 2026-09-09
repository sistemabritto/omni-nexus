#!/usr/bin/env python3
"""Bound known backup archives. Dry-run by default; never prune live data."""
import argparse
import json
import re
import shutil
import time
import zipfile
from pathlib import Path

ZIP_ROOT = Path('/var/lib/docker/volumes/evonexus_evonexus_backups/_data')
HERMES_ROOT = Path('/mnt/docker-volumes/hermes-unified')

def candidates(root, pattern, keep=3):
    if not root.is_dir() or root.is_symlink():
        return []
    items = sorted((p for p in root.iterdir() if not p.is_symlink() and re.fullmatch(pattern,p.name)),
                   key=lambda p:p.name, reverse=True)
    return [p for p in items[keep:] if time.time()-p.stat().st_mtime > 86400]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    zips=sorted(ZIP_ROOT.glob('evonexus-backup-*.zip'),reverse=True)
    # Refuse to remove older recovery points if the kept archives are unreadable.
    if zips:
        for p in zips[:3]:
            with zipfile.ZipFile(p) as archive:
                assert 'manifest.json' in archive.namelist(), p
                json.loads(archive.read('manifest.json'))
    targets=candidates(ZIP_ROOT,r'evonexus-backup-\d{8}-\d{6}\.zip')
    roots=[HERMES_ROOT/'backups', *sorted((HERMES_ROOT/'profiles').glob('*/backups'))]
    for root in roots:
        # Legacy scheduled DB dumps and their metadata, not user checkpoints.
        old=candidates(root,r'sb-backup-\d{8}_\d{6}-dbs')
        targets.extend(old)
        for p in old:
            info=p.with_name(p.name.removesuffix('-dbs')+'-info.txt')
            if info.is_file() and not info.is_symlink(): targets.append(info)
        targets.extend(candidates(root,r'.+\.tar\.gz'))
    total=0
    for p in targets:
        size=p.stat().st_size if p.is_file() else sum(x.stat().st_size for x in p.rglob('*') if x.is_file() and not x.is_symlink())
        print(('DELETE' if args.apply else 'WOULD_DELETE'),size,p,flush=True)
        total+=size
        if args.apply:
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()
    print(json.dumps({'applied':args.apply,'count':len(targets),'bytes':total}))

if __name__=='__main__': main()
