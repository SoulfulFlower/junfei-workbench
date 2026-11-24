"""Observe an exact original SKU family using Seller Central's visible SKU filter.

Only native CLI page visit/content/exec are used. No saves, API calls, clicks,
uploads or credentials are read. Missing/ambiguous rows never count as healthy.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode

from ziniao_plugin import native_cli, run
from ziniao_page_observe import observe

MARKETS={'US':('https://sellercentral.amazon.com','美国'),
         'UK':('https://sellercentral.amazon.co.uk','英国')}

SCRIPT=r'''(() => {
 const cfg=__CONFIG__,norm=s=>String(s||'').trim().replace(/\s+/g,' ');
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
 const headers=[...document.querySelectorAll('.dropdown-account-switcher-header')].filter(visible);
 if(location.origin!==cfg.origin||location.pathname!=='/amazonsell/manage-products')return JSON.stringify({error:'market_or_page_changed'});
 if(!headers.length){if(document.querySelector('input[type="password"]'))return JSON.stringify({error:'authentication_required'});return JSON.stringify({pending:'market_header_loading',loading:true,rows:[],observedAt:new Date().toISOString()});}
 if(headers.length!==1||norm(headers[0].innerText)!==cfg.label)return JSON.stringify({error:'market_identity_changed'});
 const observedFilter=(new URL(location.href).searchParams.get('searchSku')||'').split(',').map(s=>s.trim()).filter(Boolean);
 if(observedFilter.length!==cfg.skus.length||new Set(observedFilter).size!==cfg.skus.length||observedFilter.some(s=>!cfg.skus.includes(s)))return JSON.stringify({error:'exact_SKU_filter_changed',observedFilterCount:observedFilter.length,requestedFilterCount:cfg.skus.length,overlapCount:observedFilter.filter(s=>cfg.skus.includes(s)).length});
 const wanted=new Set(cfg.skus),rows=[];
 const headerRows=[...document.querySelectorAll('thead tr')].map(r=>[...r.querySelectorAll('th')].map(c=>norm(c.innerText)));
 const columns=headerRows.find(r=>r.some(c=>c.includes('商品状态')))||[];
 const statusIndex=columns.findIndex(c=>c.includes('商品状态'));
 for(const row of document.querySelectorAll('tbody tr')){
  const links=[...row.querySelectorAll('a[href]')].map(a=>{try{const u=new URL(a.getAttribute('href'),location.href);return{u,text:norm(a.innerText)};}catch{return null;}}).filter(Boolean);
  const identities=links.filter(a=>a.u.origin===cfg.origin&&a.u.pathname==='/skucentral'&&wanted.has(a.u.searchParams.get('mSku')));
  const skus=[...new Set(identities.map(a=>a.u.searchParams.get('mSku')))];
  if(!skus.length)continue;
  const cells=[...row.querySelectorAll('td')].map(c=>norm(c.innerText));
  const asinLinks=links.filter(a=>a.u.hostname==='www.amazon.com'||a.u.hostname==='www.amazon.co.uk').map(a=>a.u.pathname.match(/\/dp\/(B[A-Z0-9]{9})(?:\/|$)/)?.[1]).filter(Boolean);
  rows.push({skus,sku:skus.length===1?skus[0]:null,asins:[...new Set(asinLinks)],rowText:norm(row.innerText),cells,
    statusCellText:statusIndex>=0&&cells.length===columns.length?cells[statusIndex]:null,
    controls:[...row.querySelectorAll('button,a[role="button"]')].map(e=>({text:norm(e.innerText),aria:e.getAttribute('aria-label')}))});
 }
 const body=norm(document.body.innerText),loading=body.includes('正在加载商品')||body.includes('Loading products');
 return JSON.stringify({url:location.href,label:cfg.label,columns,headerRows,statusIndex,rows,loading,observedAt:new Date().toISOString(),bodyText:body.slice(-3000)});
})()'''


def unwrap(value):
    if value.get('ok') is not True:
        raise ValueError('原生库存读取失败；不重试写操作')
    while isinstance(value.get('data'),dict):
        value=value['data']
    if value.get('exceptionDetails'):
        raise ValueError('原生库存只读脚本执行失败')
    return json.loads(value.get('result',''))


def summarize_coverage(skus,rows,loading=False):
    observed=[row['sku'] for row in rows if row['sku']]
    counts=Counter(observed)
    missing=sorted(set(skus)-set(observed))
    duplicates=sorted(s for s,count in counts.items() if count!=1)
    ambiguous=sum(len(row['skus'])!=1 for row in rows)
    statuses=Counter(row['statusCellText'] or 'UNRESOLVED_STATUS_CELL' for row in rows)
    return {'requestedCount':len(skus),'observedCount':len(observed),'missingSkus':missing,
            'duplicateSkus':duplicates,'ambiguousRows':ambiguous,
            'observationPending':bool(loading),
            'coverageVerified':not loading and not missing and not duplicates and not ambiguous and len(observed)==len(skus),
            'statusCellCounts':dict(statuses)}


def audit(args):
    source=Path(args.expected).resolve()
    packet=json.loads(source.read_text(encoding='utf-8-sig'))
    families=packet.get('families')
    if not isinstance(families,list):
        raise ValueError('缺少独立核对的families原SKU清单')
    matches=[v for v in families if v.get('parentSku')==args.parent_sku]
    if packet.get('accountId')!=2 or len(matches)!=1:
        raise ValueError('原账号或原父SKU不符')
    family=matches[0]
    children=family.get('children',[])
    skus=[v.get('sku') for v in children]
    if (not skus or len(skus)>100 or len(set(skus))!=len(skus)
            or any(not isinstance(s,str) or not s.startswith(args.parent_sku+'-')
                   or not re.fullmatch(r'[A-Za-z0-9_-]+(?: [A-Za-z0-9_-]+)*',s) for s in skus)):
        raise ValueError('原子SKU集合缺失、重复、超范围或不支持')
    origin,country=MARKETS[args.market]
    # Before any navigation, verify this exact native target's visible market.
    observe(args.store_id,args.target_id,origin,args.seller,country)
    url=origin+'/amazonsell/manage-products?'+urlencode({'view':'all','searchSku':','.join(skus),'pageSize':'100','pageIndex':'0'})
    cli=native_cli()
    if not args.observe_current:
        run(cli,'page','visit','--store-id',args.store_id,'--target-id',args.target_id,
            '--url',url,'--wait-until','domcontentloaded','--timeout','30000')
    config={'origin':origin,'label':args.seller+' '+country,'skus':skus}
    script=SCRIPT.replace('__CONFIG__',json.dumps(config,ensure_ascii=False))
    result=None
    for attempt in range(24):
        result=unwrap(run(cli,'page','exec','--store-id',args.store_id,'--target-id',args.target_id,'--script',script))
        if result.get('error'):
            raise ValueError(result['error'])
        seen={s for row in result['rows'] for s in row['skus']}
        if seen==set(skus) and not result.get('loading') and not result.get('pending'):
            break
        if attempt<23:
            time.sleep(0.5)
    return {'at':datetime.now(timezone.utc).isoformat(),'accountId':2,'storeId':args.store_id,
            'market':args.market,'seller':args.seller,'parentSku':args.parent_sku,
            'sourceExpectedFile':str(source),'sourceExpectedSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            **summarize_coverage(skus,result['rows'],bool(result.get('loading') or result.get('pending'))),'observation':result,
            'businessWrites':False,'uploaded':False,'saved':False,'republished':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store-id',required=True)
    parser.add_argument('--target-id',required=True)
    parser.add_argument('--seller',required=True)
    parser.add_argument('--market',choices=MARKETS,required=True)
    parser.add_argument('--expected',required=True)
    parser.add_argument('--parent-sku',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--observe-current',action='store_true',help='Only read the current exact filter; never navigate again')
    args=parser.parse_args()
    try:
        record=audit(args)
    except Exception as error:
        raise SystemExit(str(error)) from None
    output=Path(args.output).resolve()
    output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('parentSku','requestedCount','observedCount','missingSkus','duplicateSkus','ambiguousRows','observationPending','coverageVerified','statusCellCounts')},ensure_ascii=False))
    if record['observationPending']:
        raise SystemExit(2)
