import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {observeUkSchemaPreparation,installUkSchemaObservation,ukSchemaObservationSnapshot,releaseUkSchemaObservation,openUkCategoryRecommendations,ukAutoRecommendationStable} from './ego-uk-draft.mjs';

const meta={country_code:'GB',locale:'en_GB',hash:'real-schema-hash',product_type_name:'SHIRT',version:'observed-version',schema_content:{properties:{}}};
const endpoint='https://app.junfeikuajing.com/api/amazon/category/get-product-type?country_code=GB&product_type_name=SHIRT';
function schemaFixture(){
 class XHR{
  constructor(){this.listeners=[];}open(method,url){this.method=method;this.url=url;}send(){}addEventListener(_event,listener){this.listeners.push(listener);}
  complete(status,body){this.status=status;this.responseText=typeof body==='string'?body:JSON.stringify(body);for(const listener of this.listeners.splice(0))listener.call(this);}
 }
 const original={open:XHR.prototype.open,send:XHR.prototype.send},context=vm.createContext({window:{},XMLHttpRequest:XHR,URL,Date,location:{href:'https://www.junfeikuajing.com/#/amazon/product/200?type=draft'}});
 const evaluate=(fn,arg)=>{context.argument=arg;return structuredClone(vm.runInContext('('+fn.toString()+')(argument)',context));};
 const page={evaluate:async(fn,arg)=>evaluate(fn,arg),waitForFunction:async(fn,arg)=>{if(!evaluate(fn,arg))throw Error('page.waitForFunction timed out after 20000ms');}};
 const emit=(body={code:0,data:meta},status=200,url=endpoint)=>{const xhr=new XHR();xhr.open('GET',url);xhr.send();xhr.complete(status,body);return xhr;};
 const input={ukTarget:{storeName:'Target UK'}},record={draftId:'200'},snapshots=[],persist=async()=>snapshots.push(structuredClone(record));
 return{page,context,XHR,original,evaluate,emit,input,record,snapshots,persist};
}

test('UK native schema observer persists exact token bindings request result and metadata before cleanup',async()=>{
 const f=schemaFixture(),actual=await observeUkSchemaPreparation(f.page,f.input,f.record,f.persist,async()=>f.emit());
 assert.deepEqual(actual,meta);const observation=f.record.schemaRequestObservation;
 assert.equal(observation.stage,'schema_received');assert.match(observation.token,/^uk-schema:200:/);assert.equal(observation.expectedToken,observation.token);
 assert.deepEqual(observation.bindings,{open:true,send:true});assert.ok(observation.installedAt&&observation.endedAt);assert.equal(observation.requests.length,1);
 assert.equal(observation.requests[0].url,endpoint);assert.equal(observation.requests[0].httpStatus,200);assert.equal(observation.requests[0].code,0);assert.equal(observation.requests[0].parseError,null);
 assert.deepEqual(observation.metaIdentity,{country_code:'GB',locale:'en_GB',hash:meta.hash,product_type_name:'SHIRT',version:meta.version});
 assert.equal(observation.requests[0].accepted,true);assert.equal(f.context.window.__ukSchema,undefined);assert.equal(f.XHR.prototype.open,f.original.open);assert.equal(f.XHR.prototype.send,f.original.send);
 assert.ok(f.snapshots.some(snapshot=>snapshot.schemaRequestObservation.stage==='selecting_category'));
});

test('HTTP business-code JSON and GB identity failures remain strict and durable instead of becoming a silent timeout',async()=>{
 const cases=[{status:401,body:{code:1,data:null}},{body:{code:1,data:meta}},{body:{code:'0',data:meta}},{body:'not-json'},
  {body:{code:0,data:{...meta,country_code:'US'}}},{body:{code:0,data:{...meta,locale:'en_US'}}},{body:{code:0,data:{...meta,hash:''}}},
  {body:{code:0,data:{...meta,product_type_name:'COAT'}}}];
 for(const row of cases){const f=schemaFixture();await assert.rejects(()=>observeUkSchemaPreparation(f.page,f.input,f.record,f.persist,async()=>f.emit(row.body,row.status??200)),/严格检查/);
  const observation=f.record.schemaRequestObservation;assert.equal(observation.requests.length,1);assert.equal(observation.requests[0].accepted,false);assert.ok(observation.error&&observation.endedAt);assert.equal(observation.hasData,false);
  if(row.body==='not-json')assert.ok(observation.requests[0].parseError);assert.equal(f.context.window.__ukSchema,undefined);
 }
});

test('schema timeout preserves pending GET evidence and previous observations while restoring only owned wrappers',async()=>{
 const f=schemaFixture(),previous={token:'previous',requests:[{old:'preserved'}]};f.record.schemaRequestObservation=structuredClone(previous);
 await assert.rejects(()=>observeUkSchemaPreparation(f.page,f.input,f.record,f.persist,async()=>{const xhr=new f.XHR();xhr.open('GET',endpoint);xhr.send();}),/timed out/);
 const observation=f.record.schemaRequestObservation;assert.equal(observation.requests[0].url,endpoint);assert.equal(observation.requests[0].httpStatus,null);assert.match(observation.error,/timed out/);assert.ok(observation.endedAt);
 assert.deepEqual(f.record.schemaRequestObservationHistory,[previous]);assert.equal(f.context.window.__ukSchema,undefined);assert.equal(f.XHR.prototype.open,f.original.open);
});

test('lost exact XHR bindings or token stop before schema waiting and never overwrite a foreign wrapper on cleanup',async()=>{
 for(const key of ['open','send','token']){const f=schemaFixture(),foreign=function(){};
  await assert.rejects(()=>observeUkSchemaPreparation(f.page,f.input,f.record,f.persist,async()=>{if(key==='token')f.context.window.__ukSchema.token='other-token';else f.XHR.prototype[key]=foreign;}),/绑定/);
  const observation=f.record.schemaRequestObservation;assert.equal(observation.hasData,false);assert.ok(observation.error);if(key==='token')assert.notEqual(observation.expectedToken,observation.token);else{assert.equal(observation.bindings[key],false);assert.equal(f.XHR.prototype[key],foreign);}
 }
});

test('US schema and a reused XHR for another endpoint cannot satisfy a GB schema observation',async()=>{
 const f=schemaFixture();await assert.rejects(()=>observeUkSchemaPreparation(f.page,f.input,f.record,f.persist,async()=>f.emit({code:0,data:{...meta,country_code:'US',locale:'en_US'}},200,endpoint.replace('country_code=GB','country_code=US'))),/timed out/);
 assert.equal(f.record.schemaRequestObservation.requests[0].countryCode,'US');assert.equal(f.record.schemaRequestObservation.hasData,false);
 const g=schemaFixture();g.evaluate(installUkSchemaObservation,'reuse-token');const xhr=new g.XHR();xhr.open('GET',endpoint);xhr.open('GET','https://app.junfeikuajing.com/api/common/lookup');xhr.send();xhr.complete(200,{code:0,data:meta});
 assert.deepEqual(g.evaluate(ukSchemaObservationSnapshot,'reuse-token').requests,[]);g.evaluate(releaseUkSchemaObservation,'reuse-token');
});

function recommendationFixture({existing=false,missing=false,neverUnmask=false,arriveWhileWaiting=false}={}){
 let recommended=existing,masked=true,rect={x:10,y:-1000,width:100,height:30},scrolls=0;const clicks=[],stability=[];
 const button={innerText:'自动识别产品类型',disabled:false,getBoundingClientRect:()=>rect,contains:hit=>hit===button,scrollIntoView:()=>{scrolls++;rect={...rect,y:50};}};
 const visible={getBoundingClientRect:()=>({width:1})},context=vm.createContext({window:{},document:{querySelectorAll:selector=>selector==='button'?(missing?[]:[button]):recommended?[visible]:[],elementFromPoint:()=>masked?{}:button},getComputedStyle:()=>({opacity:'1',pointerEvents:'auto',visibility:'visible'}),innerWidth:800,innerHeight:600});
 const evaluate=(fn,arg)=>{context.argument=arg;return vm.runInContext('('+fn.toString()+')(argument)',context);};
 const page={evaluate:async(fn,arg)=>evaluate(fn,arg),click:async selector=>{assert.equal(masked,false);clicks.push(selector);recommended=true;},waitForFunction:async(fn,arg)=>{
  for(let n=0;n<6;n++){if(arriveWhileWaiting&&fn===ukAutoRecommendationStable)recommended=true;const ready=evaluate(fn,arg);if(fn===ukAutoRecommendationStable){stability.push(ready);if(!neverUnmask)masked=false;}if(ready)return;}
  throw Error('stable recommendation timeout');
 }};
 return{page,clicks,stability,get scrolls(){return scrolls;}};
}

test('UK fallback scrolls and hit-tests the native auto button until mask settles, then waits only for recommendation dialog',async()=>{
 const f=recommendationFixture();await openUkCategoryRecommendations(f.page);assert.equal(f.scrolls,1);assert.deepEqual(f.clicks,['loc=role:button[name="自动识别产品类型"]']);assert.deepEqual(f.stability.slice(0,4),[false,false,false,true]);
});

test('existing recommendation is reused and absent or masked auto controls never fall back to category search or Save',async()=>{
 const existing=recommendationFixture({existing:true});await openUkCategoryRecommendations(existing.page);assert.deepEqual(existing.clicks,[]);assert.equal(existing.scrolls,0);
 const missing=recommendationFixture({missing:true});await assert.rejects(()=>openUkCategoryRecommendations(missing.page),/入口/);assert.deepEqual(missing.clicks,[]);
 const blocked=recommendationFixture({neverUnmask:true});await assert.rejects(()=>openUkCategoryRecommendations(blocked.page),/timeout/);assert.deepEqual(blocked.clicks,[]);
});

test('a recommendation arriving asynchronously during the auto wait is reused without clicking its covered button',async()=>{
 const f=recommendationFixture({arriveWhileWaiting:true,neverUnmask:true});await openUkCategoryRecommendations(f.page);
 assert.deepEqual(f.clicks,[]);assert.equal(f.scrolls,1);assert.deepEqual(f.stability,[true]);
});
