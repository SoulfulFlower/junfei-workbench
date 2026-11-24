"""Read matched-other-seller ASIN only, after visible structure/spec comparison."""
import os,sys,json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent.parent
os.environ['JUNFEI_ACCOUNT_DATA']=str(Path.home()/'AmazonListingWorkbenchData');sys.path.insert(0,str(ROOT/'listing-workbench'))
import sellersprite
args={'marketplace':'US','asin':'B0GWXSFRV8','returnFields':'asin,title,bsrRank,bsrLabel,sellerId,sellerName'}
p=ROOT/'automation/data/pvc-matched-rank-20261102.json'
with p.open('x',encoding='utf-8') as f:json.dump({'status':'request_unknown','arguments':args},f)
r=sellersprite.Client().connect().call('asin_detail',args)
record={'status':'response_received','source':'SellerSprite MCP asin_detail','checkedAt':datetime.now(timezone.utc).isoformat(),'arguments':args,'matchEvidence':'automation/data/pvc-comparison-detail-20261102.json','data':{k:r.get(k) for k in ('asin','title','bsrRank','bsrLabel','sellerId','sellerName')}}
p.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record,ensure_ascii=False))
