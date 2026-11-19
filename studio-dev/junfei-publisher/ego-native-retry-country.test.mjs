import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {submitNativeMediaRecovery} from './ego-publication-recovery.mjs';

function scenario(country='GB'){
 const store=country==='GB'?'Store-UK':'Store-US',marketId=country==='GB'?'92':'91';let clicks=0;
 const input={destination:{countryCode:country,marketId},store,goods:{parentSku:'Original'}},record={publishId:'123',mediaRecovery:{intent:{publishId:'123'}}},sent=[];
 class XHR{constructor(){this.listeners=[];}open(method,url){this.method=method;this.url=url;}send(body){sent.push({method:this.method,url:this.url,body});this.status=200;this.responseText='{"code":0}';for(const cb of this.listeners)cb();}addEventListener(_type,cb){this.listeners.push(cb);}}
 const button={innerText:'再次发布',disabled:false,setAttribute(){},scrollIntoView(){}},row={cells:[{}, {innerText:'123'}, {}, {}, {innerText:store}, {innerText:'Original'}],getBoundingClientRect:()=>({width:100}),querySelectorAll:()=>[button]};
 const context=vm.createContext({window:{},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com/#/goods/amazon/publish'},document:{querySelectorAll:()=>[row]}});
 const page={evaluate:async(fn,arg)=>{context.arg=arg;return structuredClone(vm.runInContext('('+fn.toString()+')(arg)',context));},click:async selector=>{assert.equal(selector,'[data-native-media-recovery]');clicks++;const xhr=new context.XMLHttpRequest();xhr.open('POST','https://app.junfeikuajing.com/api/amazon/goods/publish/re-publish');xhr.send('{"ids":[123]}');},waitForFunction:async fn=>assert.equal(vm.runInContext('('+fn.toString()+')()',context),true)};
 const nativeRow={id:123,sku:'Original',market_id:marketId,country_code:country,market:{alias:store},status:'failed'};
 return{input,record,page,nativeRow,sent,get clicks(){return clicks;}};
}

test('normal original-family retry supports exact frozen US and GB identities',async()=>{
 for(const country of ['US','GB']){const f=scenario(country);await submitNativeMediaRecovery(f.page,f.input,f.record,async()=>{},{query:async()=>[f.nativeRow]});assert.equal(f.clicks,1);assert.equal(f.sent.length,1);assert.deepEqual(JSON.parse(f.sent[0].body),{ids:[123]});assert.equal(f.record.mediaRecovery.nativeRequests[0].response.httpStatus,200);}
});

test('foreign country, market, store, SKU, or duplicate parent rows never click or submit',async()=>{
 for(const replacement of [{country_code:'US'},{market_id:'91'},{market:{alias:'Other'}},{sku:'Foreign'},'duplicate']){
  const f=scenario('GB'),rows=replacement==='duplicate'?[f.nativeRow,f.nativeRow]:[{...f.nativeRow,...replacement}];
  await assert.rejects(()=>submitNativeMediaRecovery(f.page,f.input,f.record,async()=>{},{query:async()=>rows}),/原失败任务行或店铺不唯一/);
  assert.equal(f.clicks,0);assert.equal(f.sent.length,0);assert.equal(f.record.mediaRecovery.nativeRequests,undefined);
 }
});

test('callback mode arms only after exact native row, button and bound guard; foreign scope never arms',async()=>{
 const valid=scenario('GB');delete valid.record.mediaRecovery.intent;let armed=0;
 await submitNativeMediaRecovery(valid.page,valid.input,valid.record,async()=>{},{query:async()=>[valid.nativeRow],armIntent:async()=>{assert.equal(valid.record.mediaRecovery.nativePreflightProof.guardBound,true);assert.equal(valid.clicks,0);valid.record.mediaRecovery.intent={publishId:'123'};armed++;}});
 assert.equal(armed,1);assert.equal(valid.sent.length,1);
 const foreign=scenario('GB');delete foreign.record.mediaRecovery.intent;
 await assert.rejects(()=>submitNativeMediaRecovery(foreign.page,foreign.input,foreign.record,async()=>{},{query:async()=>[{...foreign.nativeRow,country_code:'US'}],armIntent:async()=>assert.fail('foreign row must not arm')}),/原失败任务行/);
 assert.equal(foreign.record.mediaRecovery.intent,undefined);assert.equal(foreign.clicks,0);
});
