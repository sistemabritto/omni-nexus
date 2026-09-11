"""Run on VPS: install only the reviewed skill files, preserving prior versions."""
from pathlib import Path
from datetime import datetime, timezone
import shutil

FILES=['social-editorial-strategy/SKILL.md',
 'social-editorial-strategy/references/gambito-de-valor-v4.md',
 'social-reels-scripts/references/coproducao-magneto.md',
 'social-reels-scripts/references/matriz-temas-sistemabritto.md']
if __name__=='__main__':
    src=Path('/tmp/gambito-v4/.claude/skills')
    root=Path('/var/lib/docker/volumes/evonexus_evonexus_claude_workspace/_data/skills')
    backup=Path('/var/backups')/datetime.now(timezone.utc).strftime('gambito-skills-%Y%m%dT%H%M%S')
    for name in FILES:
        dest=root/name
        if dest.exists():
            saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src/name,dest)
    inventory=Path('/var/lib/docker/volumes/evonexus_evonexus_workspace/_data/social/gambito-v4-inventory.json')
    if inventory.exists():
        backup.mkdir(parents=True,exist_ok=True);shutil.copy2(inventory,backup/inventory.name)
    shutil.copy2('/tmp/gambito-v4/gambito-v4-inventory.json',inventory)
    print('Installed four skill files and draft inventory; backup:',backup)
