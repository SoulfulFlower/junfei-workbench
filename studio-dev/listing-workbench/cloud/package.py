"""Create an upload archive without credentials, sessions, backups or local TLS."""
from pathlib import Path
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing

app = Path(__file__).resolve().parents[1]
output = app.parent/'cloud-deployment'
output.mkdir(exist_ok=True)
archive_path = output/'junfei-cloud.zip'
with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
    def add(file, name):
        archive.write(file, str(name).replace('\\', '/'))
    for file in app.iterdir():
        if file.is_file() and file.suffix in ('.py', '.js', '.cjs', '.html', '.css', '.txt', '.md', '.ps1'):
            if file.name.startswith(('live_', 'rebuild_', 'new_product_')):
                continue
            add(file, file.name)
    for directory in ('assets', 'extension', 'visual-ui', 'cloud'):
        for file in (app/directory).rglob('*'):
            if not file.is_file() or any(p in ('node_modules', '__pycache__') for p in file.relative_to(app/directory).parts):
                continue
            if file.name in ('debug_test.py', 'package.py'):
                continue
            add(file, file.relative_to(app))
    data = app/'data'
    for file in data.rglob('*'):
        if not file.is_file():
            continue
        relative = file.relative_to(data)
        if len(relative.parts) == 1:
            allowed = file.suffix == '.sqlite3' or file.name in ('model-preferences.json', 'listing-prompt-custom.txt')
        elif relative.parts[0] in ('uploads', 'studio-results'):
            allowed = file.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.image')
        elif relative.parts[0] == 'account-workspaces':
            allowed = file.suffix == '.sqlite3' or file.name in ('model-preferences.json', 'listing-prompt-custom.txt') or ('uploads' in relative.parts or 'studio-results' in relative.parts) and file.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.image')
        else:
            allowed = False
        if not allowed:
            continue
        if file.suffix == '.sqlite3':
            snapshot = Path(folder)/relative
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect('file:'+file.as_posix()+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
                if file.name == 'accounts.sqlite3':
                    target.execute('DELETE FROM tokens')
                    target.execute('DELETE FROM attempts')
                    target.commit()
            add(snapshot, Path('data')/relative)
        else:
            add(file, Path('data')/relative)
    archive.writestr('data/deployment.json', json.dumps({'enabled': False}))
with zipfile.ZipFile(archive_path) as archive:
    assert not any(name.endswith(('.dpapi', '.fernet', '.pem', '.key', '.log')) for name in archive.namelist())
    print('Files:', len(archive.namelist()))
print('Archive:', archive_path.name, 'MB:', round(archive_path.stat().st_size/1048576, 1))
