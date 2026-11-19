import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {applyDescription,validateRequest,updateEgoDraft} from './ego-existing-draft.mjs';
const request={draftId:'172528873',store:'示例店铺-美国',erpSku:'MTkzMzU-I18DXZWC',patch:{description:'Verified description'},evidence:{description:'source record'}};
test('other store, SKU, route and host cannot be edited',async()=>{
 for(const change of [{store:'other'},{erpSku:'other'},{url:'https://www.junfeikuajing.com/#/amazon/product/172527185?type=draft'},{url:'https://example.com/#/amazon/product/172528873?type=draft'}]) {
  let fills=0;
  const page={evaluate:async()=>({url:'https://www.junfeikuajing.com/#/amazon/product/172528873?type=draft',store:request.store,erpSku:request.erpSku,description:'old',...change}),fill:async()=>{fills++;}};
  await assert.rejects(applyDescription(page,request),/身份不匹配/);
  assert.equal(fills,0);
 }
});
test('adapter rejects unsupported price/publish changes and evidence-free copy',()=>{
 for(const patch of [{price:'0.01'},{publish:true},{description:'copy'}]) {
  assert.throws(()=>validateRequest({...request,patch,evidence:{}}));
 }
});

function scenario(options={}) {
 const values={'店铺':request.store,'父Sku,自定义':request.erpSku,'产品描述':'old copy','价格':'7.69','库存':'88','亚马逊运输模板':'Migrated Template','处理时间':'3','品牌':'OLD_BRAND','制造商':'OLD_MAKER'};
 const controls=Object.entries(values).map(([name,value])=>({value,getAttribute:key=>key==='placeholder'?name:null}));
 const description=controls[2];
 const title={value:'old title',getAttribute:key=>key==='placeholder'?'产品标题':null};
 const highlights={value:'',getAttribute:key=>key==='placeholder'?'商品亮点':null};
 const bulletControls=Array.from({length:6},(_,i)=>({value:'old '+i,getAttribute:key=>key==='placeholder'?'Bullet Point':null,
  closest:selector=>selector==='.el-form-item'?{innerText:i<5?'五点描述':'关键词'}:selector==='#product-attr-keywords'&&i===5?{}:null}));
 controls.push(title,highlights,...bulletControls);
 const state={url:'',saves:0,record:null,history:[],persisted:'old copy'};
 const save={innerText:'保存',closest:()=>({innerText:'翻译类型 保存 保存并发布'})};
 const publish={innerText:'保存并发布',closest:()=>({innerText:'翻译类型 保存 保存并发布'})};
 const edit={innerText:'编辑'};
 const cells=[request.draftId,request.store,options.wrongRow?'other SKU':request.erpSku,'未发布'].map(innerText=>({innerText}));
 const row={innerText:cells.map(c=>c.innerText).join(' '),querySelectorAll:s=>s==='td'?cells:s==='button'?[edit]:[]};
 function document() {
  const list=state.url.endsWith('/draft');
  return {querySelector:s=>s==='textarea[placeholder="产品描述"]'?description:s==='input[placeholder="店铺"]'?controls[0]:['品牌','制造商','亚马逊运输模板'].some(x=>s===`input[placeholder="${x}"]`)?controls.find(c=>s===`input[placeholder="${c.getAttribute('placeholder')}"]`):null,
   querySelectorAll:s=>s==='input,textarea'?controls:s==='textarea[placeholder="Bullet Point"]'?bulletControls:s==='input'?controls.filter(c=>c!==description):s==='button'?(list?[edit]:[save,publish]):s==='tr'&&list?[row]:[]};
 }
 const execute=(fn,arg)=>vm.runInNewContext(`(${fn.toString()})(arg)`,{arg,document:document(),location:{href:state.url,hash:new URL(state.url).hash}});
 const page={
  goto:async url=>{state.url=url;},
  evaluate:async(fn,arg)=>execute(fn,arg),
  waitForFunction:async(fn,arg)=>{if(!execute(fn,arg))throw Error('page wait timeout');},
  fill:async(selector,value)=>{
   const index=/nth=(\d+)/.exec(selector);
   const field=index?bulletControls[Number(index[1])]:selector.startsWith('#product-attr-keywords')?bulletControls[5]:selector.includes('产品标题')?title:selector.includes('商品亮点')?highlights:selector.includes('placeholder="品牌"')?controls.find(c=>c.getAttribute('placeholder')==='品牌'):selector.includes('placeholder="制造商"')?controls.find(c=>c.getAttribute('placeholder')==='制造商'):description;
   if(options.reactiveManufacturer&&selector.includes('placeholder="制造商"')&&value&&field.value)field.value=value+value;
   else field.value=value;
   if(options.reactiveManufacturer&&selector.includes('placeholder="品牌"'))controls.find(c=>c.getAttribute('placeholder')==='制造商').value=value;
   if(options.changePrice)controls.find(e=>e.getAttribute('placeholder')==='价格').value='0.01';
  },
  click:async selector=>{
   assert.equal(selector,'button >> nth=0');
   if(state.url.endsWith('/draft')) {
    state.url=`https://www.junfeikuajing.com/#/amazon/product/${request.draftId}?type=draft`;
    description.value=options.persistFailure?'old copy':state.persisted;
    if(options.brandPersistFailure)controls.find(c=>c.getAttribute('placeholder')==='品牌').value='OLD_BRAND';
   } else {
    assert.equal(state.record.status,'save_unknown');
    state.saves++;
    if(options.saveTimeout)throw Error('save timeout');
    state.persisted=description.value;state.url='https://www.junfeikuajing.com/#/goods/amazon/draft';
   }
  }
 };
 const ledger={create:async r=>{if(state.record)throw Error('existing receipt');state.record=structuredClone(r);state.history.push(r.status);},
  write:async r=>{if(options.diskFull&&r.status==='save_unknown')throw Error('disk full');state.record=structuredClone(r);state.history.push(r.status);}};
 return {page,ledger,state};
}

test('ego workflow saves once and verifies persisted copy and row identity',async()=>{
 const h=scenario();
 const result=await updateEgoDraft(h.page,request,h.ledger);
 assert.equal(result.status,'draft_saved_reopened_verified');
 assert.equal(result.reopened.description,request.patch.description);
 assert.deepEqual(h.state.history,['started','save_unknown','draft_saved_reopened_verified']);
 await assert.rejects(updateEgoDraft(h.page,request,h.ledger),/existing receipt/);
 assert.equal(h.state.saves,1);
});

test('ego save timeout, row mismatch and persisted value mismatch remain unknown without replay',async()=>{
 for(const options of [{saveTimeout:true},{wrongRow:true},{persistFailure:true}]) {
  const h=scenario(options);
  await assert.rejects(updateEgoDraft(h.page,request,h.ledger));
  assert.equal(h.state.record.status,'save_unknown');
  await assert.rejects(updateEgoDraft(h.page,request,h.ledger),/existing receipt/);
  assert.equal(h.state.saves,1);
 }
});

test('ego cannot click save before the unknown state is durable',async()=>{
 const h=scenario({diskFull:true});
 await assert.rejects(updateEgoDraft(h.page,request,h.ledger),/disk full/);
 assert.equal(h.state.saves,0);
});

const fullRequest={...request,patch:{title:'White Zipper Toiletry Bag',highlights:'White zipper pouch',bullets:['Storage','Dimensions','Zipper','Brushes','White'],description:'Verified copy',terms:'toiletries brush pouch'},evidence:Object.fromEntries(['title','highlights','bullets','description','terms'].map(key=>[key,'verified product facts']))};

test('all five copy fields persist with five bullets separated from backend terms',async()=>{
 const h=scenario();const result=await updateEgoDraft(h.page,fullRequest,h.ledger);
 assert.deepEqual(JSON.parse(JSON.stringify(result.reopened.copy)),fullRequest.patch);
 assert.equal(h.state.saves,1);
});

test('malformed copy, unsupported fields and byte overflow stop before browser work',()=>{
 for(const patch of [{title:'a'.repeat(76)},{highlights:'a'.repeat(126)},{bullets:['only one']},{bullets:['a','b','c','d','e\nf']},{terms:'汉'.repeat(84)},{brand:'other'}]) {
  assert.throws(()=>validateRequest({...fullRequest,patch}));
 }
});

test('an unexpected price change during filling cannot be saved',async()=>{
 const h=scenario({changePrice:true});
 await assert.rejects(updateEgoDraft(h.page,fullRequest,h.ledger),/经营参数发生变化/);
 assert.equal(h.state.saves,0);
});

const genericRequest={...fullRequest,patch:{...fullRequest.patch,brand:'Generic',manufacturer:'Generic'},evidence:{...fullRequest.evidence,brand:'Unbranded supplier; no verified brand authorization',manufacturer:'Generic fallback; actual maker unconfirmed'}};
test('Generic fallback is paired, source-bound and reopened before verification',async()=>{
 const h=scenario({reactiveManufacturer:true});const result=await updateEgoDraft(h.page,genericRequest,h.ledger);
 assert.deepEqual(JSON.parse(JSON.stringify(result.reopened.copy)),genericRequest.patch);
 assert.equal(result.changes.before.copy.brand,'OLD_BRAND');assert.equal(h.state.saves,1);
 const bad=scenario({brandPersistFailure:true});await assert.rejects(updateEgoDraft(bad.page,genericRequest,bad.ledger),/重开后/);
 assert.equal(bad.state.record.status,'save_unknown');assert.equal(bad.state.saves,1);
});
test('arbitrary and one-sided brand edits cannot reach the browser',()=>{
 for(const patch of [{brand:'Generic'},{manufacturer:'Generic'},{brand:'OTHER',manufacturer:'OTHER'}])assert.throws(()=>validateRequest({...genericRequest,patch}),/Generic/);
 assert.throws(()=>validateRequest({...genericRequest,evidence:{...genericRequest.evidence,brand:''}}),/来源/);
});
