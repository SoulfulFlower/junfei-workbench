import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {validateLibraryRequest,validateLibraryCommerce,fillLibraryCommerce,openNewLibraryForm,stageLibraryDraft,saveStagedLibraryDraft,startSaveObservation,finishSaveObservation,inspectLibraryForm} from './ego-library-draft.mjs';

const request={accountId:1,productId:'source-variant',store:'示例店铺-美国',marketplace:'US',mode:'library_draft',sourceUrl:'https://detail.1688.com/offer/952542058876.html',sku:'WYJ20261102142256',brand:'Generic',manufacturer:'Generic',title:'Clear PVC Table Protector, 50 x 100 cm',description:'Clear PVC sheet, 1.5mm thick.',bullets:['Clear PVC','50 x 100 cm','1.5mm thickness','Rounded corners','Measure before ordering'],terms:'desk pad',notes:'Incomplete draft; do not publish',evidence:Object.fromEntries(['sourceUrl','title','description','bullets','terms'].map(k=>[k,'observed source record']))};
const blank=()=>({url:'https://www.junfeikuajing.com/#/product/library',form:{source:'',sourceUrl:'',sku:'',brand:'',manufacturer:'',title:'',description:'',terms:'',notes:'',bullets:['','','','','']},shipping:{'价格':'','重量':''},variants:[],imageCount:0,variantSkuControlCount:1});
const staged=()=>({accountId:1,productId:request.productId,sku:request.sku,request:structuredClone(request),before:blank(),status:'library_draft_staged_not_saved'});
const actual=()=>({...blank(),form:{source:'1688',...Object.fromEntries(['sourceUrl','sku','brand','manufacturer','title','description','terms','notes','bullets'].map(k=>[k,request[k]]))}});
const commerce=()=>({currency:'USD',price:'1.23',variants:[{sku:'FIXTURE-CLEAR',color:'Clear',size:'50 x 100 cm',price:'1.23'}],evidence:{price:'Synthetic UI test amount; never saved or offered for sale',variants:'Synthetic test variant'}});

test('commerce accepts 24 verified rows and rejects unsupported capacity without dropping SKUs',()=>{
 const c=commerce();c.variants=Array.from({length:24},(_,n)=>({...c.variants[0],sku:`FIXTURE-${n}`}));
 assert.equal(validateLibraryCommerce(c).variants.length,24);
 c.variants.push({...c.variants[0],sku:'FIXTURE-24'});
 assert.throws(()=>validateLibraryCommerce(c),/1–24/);
});

test('commerce requires supported currency, positive decimal prices, unique SKUs and explicit evidence',()=>{
 assert.equal(validateLibraryCommerce(commerce()).currency,'USD');
 for(const patch of [{currency:'CNY'},{price:'0'},{price:'-1'},{price:1.23},{price:'1e2'},{price:'1.234'},{price:'NaN'},{evidence:{}},{variants:[]},{quantity:88}])assert.throws(()=>validateLibraryCommerce({...commerce(),...patch}));
 for(const v of [{...commerce().variants[0],price:''},{...commerce().variants[0],sku:'bad/sku'},{...commerce().variants[0],color:''}])assert.throws(()=>validateLibraryCommerce({...commerce(),variants:[v]}));
 assert.throws(()=>validateLibraryCommerce({...commerce(),variants:[...commerce().variants,...commerce().variants]}));
 assert.doesNotThrow(()=>validateLibraryRequest({...request,commerce:commerce()}));
});

test('exported size-bearing child SKU is preserved, unsafe or padded identities are rejected',()=>{
 const c=commerce();c.variants[0].sku='WYJ20261102142256-C01-50 x 100 cm';
 assert.equal(validateLibraryCommerce(c).variants[0].sku,c.variants[0].sku);
 for(const sku of ['', ' leading','trailing ','two  spaces','a\tb','a\nb','../sku','a/b','a\\b','a'.repeat(41)]){
  assert.throws(()=>validateLibraryCommerce({...c,variants:[{...c.variants[0],sku}]}));
 }
});

test('commerce filling refuses existing rows or prices before any mutation',async()=>{
 for(const change of [{variants:[{sku:'EXISTING'}]},{shipping:{'价格':'99'}}]){
  let changes=0;const page={evaluate:async()=>({...blank(),...change}),fill:async()=>changes++,click:async()=>changes++};
  await assert.rejects(fillLibraryCommerce(page,commerce()),/仅允许/);assert.equal(changes,0);
 }
});

test('stale variant price, SKU, images or unrelated shipping stops before external save',async()=>{
 const c=commerce(),good={...actual(),shipping:{...blank().shipping,'价格':c.price},variants:[{...c.variants[0],images:[]}]};
 for(const change of [{variants:[{...good.variants[0],price:'9.99'}]},{variants:[{...good.variants[0],sku:'OTHER'}]},{variants:[{...good.variants[0],images:['unreviewed.png']}]},{shipping:{...good.shipping,'重量':'999'}}]){
  let changes=0;const record={...staged(),request:{...request,commerce:c}};
  await assert.rejects(saveStagedLibraryDraft({evaluate:async()=>({...good,...change}),click:async()=>changes++},record,{write:async()=>changes++}));
  assert.equal(changes,0);
 }
});

test('valid commerce reaches durable intent without relying on JSON property order',async()=>{
 const c=commerce();c.variants[0]={price:'1.23',size:'50 x 100 cm',color:'Clear',sku:'FIXTURE-CLEAR'};
 const good={...actual(),shipping:{...blank().shipping,'价格':c.price},variants:[{sku:'FIXTURE-CLEAR',color:'Clear',size:'50 x 100 cm',price:'1.23',images:[]}]};
 let calls=0;const page={evaluate:async()=>++calls===1?good:'button >> nth=12',click:async()=>assert.fail('must persist intent first')};
 await assert.rejects(saveStagedLibraryDraft(page,{...staged(),request:{...request,commerce:c}},{write:async()=>{throw Error('fixture durable-intent stop');}}),/fixture durable-intent stop/);
});

test('new library tool rejects publication, unsupported logistics, credentials and ungrounded copy',()=>{
 for(const patch of [{mode:'publish'},{price:'7.69'},{sourceUrl:'https://u:p@detail.1688.com/offer/952542058876.html'},{brand:'supplier'},{sku:'a b'},{terms:'中'.repeat(84)},{evidence:{}},{bullets:['one']}])assert.throws(()=>validateLibraryRequest({...request,...patch}));
 assert.equal(validateLibraryRequest(request),request);
});

test('an explicitly sourced shop brand is accepted without assuming other brands apply',()=>{
 const branded={...request,brand:'KIMEETOL',manufacturer:'KIMEETOL',evidence:{...request.evidence,brand:'Target shop sync receipt and current user confirmation',manufacturer:'Observed target shop sync; user confirmed brand use'}};
 assert.equal(validateLibraryRequest(branded),branded);
 for(const evidence of [{...branded.evidence,brand:''},{...branded.evidence,manufacturer:''}])assert.throws(()=>validateLibraryRequest({...branded,evidence}));
 for(const brand of [' KIMEETOL','KIMEETOL\nOTHER','<brand>','a'.repeat(51)])assert.throws(()=>validateLibraryRequest({...branded,brand}));
});

test('existing form and wrong site are stopped before ledger creation or typing',async()=>{
 for(const change of [{url:'https://example.com/#/product/library'},{form:{...blank().form,sku:'EXISTING'}},{shipping:{'重量':'975'}},{imageCount:1},{variants:[{sku:'EXISTING'}]}]){
  let mutations=0;
  const page={evaluate:async()=>({...blank(),...change}),fill:async()=>mutations++};
  await assert.rejects(stageLibraryDraft(page,request,{create:async()=>mutations++}));assert.equal(mutations,0);
 }
});

test('opening a new form waits for the visible dialog even when a hidden previous dialog remains',async()=>{
 const calls=[];
 const document={querySelector:()=>({}),querySelectorAll:selector=>selector==='button'?[{innerText:'添加'}]:[{getBoundingClientRect:()=>({width:0})},{getBoundingClientRect:()=>({width:1200})}]};
 const page={goto:async url=>calls.push(url),evaluate:async()=>false,click:async selector=>calls.push(selector),waitForSelector:async()=>{throw Error('first hidden dialog would time out');},waitForFunction:async fn=>assert.equal(vm.runInNewContext(`(${fn.toString()})()`,{document,location:{hash:'#/product/library'}}),true)};
 await openNewLibraryForm(page);assert.equal(calls.length,2);assert.equal(calls[1],'loc=role:button[name="添加"]');
});

test('existing visible dialog stops a second add before any click',async()=>{
 let clicks=0;const page={goto:async()=>{},waitForFunction:async()=>{},evaluate:async()=>true,click:async()=>clicks++};
 await assert.rejects(openNewLibraryForm(page),/已有产品详情表单/);assert.equal(clicks,0);
});

test('changed text or shipping after staging cannot be saved',async()=>{
 for(const change of [{form:{...actual().form,title:'someone edited this'}},{shipping:{'价格':'0.01','重量':''}},{variants:[{sku:request.sku,color:'Clear',size:'50 x 100 cm',price:'0.01',images:[]}]}]){
  let writes=0,clicks=0;
  const page={evaluate:async()=>({...actual(),...change}),click:async()=>clicks++};
  await assert.rejects(saveStagedLibraryDraft(page,staged(),{write:async()=>writes++}));assert.equal(clicks,0);assert.equal(writes,0);
 }
});

test('durable save intent failure prevents external save',async()=>{
 let calls=0,clicks=0;
 const page={evaluate:async()=>++calls===1?actual():'button >> nth=12',click:async()=>clicks++};
 await assert.rejects(saveStagedLibraryDraft(page,staged(),{write:async()=>{throw Error('disk full');}}),/disk full/);
 assert.equal(clicks,0);
});

test('save observation timeout stays unknown and same operation cannot be replayed',async()=>{
 let calls=0,clicks=0;const history=[],record=staged();
 const page={evaluate:async()=>{calls++;return calls===1?actual():calls===2?'button >> nth=12':calls===3?100:{messages:[],requests:[]};},click:async()=>{clicks++;},waitForFunction:async()=>{throw Error('observation timeout');}};
 const ledger={write:async r=>history.push(structuredClone(r))};
 await assert.rejects(saveStagedLibraryDraft(page,record,ledger),/observation timeout/);
 assert.equal(record.status,'library_save_unknown');assert.equal(clicks,1);assert.equal(history.at(-1).status,'library_save_unknown');
 await assert.rejects(saveStagedLibraryDraft(page,record,ledger),/仅允许保存/);assert.equal(clicks,1);
});

test('completed HTTP 422 and transient UI validation message are retained without a second save',async()=>{
 let calls=0,clicks=0;const record=staged(),history=[];
 const page={evaluate:async()=>{
  calls++;return calls===1?actual():calls===2?'button >> nth=12':calls===3?100:{messages:['fixture validation failure'],requests:[{responseStatus:422,startTime:101,responseEnd:102}]};
 },click:async()=>clicks++,waitForFunction:async()=>{}};
 await assert.rejects(saveStagedLibraryDraft(page,record,{write:async r=>history.push(structuredClone(r))}),/HTTP 422/);
 assert.equal(clicks,1);assert.equal(record.status,'library_save_unknown');
 assert.deepEqual(history.at(-1).saveObservation.messages,['fixture validation failure']);
 await assert.rejects(saveStagedLibraryDraft(page,record,{write:async()=>{}}),/仅允许保存/);assert.equal(clicks,1);
});

test('validation response capture ignores credentials and other endpoints and restores XHR methods',async()=>{
 class XHR{open(method,url){this.method=method;this.url=url;}send(){this.sent=true;}addEventListener(name,fn){this.listener=fn;}finish(status,body){this.status=status;this.responseText=JSON.stringify(body);this.listener?.();}}
 const originalOpen=XHR.prototype.open,originalSend=XHR.prototype.send;
 const sandbox={window:{},document:{body:{},querySelectorAll:()=>[]},location:{href:'https://www.junfeikuajing.com/#/product/library'},performance:{now:()=>100,getEntriesByType:()=>[]},MutationObserver:class{observe(){}disconnect(){}},XMLHttpRequest:XHR,URL,WeakMap};
 const context=vm.createContext(sandbox),page={evaluate:async fn=>vm.runInContext(`(${fn.toString()})()`,context)};
 await startSaveObservation(page);
 const other=new XHR();other.open('POST','https://example.com/login');other.send();other.finish(422,{message:'other private response'});
 const save=new XHR();save.open('POST','https://app.junfeikuajing.com/api/product/store');save.send();save.finish(422,{message:'Validation failed',errors:{items:['fixture missing item'],api_key:['never store this']},secret:'not a field'});
 const observed=JSON.parse(JSON.stringify(await finishSaveObservation(page)));
 assert.equal(observed.responses.length,1);assert.deepEqual(observed.responses[0].validationErrors,{items:['fixture missing item']});
 assert.equal(JSON.stringify(observed).includes('never store'),false);assert.equal(JSON.stringify(observed).includes('other private'),false);
 assert.equal(XHR.prototype.open,originalOpen);assert.equal(XHR.prototype.send,originalSend);
});


test('observed split-table variants are read by header and cell positions, not generic placeholders',async()=>{
 const placeholders=['来源','来源链接','SKU','品牌','制造商','标题','描述','关键词','备注','价格','长','宽','高','重量','中文名','英文名','申报价格','海关编码','是否带电','请选择开发人','请选择采购人','制造商编号'];
 const input=(placeholder,value='')=>({value,type:'text',getAttribute:k=>k==='placeholder'?placeholder:null});
 const all=placeholders.map(p=>input(p));
 for(let i=1;i<=5;i++)all.push({...input('五点描述'),closest:()=>({previousElementSibling:{innerText:`五点描述${i}`}})});
 const controls=['CHILD-1','Clear','50 x 100 cm','15.60'].map((value,i)=>({...input('placeholder',value),closest:()=>({cellIndex:i+2})}));
 const row={querySelectorAll:s=>s==='input'?controls:s==='img'?[{getAttribute:()=>'/image.webp'}]:[]};
 const table={querySelectorAll:s=>s==='.el-table__header th'?['','图片','SKU','颜色','尺寸','价格','操作',''].map(innerText=>({innerText})):s==='.el-table__body tr'?[row]:[]};
 const dialog={getBoundingClientRect:()=>({width:100}),setAttribute(){},querySelectorAll:s=>s==='input,textarea'?all:s==='.el-table'?[table]:[]};
 const document={querySelectorAll:s=>s.includes('role="dialog"')?[dialog]:[]};
 const page={evaluate:async fn=>vm.runInNewContext(`(${fn.toString()})()`,{document,location:{href:'https://www.junfeikuajing.com/#/product/library'}})};
 const observed=JSON.parse(JSON.stringify(await inspectLibraryForm(page)));
 assert.deepEqual(observed.variants,[{sku:'CHILD-1',color:'Clear',size:'50 x 100 cm',price:'15.60',images:['/image.webp']}]);
 controls[0].closest=()=>({cellIndex:3});
 await assert.rejects(inspectLibraryForm(page),/变体字段结构变化/);
});
