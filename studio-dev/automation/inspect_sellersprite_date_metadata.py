import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
os.environ['JUNFEI_ACCOUNT_DATA']=str(Path.home()/'AmazonListingWorkbenchData')
sys.path.insert(0,str(ROOT/'listing-workbench'))
import sellersprite
c=sellersprite.Client().connect()
t=c.tools['asin_detail']
out=ROOT/'automation/data/sellersprite-date-metadata-20261102.json'
with out.open('x',encoding='utf-8') as f: json.dump(t,f,ensure_ascii=False,indent=2)
print(json.dumps(t,ensure_ascii=False))
