from pathlib import Path
import shutil

block_cipher = None
publisher = Path('junfei-publisher')
node = shutil.which('node')
project_link = Path('build/ego-project-link/project-root.txt')
project_link.parent.mkdir(parents=True, exist_ok=True)
project_link.write_text(str(Path('.').resolve()), encoding='utf-8')
if not node:
    raise RuntimeError('Building JunfeiDraftAgent requires the Node.js runtime')

a = Analysis(
    ['junfei-publisher/app.py'],
    pathex=['junfei-publisher'],
    binaries=[],
    datas=[
        (str(publisher / name), '.') for name in (
            'existing-draft.mjs', 'listing.mjs', 'brain-worker.mjs',
            'brain-url-policy.mjs', 'brain-session-lifecycle.mjs',
            'brain-page-tracker.mjs', 'recipe.json',
            'brain-edge-profile.mjs', 'brain-page-metadata.mjs', 'brain-image-paste.mjs',
            'ego-existing-draft.mjs',
        )
    ] + [
        (str(project_link), '.'),
        (str(publisher / 'node_modules'), 'node_modules'),
        (node, '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='JunfeiDraftAgent',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[],
    name='JunfeiDraftAgent',
)
