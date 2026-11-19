from pathlib import Path
import shutil
# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['listing-workbench/desktop_launcher.py'],
    pathex=['listing-workbench'],
    binaries=[],
    datas=[(str(p), '.') for pattern in ('*.js', '*.css', '*prompt*.txt') for p in Path('listing-workbench').glob(pattern)] + [('listing-workbench/index.html', '.'), ('listing-workbench/assets', 'assets'), ('listing-workbench/extension', 'extension'), ('listing-workbench/visual-ui/dist', 'visual-ui/dist'), ('junfei-publisher/listing.mjs', 'junfei-publisher'), ('junfei-publisher/existing-draft.mjs', 'junfei-publisher'), ('junfei-publisher/node_modules', 'junfei-publisher/node_modules'), (shutil.which('node'), '.')],
    hiddenimports=['agent_library'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.datas += [('automation/config.json', str(Path('automation/config.json').resolve()), 'DATA')]
a.datas += [(str(Path('data/logistics')/p.name),str(p.resolve()),'DATA') for p in Path('listing-workbench/data/logistics').glob('*.json')]
project_link = Path('build/workbench-project-link/project-root.txt')
project_link.parent.mkdir(parents=True, exist_ok=True)
project_link.write_text(str(Path('.').resolve()), encoding='utf-8')
a.datas += [('project-root.txt', str(project_link.resolve()), 'DATA'),
            ('ego-existing-draft.mjs', str(Path('junfei-publisher/ego-existing-draft.mjs').resolve()), 'DATA')]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AmazonAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AmazonAgent',
)
