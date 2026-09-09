#!/usr/bin/env python3
"""Create one consistent live SQLite recovery file, including WAL contents."""
import sqlite3,sys
from pathlib import Path
source,target=map(Path,sys.argv[1:])
assert source.is_file() and not target.exists()
with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
    assert dst.execute('PRAGMA quick_check').fetchone()[0]=='ok'
print('SQLite snapshot verified:',source.name,flush=True)
