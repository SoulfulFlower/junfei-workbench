import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {submitNativePublication} from './ego-publish-native.mjs';
import {submitNativeCopy} from './ego-copy-native.mjs';

// Executes the real browser XHR guards in an isolated fake DOM/XHR context.
// No EGO/browser process, website, login or network is used by these tests.
function fakePage({sourceId='101',route='/api/amazon/goods/draft/publish',ids=[101],copy=false}={}){
 const sent=[],attrs={},events=[];let current='https://www.junfeikuajing.com/#/goods/amazon/draft',menuOpen=false;
 const action={innerText:copy?'复制':'发布',setAttribute:(k,v)=>attrs[k]=v};
 const menu={innerText:'操作',setAttribute:(k,v)=>attrs[k]=v};
 const row={getBoundingClientRect:()=>({width:500}),innerText:`${sourceId} Parent Exact Store`,cells:Array.from({length:9},()=>({innerText:''})),querySelectorAll:()=>copy?[menu]:[action]};
 row.cells[1].innerText=sourceId;row.cells[4].innerText='Exact Store';row.cells[5].innerText='Parent';
 const popup={getBoundingClientRect:()=>({width:menuOpen?100:0}),querySelectorAll:()=>[action]};
 class FakeXHR{
  open(method,url){this.method=method;this.url=url;}
  addEventListener(_event,fn){this.listener=fn;}
  send(body){sent.push({method:this.method,url:this.url,body});this.status=200;this.responseText=JSON.stringify(this.method==='GET'?{code:0,data:{list:{total:1,data:[{id:Number(sourceId),sku:'Parent',market:{alias:'Exact Store'}}]}}}:{code:0,data:null});this.listener?.();}
 }
 const context=vm.createContext({URL,WeakMap,Date,JSON,Error,XMLHttpRequest:FakeXHR,window:{},location:{href:current},getComputedStyle:()=>({visibility:'visible',display:'block'}),document:{querySelector:s=>s==='.el-pagination__total'?{innerText:'共 1 条'}:null,querySelectorAll:s=>s==='.el-table__body tr'?[row]:s==='.el-dropdown-menu'?[popup]:[]}});
 const evaluate=async(fn,arg)=>vm.runInContext(`(${fn.toString()})(${JSON.stringify(arg)??'undefined'})`,context);
 const page={evaluate,goto:async url=>{current=url;context.location.href=url;menuOpen=false;},reload:async()=>{},waitForSelector:async()=>{},fill:async()=>{},
  waitForFunction:async(fn,arg)=>{assert(await evaluate(fn,arg),'fake condition must hold without timers');},
  hover:async selector=>{assert.equal(selector,'[data-native-copy-menu]');assert.equal(attrs['data-native-copy-menu'],'true');events.push('hover-copy-menu');menuOpen=true;},
  click:async selector=>{
   if(selector==='loc=role:button[name="搜索"]'){
    const section=new URL(current).hash.endsWith('/draft')?'draft':'publish';
    vm.runInContext(`(()=>{const x=new XMLHttpRequest();x.open('GET',${JSON.stringify('https://app.junfeikuajing.com/api/amazon/goods/'+section+'/index?sku=Parent')});x.send();})()`,context);
   }else if(selector==='[data-native-publication]'||selector==='[data-native-copy-once]'){
    if(copy){assert.equal(menuOpen,true);assert.equal(attrs['data-native-copy-once'],'true');}
    vm.runInContext(`(()=>{const x=new XMLHttpRequest();x.open('POST',${JSON.stringify('https://app.junfeikuajing.com'+route)});x.send(${JSON.stringify(JSON.stringify({ids}))});})()`,context);
   }else assert.fail('unexpected native UI action: '+selector);
  }};
 return{page,sent,context,events};
}
const input={goods:{parentSku:'Parent'},store:'Exact Store',destination:{draftId:'101'}};

test('actual native publish guard captures exact single request and blocks another click',async()=>{
 const {page,sent}=fakePage(),record={phase:'publish_unknown',intent:{draftId:'101'}};
 await submitNativePublication(page,input,record,async()=>{});
 assert.equal(record.nativeRequests.length,1);assert.equal(record.nativeRequests[0].path,'/api/amazon/goods/draft/publish');
 assert.equal(sent.filter(v=>v.method==='GET'&&v.url.includes('/draft/index?sku=Parent')).length,1);
 assert.equal(sent.filter(v=>v.method==='POST').length,1);
 await assert.rejects(submitNativePublication(page,input,record,async()=>{}),/禁止重发/);
});

test('actual publish XHR guard refuses a wrong source id and unrelated mutation',async()=>{
 for(const variant of [{ids:[999]},{route:'/api/amazon/goods/draft/delete'}]){
  const {page,sent}=fakePage(variant),record={phase:'publish_unknown',intent:{draftId:'101'}};
  await assert.rejects(submitNativePublication(page,input,record,async()=>{}),/拦截/);
  assert.equal(sent.filter(v=>v.method==='POST').length,0);
 }
});

test('actual copy guard records the route emitted by UI with exact publishing id',async()=>{
 const {page,sent,events}=fakePage({copy:true,sourceId:'202',route:'/api/amazon/goods/publish/copy',ids:[202]}),record={phase:'copy_unknown',intent:{sourcePublishId:'202'}};
 await submitNativeCopy(page,{source:input,sourcePublication:{publishId:'202'}},record,async()=>{});
 assert.equal(record.nativeRequests[0].path,'/api/amazon/goods/publish/copy');assert.equal(sent.filter(v=>v.method==='POST').length,1);
 assert.equal(sent.filter(v=>v.method==='GET'&&v.url.includes('/publish/index?sku=Parent')).length,1);assert.deepEqual(events,['hover-copy-menu']);
 await assert.rejects(submitNativeCopy(page,{source:input,sourcePublication:{publishId:'202'}},record,async()=>{}),/禁止重发/);
});

test('actual copy XHR guard refuses an unrelated source or endpoint before network send',async()=>{
 for(const variant of [{route:'/api/amazon/goods/publish/copy',ids:[999]},{route:'/api/amazon/goods/publish/delete',ids:[202]}]){
  const {page,sent}=fakePage({copy:true,sourceId:'202',...variant}),record={phase:'copy_unknown',intent:{sourcePublishId:'202'}};
  await assert.rejects(submitNativeCopy(page,{source:input,sourcePublication:{publishId:'202'}},record,async()=>{}),/拦截/);
  assert.equal(sent.filter(v=>v.method==='POST').length,0);
 }
});
