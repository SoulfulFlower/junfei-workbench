import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {ensureUkBrandExemption,assertUkExemptionContext,parseUkExemptionCheck,installUkExemptionGuard} from './ego-uk-exemption.mjs';

const origin='https://app.junfeikuajing.com/api/amazon/category/upc-exemption/';
const nativeScope={seller_id:'ACTUALSELLER',country_code:'GB',primary_category_name:'Fashion',product_type_name:'SHIRT',brand:'Kimeetol'};
const statusMap={waiting:'等待申请',applying:'申请中',timeout:'处理超时',unavailable:'不可销售',available:'允许销售',failed:'申请失败'};
function fixture(statuses=[null,'available']){
 const prepared={accountId:2,productId:'original-product',jobId:'original-job',sha256:'original-snapshot',marketplace:'UK',mode:'draft',store:'Target UK',goods:{brand:'KIMEETOL'},destination:{draftId:'200',countryCode:'GB',marketplaceId:'UKMARKET',schemaHash:'gb-schema'}};
 const meta={hash:'gb-schema',country_code:'GB',locale:'en_GB',product_type_name:'SHIRT',schema_content:{$defs:{marketplace_id:{default:'UKMARKET'}}}};
 const ui={url:'https://www.junfeikuajing.com/#/amazon/product/200?type=draft',store:'Target UK',brand:'KIMEETOL',status:'未检测到UPC豁免',nativeMarketId:'190836'};
 const record={draftId:'200',categoryChoice:{text:'Fashion Women Clothing Tops T-Shirts & Blouses T-Shirts'},sourceEvidence:{original:'keep'},saveIntent:{original:'keep'}},snapshots=[],calls={refresh:0,apply:0,wait:0,waitUi:0},waits=[];let clock=0;
 const observation=status=>({request:{method:'POST',url:origin+'check',payload:structuredClone(nativeScope),response:{httpStatus:200,body:{code:0,data:{status,status_map:statusMap}}}},ui:{...ui,status:status==='available'?'UPC豁免：允许销售':status===null?'未检测到UPC豁免':'UPC豁免：'+statusMap[status]}});
 const adapters={schemaObservation:meta,ui:async()=>({...ui}),refresh:async()=>{calls.refresh++;return observation(statuses.length>1?statuses.shift():statuses[0]);},
  apply:async()=>{calls.apply++;assert.ok(snapshots.at(-1).brandExemption.applyIntent);return{request:{method:'POST',url:origin+'apply',payload:structuredClone(nativeScope),response:{httpStatus:200,body:{code:0}}}};},
  timeoutMs:10000,now:()=>clock,wait:async ms=>{calls.wait++;waits.push(ms);clock+=ms;},waitUi:async()=>calls.waitUi++};
 return{prepared,meta,ui,record,snapshots,calls,statuses,observation,adapters,waits,get clock(){return clock;},persist:async()=>snapshots.push(structuredClone(record))};
}

test('fresh available UK check accepts canonical native brand and observed market without requiring configured marketId or applying',async()=>{
 const f=fixture(['available']);const result=await ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters);
 assert.equal(result.phase,'allowed');assert.equal(result.nativeMarketId,'190836');assert.equal(result.nativeScope.brand,'Kimeetol');assert.equal(f.prepared.goods.brand,'KIMEETOL');assert.equal(f.prepared.destination.marketId,undefined);
 assert.equal(f.calls.refresh,1);assert.equal(f.calls.apply,0);assert.equal(result.applyIntent,undefined);assert.deepEqual(f.record.sourceEvidence,{original:'keep'});assert.deepEqual(f.record.saveIntent,{original:'keep'});
});

test('missing exemption durably arms one exact original-draft application before applying and then refreshes real status',async()=>{
 const f=fixture();const result=await ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters);
 assert.equal(f.calls.apply,1);assert.equal(f.calls.refresh,2);assert.equal(result.applyIntent.identity.draftId,'200');assert.equal(result.applyIntent.nativeScope.seller_id,nativeScope.seller_id);assert.ok(result.requestAcceptedAt);assert.equal(result.phase,'allowed');
 f.statuses.splice(0,f.statuses.length,'available');await ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters);assert.equal(f.calls.apply,1);
});

test('lost application response remains unknown and never reapplies across repeated null checks and later allowed reconciliation',async()=>{
 const f=fixture([null]);f.adapters.apply=async()=>{f.calls.apply++;assert.ok(f.snapshots.at(-1).brandExemption.applyIntent);throw Error('response lost');};
 await assert.rejects(()=>ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters),/不重复申请/);const intent=structuredClone(f.record.brandExemption.applyIntent);assert.equal(f.calls.apply,1);assert.equal(f.record.brandExemption.requestAcceptedAt,undefined);
 await assert.rejects(()=>ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters),/不重复申请/);assert.equal(f.calls.apply,1);assert.deepEqual(f.record.brandExemption.applyIntent,intent);
 f.statuses.splice(0,1,'available');const result=await ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters);assert.equal(result.phase,'allowed');assert.equal(f.calls.apply,1);assert.equal(result.lastApplyError,'response lost');assert.deepEqual(result.applyIntent,intent);
});

test('pending or failed native states do not start a second application',async()=>{
 for(const status of ['waiting','applying','timeout','failed','unavailable']){const f=fixture([status]);await assert.rejects(()=>ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters));assert.equal(f.calls.apply,0);assert.equal(f.record.brandExemption.applyIntent,undefined);}
});

test('a known applying request polls only its frozen scope until available within the bounded read window',async()=>{
 const f=fixture([null,'applying','applying','available']);f.adapters.timeoutMs=180000;
 const result=await ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters);
 assert.equal(result.phase,'allowed');assert.equal(result.applicationState,'available');assert.equal(f.calls.apply,1);assert.equal(result.poll.attempts,3);assert.equal(result.poll.timedOut,false);assert.equal(result.poll.result,'available');
 assert.deepEqual(f.waits,[5000,5000]);assert.equal(f.clock,10000);assert.ok(f.snapshots.some(snapshot=>snapshot.brandExemption.phase==='pending'&&snapshot.brandExemption.applicationState==='applying'));
 for(const row of result.checks)assert.deepEqual(row.request.payload,nativeScope);
});

test('bounded applying timeout preserves acknowledgement and intent and a resumed poll never reapplies',async()=>{
 const f=fixture([null,'applying']);f.adapters.timeoutMs=12000;
 await assert.rejects(()=>ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters),error=>error.code==='ERP_UK_EXEMPTION_PENDING');
 const intent=structuredClone(f.record.brandExemption.applyIntent);assert.equal(f.record.brandExemption.phase,'pending');assert.equal(f.record.brandExemption.applicationState,'applying');assert.ok(f.record.brandExemption.requestAcceptedAt);assert.equal(f.record.brandExemption.poll.timedOut,true);assert.equal(f.record.brandExemption.poll.elapsedMs,12000);assert.ok(f.waits.every(ms=>ms<=5000));
 await assert.rejects(()=>ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters),error=>error.code==='ERP_UK_EXEMPTION_PENDING');
 assert.equal(f.calls.apply,1);assert.deepEqual(f.record.brandExemption.applyIntent,intent);assert.equal(f.record.brandExemption.pollHistory.length,1);
});

test('wrong UK brand store draft schema or actual market stops before even refreshing and changed native seller stops before apply',async()=>{
 for(const mutate of [f=>f.ui.brand='OTHER',f=>f.ui.store='Other Store',f=>f.ui.url=f.ui.url.replace('/200?','/201?'),f=>f.ui.nativeMarketId=null,f=>f.prepared.destination.marketId='191897',f=>f.meta.country_code='US',f=>f.meta.hash='different']){
  const f=fixture();mutate(f);await assert.rejects(()=>ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters));assert.equal(f.calls.refresh,0);assert.equal(f.calls.apply,0);
 }
 const f=fixture();f.record.brandExemption={identity:assertUkExemptionContext(f.prepared,f.meta,f.ui)};
 await assert.rejects(()=>ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters),/检查点/);assert.equal(f.calls.refresh,0);
 const g=fixture(['available']);await ensureUkBrandExemption({},g.prepared,g.record,g.persist,g.adapters);g.adapters.refresh=async()=>{const result=g.observation(null);result.request.payload.seller_id='OTHERSELLER';return result;};
 await assert.rejects(()=>ensureUkBrandExemption({},g.prepared,g.record,g.persist,g.adapters),/范围/);assert.equal(g.calls.apply,0);
 const changed=fixture();changed.adapters.refresh=async()=>{const result=changed.observation(null);result.ui.nativeMarketId='other-market';return result;};await assert.rejects(()=>ensureUkBrandExemption({},changed.prepared,changed.record,changed.persist,changed.adapters));assert.equal(changed.calls.apply,0);assert.equal(changed.record.brandExemption.applyIntent,undefined);
});

test('server available waits for UI rendering but never claims allowed from a stale or never-allowed UI',async()=>{
 const f=fixture(['available']);f.adapters.refresh=async()=>{const o=f.observation('available');o.ui.status='未检测到UPC豁免';return o;};f.adapters.waitUi=async()=>{f.calls.waitUi++;f.ui.status='UPC豁免：允许销售';};
 assert.equal((await ensureUkBrandExemption({},f.prepared,f.record,f.persist,f.adapters)).phase,'allowed');assert.equal(f.calls.waitUi,1);assert.equal(f.calls.apply,0);
 const g=fixture(['available']);g.adapters.refresh=async()=>{const o=g.observation('available');o.ui.status='未检测到UPC豁免';return o;};
 await assert.rejects(()=>ensureUkBrandExemption({},g.prepared,g.record,g.persist,g.adapters),/UI尚未确认/);assert.notEqual(g.record.brandExemption.phase,'allowed');assert.equal(g.calls.apply,0);
});

function guardFixture(mode='apply'){
 const f=fixture(),identity=assertUkExemptionContext(f.prepared,f.meta,f.ui),sent=[];
 class XHR{open(){}addEventListener(){}send(body){sent.push(JSON.parse(body));}}
 const context=vm.createContext({window:{fetch:async()=>{throw Error('fake network must not be called');}},XMLHttpRequest:XHR,URL,Date,location:{href:f.ui.url},plan:{token:'test-token',mode,identity,nativeScope,categoryText:f.record.categoryChoice.text}});
 vm.runInContext('('+installUkExemptionGuard.toString()+')(plan)',context);
 const send=(payload=nativeScope,endpoint=origin+(mode==='apply'?'apply':'check'),opened=true)=>{context.payload=payload;context.endpoint=endpoint;context.opened=opened;return vm.runInContext('(()=>{const xhr=new XMLHttpRequest();if(opened)xhr.open("POST",endpoint);xhr.send(JSON.stringify(payload));})()',context);};
 return{sent,context,send};
}

test('native guard accepts the observed five-key casefold check and one original application while blocking duplicate or foreign writes',()=>{
 const check=guardFixture('check');check.send();assert.equal(check.sent.length,1);assert.equal(check.sent[0].brand,'Kimeetol');
 const apply=guardFixture();apply.send();assert.equal(apply.sent.length,1);assert.throws(()=>apply.send());assert.equal(apply.sent.length,1);
 for(const [key,value]of Object.entries({seller_id:'OTHER',country_code:'US',primary_category_name:'Other',product_type_name:'COAT',brand:'Other'})){const f=guardFixture();assert.throws(()=>f.send({...nativeScope,[key]:value}));assert.equal(f.sent.length,0);}
 for(const endpoint of ['https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish','https://app.junfeikuajing.com/api/amazon/goods/publish/json-update','https://app.junfeikuajing.com/api/amazon/goods/draft/copy']){const f=guardFixture();assert.throws(()=>f.send(nativeScope,endpoint));assert.equal(f.sent.length,0);}
 const extra=guardFixture();assert.throws(()=>extra.send({...nativeScope,id:'other'}));assert.equal(extra.sent.length,0);
 const unknown=guardFixture();assert.throws(()=>unknown.send(nativeScope,origin+'apply',false));assert.equal(unknown.sent.length,0);
 const readOnly=guardFixture('check');assert.throws(()=>readOnly.send(nativeScope,origin+'apply'));assert.equal(readOnly.sent.length,0);
});

test('native guard rejects mutation through fetch and check parsing requires the true available status map',async()=>{
 const f=guardFixture();await assert.rejects(()=>vm.runInContext('window.fetch("https://app.junfeikuajing.com/api/amazon/category/upc-exemption/apply",{method:"POST"})',f.context));assert.equal(f.sent.length,0);
 const g=fixture(),identity=assertUkExemptionContext(g.prepared,g.meta,g.ui),o=g.observation('available');o.request.response.body.data.status_map={available:'Different'};assert.throws(()=>parseUkExemptionCheck(o,identity));
});
