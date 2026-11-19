import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readNativeOnline} from './ego-publish-native.mjs';

// Execute the production query and row-locator callbacks against the observed
// online table: ID column 1, store column 4, ASIN column 5, SKU column 6.
function fixture({labels=['修改'],rowSku='Parent',rowStore='Exact US',duplicateRow=false}={}){
 const attrs={},sent=[],clicked=[];
 const entries=labels.map(innerText=>({innerText,disabled:false,getAttribute:key=>key==='aria-disabled'?'false':null,
  getBoundingClientRect:()=>({width:80}),setAttribute:(key,value)=>{attrs[key]=value;}}));
 const row={innerText:`404 ${rowStore} ASIN ${rowSku}`,cells:Array.from({length:10},()=>({innerText:''})),
  getBoundingClientRect:()=>({width:800}),querySelectorAll:selector=>selector==='a,button'?entries:[]};
 row.cells[1].innerText='404';row.cells[4].innerText=rowStore;row.cells[5].innerText='B0MOCK';row.cells[6].innerText=rowSku;
 class XHR{
  open(method,url){this.method=method;this.url=url;}
  addEventListener(_name,callback){this.callback=callback;}
  send(body){sent.push({method:this.method,url:this.url,body});this.status=200;
   this.responseText=JSON.stringify(this.url.includes('/index?')?{code:0,data:{list:{total:1,data:[{id:404,sku:'Parent',market:{alias:'Exact US'}}]}}}:{code:0,data:{id:404,sku:'Parent',status:'online'}});this.callback?.();}
 }
 const context=vm.createContext({URL,WeakMap,JSON,Error,XMLHttpRequest:XHR,window:{},location:{href:'https://www.junfeikuajing.com/#/goods/amazon/online'},
  getComputedStyle:()=>({visibility:'visible',display:'block'}),document:{querySelectorAll:selector=>selector==='.el-table__body tr'?(duplicateRow?[row,row]:[row]):[]}});
 const evaluate=async(fn,arg)=>vm.runInContext(`(${fn.toString()})(${JSON.stringify(arg)??'undefined'})`,context);
 const request=url=>vm.runInContext(`(()=>{const x=new XMLHttpRequest();x.open('GET',${JSON.stringify(url)});x.send();})()`,context);
 const page={evaluate,goto:async url=>{context.location.href=url;},reload:async()=>{},waitForSelector:async()=>{},fill:async()=>{},
  waitForFunction:async(fn,arg)=>assert(await evaluate(fn,arg)),click:async selector=>{
   clicked.push(selector);
   if(selector==='loc=role:button[name="搜索"]')request('https://app.junfeikuajing.com/api/amazon/goods/online/index?sku=Parent');
   else if(selector==='[data-native-online-read]'){assert.equal(attrs['data-native-online-read'],'true');request('https://app.junfeikuajing.com/api/amazon/goods/online/show?id=404');}
   else assert.fail('Unexpected UI action: '+selector);
  }};
 return{page,sent,clicked};
}
const input={goods:{parentSku:'Parent'},store:'Exact US'};

test('observed exact 修改 opens only the original online detail through GET',async()=>{
 const {page,sent,clicked}=fixture();const result=await readNativeOnline(page,'404',input);
 assert.equal(result.data.id,404);assert.deepEqual(clicked,['loc=role:button[name="搜索"]','[data-native-online-read]']);
 assert.equal(sent.length,2);assert(sent.every(request=>request.method==='GET'));
});

test('legacy exact 编辑 remains supported by the same read-only adapter',async()=>{
 const {page,sent}=fixture({labels:['编辑']});assert.equal((await readNativeOnline(page,'404',input)).data.status,'online');
 assert.equal(sent.filter(request=>request.url.includes('/online/show?id=404')).length,1);
});

test('two entries partial bulk labels foreign SKU/store and duplicate rows stop before detail action',async()=>{
 for(const options of [{labels:['编辑','修改']},{labels:['批量修改']},{labels:['修改资料']},{rowSku:'Parent-other'},
  {rowStore:'Exact US other'},{duplicateRow:true}]){
  const {page,sent,clicked}=fixture(options);
  await assert.rejects(()=>readNativeOnline(page,'404',input),/在线来源/);
  assert.deepEqual(clicked,['loc=role:button[name="搜索"]']);
  assert.equal(sent.filter(request=>request.url.includes('/online/show')).length,0);
 }
});
