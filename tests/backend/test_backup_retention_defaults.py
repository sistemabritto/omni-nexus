import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('backup_under_test',Path(__file__).resolve().parents[2]/'backup.py')
backup=importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)

def test_unconfigured_backup_retains_three(tmp_path,monkeypatch):
    monkeypatch.setattr(backup,'BACKUPS_DIR',tmp_path)
    monkeypatch.delenv('BACKUP_RETAIN_LOCAL',raising=False)
    monkeypatch.delenv('BACKUP_RETAIN_S3',raising=False)
    for day in range(1,6): (tmp_path/f'evonexus-backup-2026090{day}-120000.zip').touch()
    unrelated=tmp_path/'manual-recovery.zip'
    unrelated.touch()
    backup.cleanup_old_backups()
    assert len(list(tmp_path.glob('evonexus-backup-*.zip')))==3
    assert unrelated.exists()
    assert not (tmp_path/'evonexus-backup-20260901-120000.zip').exists()
