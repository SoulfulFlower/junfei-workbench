"""Root-only daily backups. SQLite online backup avoids inconsistent DB copies."""
from pathlib import Path
import datetime
import os
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing

root = Path('/opt/junfei/backups')
root.mkdir(mode=0o700, exist_ok=True)
os.chmod(root, 0o700)
data = Path('/opt/junfei/workbench/data')
with tempfile.TemporaryDirectory(dir=root) as folder:
    staged = Path(folder)/'data'
    shutil.copytree(data, staged, ignore=shutil.ignore_patterns('*.sqlite3', '*-wal', '*-shm', '*.log', 'runtime-ready.json'))
    for file in data.rglob('*.sqlite3'):
        target = staged/file.relative_to(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(file)) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
    name = root/('junfei-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.tar.gz')
    with tarfile.open(name, 'w:gz') as archive:
        archive.add(staged, arcname='data')
        archive.add('/etc/junfei/master.key', arcname='master.key')
for old in sorted(root.glob('junfei-*.tar.gz'))[:-7]:
    old.unlink()
print('Backup completed:', name.name)
