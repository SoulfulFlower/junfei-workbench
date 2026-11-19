import {test} from 'node:test';
import assert from 'node:assert/strict';
import {validateRequest,updateExistingDraft} from './existing-draft.mjs';

const request=()=>({draftId:'172528873',store:'测试店铺',erpSku:'ERP-SKU',patch:{price:'7.69',quantity:'88'}});
function harness(options={}) {
  const r=request(), history=[];
  let record=null, url='', saves=0, reopened=false;
  const state={'店铺':r.store,'父Sku,可自定义填写内容，方便卖家在后台识别是什么产品，该内容不在平台商城展示':r.erpSku,'价格':'6.00','库存':'1'};
  const counts={};
  const locator=(kind,name)=>({
    count:async()=>counts[name]??(kind==='button'&&name==='保存'?2:1),
    waitFor:async()=>{if(options.toastFailure&&kind==='alert')throw Error('toast timeout');},
    inputValue:async()=>options.identityMismatch&&name==='店铺'?'其他店铺':options.persistFailure&&reopened&&name==='价格'?'6.00':state[name],
    fill:async value=>{state[name]=value;},
    nth:()=>({click:async()=>{saves++;if(options.saveFailure)throw Error('save timeout');url='https://www.junfeikuajing.com/#/goods/amazon/draft';}}),
    filter:()=>locator(kind,name),
    getByRole:(role,opts)=>locator(role,opts?.name),
    innerText:async()=>`${r.draftId} ${r.store} ${r.erpSku} 未发布`,
    click:async()=>{reopened=true;url=`https://www.junfeikuajing.com/#/amazon/product/${r.draftId}?type=draft`;},
  });
  if(options.duplicatePrice)counts['价格']=2;
  if(options.changedButtons)counts['保存']=3;
  if(options.wrongRow)counts[r.erpSku]=0;
  const page={url:()=>url,goto:async value=>{url=value;},getByPlaceholder:name=>locator('input',name),getByRole:(role,opts)=>locator(role,opts?.name),waitForURL:async expected=>assert.equal(url,expected)};
  const ledger={read:async()=>record,write:async value=>{record=structuredClone(value);history.push(structuredClone(value));}};
  return {page,ledger,history,get record(){return record;},get saves(){return saves;}};
}
test('请求拒绝发布字段、路径注入和非明确数值',()=>{
  for(const change of [{draftId:'../1'},{patch:{store:'other'}},{patch:{price:'0'}},{patch:{price:'7.69USD'}},{patch:{quantity:'1.5'}},{patch:{handlingDays:'-1'}},{patch:{title:''}}])assert.throws(()=>validateRequest({...request(),...change}));
});
test('保存前身份不匹配，不点击保存',async()=>{
  const h=harness({identityMismatch:true});await assert.rejects(updateExistingDraft(h.page,request(),h.ledger),/店铺或ERP/);
  assert.equal(h.saves,0);assert.equal(h.record.status,'stopped_before_save');
});
test('字段或保存按钮不唯一时拒绝写入',async()=>{
  for(const opts of [{duplicatePrice:true},{changedButtons:true}]){
    const h=harness(opts);await assert.rejects(updateExistingDraft(h.page,request(),h.ledger));assert.equal(h.saves,0);
  }
});
test('保存前持久记录未知状态，列表和重开值一致才成功',async()=>{
  const h=harness();const result=await updateExistingDraft(h.page,request(),h.ledger);
  assert.deepEqual(h.history.map(r=>r.status),['started','saving_unknown','draft_saved_verified']);
  assert.equal(result.after.values.price,'7.69');assert.equal(h.saves,1);
  await assert.rejects(updateExistingDraft(h.page,request(),h.ledger),/已有执行记录/);assert.equal(h.saves,1);
});
test('保存超时、成功提示缺失、列表身份错误、重开值不符均保留未知状态',async()=>{
  for(const opts of [{saveFailure:true},{toastFailure:true},{wrongRow:true},{persistFailure:true}]){
    const h=harness(opts);await assert.rejects(updateExistingDraft(h.page,request(),h.ledger));
    assert.equal(h.record.status,'saving_unknown');assert.equal(h.saves,1);
    await assert.rejects(updateExistingDraft(h.page,request(),h.ledger),/已有执行记录/);assert.equal(h.saves,1);
  }
});
test('持久保存未知状态失败，不点击保存',async()=>{
  const h=harness();const write=h.ledger.write;
  h.ledger.write=async r=>{if(r.status==='saving_unknown')throw Error('disk full');await write(r);};
  await assert.rejects(updateExistingDraft(h.page,request(),h.ledger),/disk full/);assert.equal(h.saves,0);
});
