"""Read-only SellerSprite query with explicit date/identity projection."""
import os,sys,json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent.parent
os.environ['JUNFEI_ACCOUNT_DATA']=str(Path.home()/'AmazonListingWorkbenchData')
sys.path.insert(0,str(ROOT/'listing-workbench'))
import sellersprite
request={'marketplace':'US','includeSellers':'qigan//','keyword':'Kitchen Chairs','matchType':1,'page':1,'size':20,'order':{'field':'available_date','desc':True},'returnFields':'asin,title,availableDate,sellerId,sellerName,fulfillment'}
out=ROOT/'automation/data/qigan-product-dates-20261102.json'
with out.open('x',encoding='utf-8') as f:json.dump({'status':'request_unknown','request':request},f)
c=sellersprite.Client().connect()
r=c.call('product_research',request)
allowed={'asin','title','availableDate','sellerId','sellerName','fulfillment','items','list','records','data','total','page','size'}
def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k in allowed}
 if isinstance(v,list):return [clean(x) for x in v]
 return v
result={'status':'response_received','request':request,'checkedAt':datetime.now(timezone.utc).isoformat(),'dateBasis':'sellersprite_product_listing','data':clean(r),'qualification':'unreviewed'}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
