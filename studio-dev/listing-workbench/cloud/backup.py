"""Create a consistent, root-only archive of the cloud workspace and its key."""
from contextlib import ExitStack, closing
from pathlib import Path
import datetime
import os
import shutil
import sqlite3
import tarfile
import tempfile


IGNORED = shutil.ignore_patterns('*.sqlite3', '*-wal', '*-shm', '*-journal', '*.log', 'runtime-ready.json')


class WorkspaceChanged(Exception):
    pass


def inventory(data):
    files, databases = {}, {}
    for folder, _, names in os.walk(data):
        ignored = IGNORED(folder, names)
        for name in names:
            path = Path(folder) / name
            if path.suffix == '.sqlite3':
                stat = path.stat()
                databases[path] = (stat.st_dev, stat.st_ino)
            elif name not in ignored:
                stat = path.stat()
                files[path] = (stat.st_size, stat.st_mtime_ns, stat.st_ino)
    return files, databases


def snapshot(data, staged, key):
    with ExitStack() as connections:
        files, databases = inventory(data)
        opened = {
            file: connections.enter_context(closing(sqlite3.connect(file.as_uri() + '?mode=ro', uri=True, timeout=10)))
            for file in sorted(databases)
        }
        def versions():
            return {file: db.execute('PRAGMA data_version').fetchone()[0] for file, db in opened.items()}

        baseline = versions()
        shutil.copytree(data, staged / 'data', ignore=IGNORED)
        shutil.copy2(key, staged / 'master.key')
        for file, source in opened.items():
            target = staged / 'data' / file.relative_to(data)
            target.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(target)) as destination:
                source.backup(destination)
        if inventory(data) != (files, databases) or versions() != baseline or key.read_bytes() != (staged / 'master.key').read_bytes():
            raise WorkspaceChanged('Workspace or publication receipts changed during backup')


def create_backup(root, data, key):
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    for attempt in range(3):
        with tempfile.TemporaryDirectory(dir=root) as folder:
            staged = Path(folder) / 'snapshot'
            try:
                snapshot(data, staged, key)
            except (WorkspaceChanged, FileNotFoundError) as error:
                if attempt == 2:
                    raise RuntimeError('Could not capture a stable workspace') from error
                continue
            temporary = Path(folder) / 'backup.tar.gz'
            with tarfile.open(temporary, 'w:gz') as archive:
                archive.add(staged / 'data', arcname='data')
                archive.add(staged / 'master.key', arcname='master.key')
            os.chmod(temporary, 0o600)
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            name = root / f'junfei-{timestamp}.tar.gz'
            temporary.replace(name)
            break
    for old in sorted(root.glob('junfei-*.tar.gz'))[:-7]:
        old.unlink()
    return name


if __name__ == '__main__':
    name = create_backup(Path('/opt/junfei/backups'), Path('/opt/junfei/workbench/data'), Path('/etc/junfei/master.key'))
    print('Backup completed:', name.name)
