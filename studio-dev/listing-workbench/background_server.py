"""Windowless server entry point; capture startup errors in the normal data logs."""
import os
from pathlib import Path
import runpy
import sys
import traceback

root = Path(__file__).resolve().parent
os.chdir(root)
logs = Path(os.environ.get('JUNFEI_ACCOUNT_DATA', str(root / 'data')))
logs.mkdir(parents=True, exist_ok=True)
sys.stdout = (logs / 'server.stdout.log').open('a', encoding='utf-8', buffering=1)
sys.stderr = (logs / 'server.stderr.log').open('a', encoding='utf-8', buffering=1)
try:
    runpy.run_path(str(root / 'server.py'), run_name='__main__')
except BaseException:
    traceback.print_exc()
    raise
