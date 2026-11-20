# Clean portable distribution. Invoke through packaging/build_portable.py.
import os
from pathlib import Path
import shutil

root = Path(SPECPATH).resolve()
stage = Path(os.environ['JUNFEI_PORTABLE_STAGE']).resolve()
if not (stage / 'portable-release.json').is_file():
    raise ValueError('Use packaging/build_portable.py to prepare a clean stage')
node = shutil.which('node')
if not node:
    raise ValueError('Node.js is required on the build computer')
app = root / 'listing-workbench'
datas = [(str(p), '.') for pattern in ('*.js', '*.css', '*prompt*.txt') for p in app.glob(pattern)]
datas += [(str(app / 'index.html'), '.'), (str(app / 'assets'), 'assets'),
          (str(app / 'extension'), 'extension'), (str(app / 'visual-ui/dist'), 'visual-ui/dist'),
          (str(app / 'LICENSE-AGPL-3.0.txt'), '.'), (str(app / 'SOURCE-NOTICE.md'), '.'),
          (str(app / 'CROSS-COMPUTER.md'), '.'), (str(stage / 'portable-release.json'), '.'),
          (str(stage / 'corresponding-source.zip'), '.'),
          (str(app / 'visual-ui/NOTICE.md'), 'visual-ui'),
          (str(stage / 'portable-runtime'), 'portable-runtime'), (node, '.')]
a = Analysis([str(app / 'desktop_launcher.py')], pathex=[str(app)], binaries=[], datas=datas,
             hiddenimports=['agent_library', 'portable_support', 'runpy', 'jsonschema', 'referencing'], hookspath=[],
             hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AmazonAgentPortable',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AmazonAgentPortable')
