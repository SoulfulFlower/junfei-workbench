"""Storage boundary for one account runtime. Auth stays central in accounts.py."""
import os
from pathlib import Path
APP=Path(__file__).resolve().parent
DATA=Path(os.environ.get('JUNFEI_ACCOUNT_DATA',str(APP/'data'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
WORKER_USER=int(os.environ.get('JUNFEI_WORKER_USER','0'))
INTERNAL_TOKEN=os.environ.get('JUNFEI_INTERNAL_TOKEN','')
LIBRARY_ROOT=Path(os.environ['JUNFEI_LIBRARY_ROOT']).resolve() if WORKER_USER and INTERNAL_TOKEN and os.environ.get('JUNFEI_LIBRARY_ROOT') else DATA
