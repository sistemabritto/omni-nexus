"""Consolidate retired roles with verified copies and a reversible local journal.

Default is read-only. --apply is used by reviewed images after the existing seed
step. No historical conversation, completed ticket or execution log is deleted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from datetime import datetime, timezone


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_verified(source,destination):
    if source.is_symlink() or any(p.is_symlink() for p in (destination,*destination.parents)):
        raise RuntimeError('unsafe_copy_symlink')
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists() and digest(source)!=digest(destination):
        destination=destination.with_name(destination.stem+'-'+digest(source)[:12]+destination.suffix)
    if not destination.exists():shutil.copy2(source,destination)
    if digest(source)!=digest(destination):raise RuntimeError('copy_verification_failed')
    return destination


def migrate(root,apply=False):
    root=Path(root).resolve();mapping=json.loads(Path(__file__).with_name('squad-retirements.json').read_text())['agents']
    agents=root/'.claude/agents';memory=root/'.claude/agent-memory';library=root/'.claude/skills/squad-role-library/references'
    if any(p.is_symlink() for p in (agents,memory,library,*library.parents)):
        raise RuntimeError('unsafe_migration_symlink')
    sources=[name for name in mapping if (agents/(name+'.md')).is_file()]
    memories=[name for name in mapping if (memory/name).is_dir()]
    database=root/'dashboard/data/evonexus.db';ticket_moves=[]
    if database.is_file():
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as conn:
            columns={x[1] for x in conn.execute('PRAGMA table_info(tickets)')}
            if {'id','assignee_agent','status','locked_at'}<=columns:
                for old,new in mapping.items():
                    for (identifier,) in conn.execute("SELECT id FROM tickets WHERE assignee_agent=? AND status NOT IN ('resolved','closed','archived') AND locked_at IS NULL",(old,)):
                        ticket_moves.append((identifier,old,new))
    report={'version':2,'retiredDefinitions':sources,'memoryOwners':memories,'openTickets':len(ticket_moves),'applied':False}
    if not apply or not (sources or memories or ticket_moves):return report
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');backup=root/'backups/squad-roster-v2'/stamp;backup.mkdir(parents=True,mode=0o700)
    # Verify every source and copy before removing a single catalog definition.
    for old in sources:
        source=agents/(old+'.md')
        if source.is_symlink():raise RuntimeError('retired_source_is_symlink')
        copy_verified(source,backup/'definitions'/source.name)
        reference=library/source.name
        if reference.is_symlink():raise RuntimeError('unsafe_playbook_symlink')
        if reference.is_file() and digest(reference)!=digest(source):copy_verified(reference,backup/'previous-playbooks'/source.name)
        reference.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,reference)
        if digest(source)!=digest(reference):raise RuntimeError('playbook_verification_failed')
    for old in memories:
        source=memory/old
        for file in source.rglob('*'):
            if file.is_symlink():raise RuntimeError('retired_memory_contains_symlink')
            if file.is_file():copy_verified(file,memory/mapping[old]/'imported-roles'/old/file.relative_to(source))
    applied_moves=[]
    if ticket_moves:
        with sqlite3.connect(database) as conn, sqlite3.connect(backup/'evonexus-before.db') as out:
            conn.backup(out)
            if out.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise RuntimeError('database_backup_invalid')
            for identifier,old,new in ticket_moves:
                cursor=conn.execute("UPDATE tickets SET assignee_agent=? WHERE id=? AND assignee_agent=? AND locked_at IS NULL AND status NOT IN ('resolved','closed','archived')",(new,identifier,old))
                if cursor.rowcount:applied_moves.append((identifier,old,new))
    report.update(backup=str(backup),ticketMoves=applied_moves,phase='verified_before_removal')
    (backup/'journal.json').write_text(json.dumps(report,indent=2)+'\n')
    for old in sources:(agents/(old+'.md')).unlink()
    for old in memories:
        destination=backup/'original-memory'/old;destination.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(memory/old),str(destination))
    report.update(applied=True,backup=str(backup),ticketMoves=applied_moves,phase='complete')
    (backup/'journal.json').write_text(json.dumps(report,indent=2)+'\n')
    marker=root/'.claude/squad-roster-v2.json';marker.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='/workspace');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    print(json.dumps(migrate(args.root,args.apply)))
