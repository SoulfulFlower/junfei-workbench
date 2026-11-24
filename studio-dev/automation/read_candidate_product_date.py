"""One read-only date lookup; no sales-rank fields requested or retained."""
import os,sys,json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent.parent
os.environ['JUNFEI_ACCOUNT_DATA']=str(Path.home()/'AmazonListingWorkbenchData')
sys.path.insert(0,str(ROOT/'listing-workbench'))
import sellersprite
out=ROOT/'automation/data/B0HNTGP9R4-product-date-20261102.json'
with out.open('x',encoding='utf-8') as f:
 json.dump({'status':'request_unknown','asin':'B0HNTGP9R4','returnFields':'asin,availableDate,available_date,listingDate'},f)
c=sellersprite.Client().connect()
result=c.call('asin_detail',{'marketplace':'US','asin':'B0HNTGP9R4','returnFields':'asin,availableDate,available_date,listingDate'})
# The server field projection excludes rank. Keep only date/identity keys even
# if a future service ignores returnFields. Do not print the unfiltered response.
allowed={'asin','availableDate','available_date','listingDate','dateFirstAvailable'}
def project(value):
 if isinstance(value,dict):
  return {k:(project(v) if isinstance(v,(dict,list)) else v) for k,v in value.items() if k in allowed or k in ('data','result','content','text','type')}
 if isinstance(value,list): return [project(v) for v in value]
 return value
# Client usually returns decoded tool JSON; text blocks must parse before filtering.
def clean(value):
 if isinstance(value,dict):
  if 'text' in value and isinstance(value['text'],str):
   try: return clean(json.loads(value['text']))
   except (ValueError,TypeError): return {'unparsedTextOmitted':True}
  return {k:clean(v) for k,v in value.items() if k in allowed or k in ('data','result','content','type')}
 if isinstance(value,list):return [clean(v) for v in value]
 return value
record={'status':'response_received','checkedAt':datetime.now(timezone.utc).isoformat(),'asin':'B0HNTGP9R4','marketplace':'US','dateBasis':'sellersprite_product_listing','source':'SellerSprite MCP asin_detail','requestedFields':'asin,availableDate,available_date,listingDate','dateFields':clean(result),'qualification':'unreviewed'}
out.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
