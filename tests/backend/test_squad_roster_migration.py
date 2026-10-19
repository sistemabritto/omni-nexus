import importlib.util
import json
import sqlite3
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('migrate_roster',ROOT/'scripts/migrate_squad_roster.py')
migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)


def test_verified_migration_preserves_playbooks_memory_and_finished_or_locked_tickets(tmp_path):
    agents=tmp_path/'.claude/agents';agents.mkdir(parents=True)
    original=b'---\nname: goal-planner\n---\nSpecialized planner role\n'
    (agents/'goal-planner.md').write_bytes(original)
    mem=tmp_path/'.claude/agent-memory/goal-planner';mem.mkdir(parents=True);(mem/'useful.md').write_text('Owned memory')
    database=tmp_path/'dashboard/data/evonexus.db';database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE tickets(id TEXT PRIMARY KEY,assignee_agent TEXT,status TEXT,locked_at TEXT)')
        c.executemany('INSERT INTO tickets VALUES(?,?,?,?)',[(str(i),'goal-planner',s,l) for i,s,l in [(1,'open',None),(2,'resolved',None),(3,'open','locked')]])
    assert not migration.migrate(tmp_path)['applied'];assert (agents/'goal-planner.md').exists()
    result=migration.migrate(tmp_path,True);assert result['applied'];assert not (agents/'goal-planner.md').exists()
    assert (tmp_path/'.claude/skills/squad-role-library/references/goal-planner.md').read_bytes()==original
    assert (tmp_path/'.claude/agent-memory/atlas-project/imported-roles/goal-planner/useful.md').read_text()=='Owned memory'
    assert (Path(result['backup'])/'original-memory/goal-planner/useful.md').read_text()=='Owned memory'
    assert (Path(result['backup'])/'definitions/goal-planner.md').read_bytes()==original
    with sqlite3.connect(database) as c:
        assert c.execute('SELECT assignee_agent FROM tickets ORDER BY id').fetchall()==[('atlas-project',),('goal-planner',),('goal-planner',)]
    assert not migration.migrate(tmp_path,True)['applied']


def test_symlink_aborts_before_removing_definition(tmp_path):
    agents=tmp_path/'.claude/agents';agents.mkdir(parents=True);(agents/'goal-planner.md').write_text('preserve')
    memory=tmp_path/'.claude/agent-memory/goal-planner';memory.mkdir(parents=True);(memory/'link').symlink_to('/etc/passwd')
    with pytest.raises(RuntimeError):migration.migrate(tmp_path,True)
    assert (agents/'goal-planner.md').read_text()=='preserve'


def test_runtime_alias_resolves_preserved_role_not_new_owner_personality(tmp_path):
    from agent_roster import agent_path
    manifest=tmp_path/'scripts/squad-retirements.json';manifest.parent.mkdir();manifest.write_text(json.dumps({'agents':{'goal-planner':'atlas-project'}}))
    reference=tmp_path/'.claude/skills/squad-role-library/references/goal-planner.md';reference.parent.mkdir(parents=True);reference.write_text('Original routine instructions')
    assert agent_path(tmp_path,'goal-planner')==reference
    with pytest.raises(ValueError):agent_path(tmp_path,'../../etc/passwd')


def test_adw_embeds_retired_playbook_without_missing_agent_cli_flag(monkeypatch):
    from ADWs import runner
    commands=[]
    monkeypatch.setattr(runner.subprocess,'Popen',lambda argv,**kw:commands.append(argv))
    runner._spawn_cli('claude','Routine fixture','goal-planner',{},2)
    assert '--agent' not in commands[0]
    assert runner._agent_prompt('goal-planner') in commands[0][-1]
