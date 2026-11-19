import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import vm from 'node:vm';
import sharp from 'sharp';
import {imageDimensions,validateAssets,inspectImageLibrary,stageImageLibrary,verifyRemoteAsset,saveStagedImageLibrary} from './ego-draft-images.mjs';

const request={draftId:'123',store:'Store',erpSku:'SKU'};
const url=n=>`https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/u/1/${n}.png`;
function responseFor(bytes,address,options={}){
 const response=new Response(bytes,options);Object.defineProperty(response,'url',{value:address});return response;
}
async function asset(t){
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'ego-images-'));t.after(()=>fs.rm(folder,{recursive:true,force:true}));
 const file=path.join(folder,'test.png');const bytes=await sharp({create:{width:1600,height:1600,channels:3,background:'white'}}).png().toBuffer();
 await fs.writeFile(file,bytes);
 t.mock.method(globalThis,'fetch',async address=>responseFor(bytes,address));
 return{path:file,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),width:1600,height:1600,purpose:'calibration_only'};
}
function scenario(options={}){
 const state={draft:{url:'https://www.junfeikuajing.com/#/amazon/product/123?type=draft',store:'Store',erpSku:'SKU',copy:{title:'title',highlights:'highlights',description:'original',brand:'Generic',manufacturer:'Generic',bullets:['1','2','3','4','5'],terms:'terms'},description:'original',price:'7.69',quantity:'88',shippingTemplate:'template',handlingDays:'3'},
  cards:[{url:url(1),width:1600,height:1600},{url:url(2),width:1600,height:1600}],records:[],saveRecords:[],saves:0,uploads:0};
 const parent={};
 const save={innerText:'保存',closest:()=>({innerText:'翻译类型 保存 保存并发布'})},publish={innerText:'保存并发布'},edit={innerText:'编辑'};
 const cells=['123','Store',options.wrongRow?'wrong SKU':'SKU','未发布'].map(innerText=>({innerText}));
 const row={innerText:cells.map(c=>c.innerText).join(' '),querySelectorAll:s=>s==='td'?cells:s==='button'?[edit]:[]};
 const document={querySelector:()=>({value:'loaded'}),querySelectorAll:s=>{
  if(s==='button')return state.draft.url.endsWith('/draft')?[edit]:[save,publish];
  if(s==='tr')return state.draft.url.endsWith('/draft')?[row]:[];
  if(s==='input[type=file]')return options.badInput?[]:[{multiple:true,accept:'.jpg, .jpeg, .png',closest:()=>({innerText:'每个变体最多选择9张图片'})}];
  if(s==='.image-box')return state.cards.map(c=>({parentElement:parent,querySelector:selector=>selector==='input[type=checkbox]'?{value:c.url,checked:options.selected||false}:selector==='img.el-image__inner'?{complete:true,naturalWidth:c.width,naturalHeight:c.height}:null,querySelectorAll:selector=>selector==='i[title="删除图片"]'?[{}]:[]}));
  throw Error('Unexpected selector '+s);
 }};
 const execute=(fn,arg)=>vm.runInNewContext(`(${fn.toString()})(arg)`,{document,arg,URL,location:{href:state.draft.url,hash:new URL(state.draft.url).hash}});
 const ledger={create:async r=>{if(state.records.length)throw Error('existing operation');state.records.push(structuredClone(r));},write:async r=>state.records.push(structuredClone(r))};
 const page={evaluate:async(fn,arg)=>Array.isArray(arg)?structuredClone(state.draft):execute(fn,arg),
  setInputFiles:async(selector,files)=>{
   assert.equal(state.records.at(-1).status,'upload_unknown');assert.equal(files.length,1);state.uploads++;
   if(options.timeout)throw Error('upload response timeout');
   state.cards.push({url:options.duplicate?url(1):url(3),width:options.resize?800:1600,height:1600});
   if(options.reorder)state.cards.reverse();if(options.changePrice)state.draft.price='0.01';
  },waitForFunction:async(fn,arg)=>{if(!execute(fn,arg))throw Error('wait timed out');},
  click:async selector=>{
   assert.equal(selector,'button >> nth=0');
   if(state.draft.url.endsWith('/draft')){
    state.draft.url='https://www.junfeikuajing.com/#/amazon/product/123?type=draft';
    if(options.missingPersistedImage)state.cards.pop();
    if(options.copyChangedOnReopen)state.draft.copy.title='unexpected';
   }else{
    assert.equal(state.saveRecords.at(-1).status,'image_save_unknown');state.saves++;
    if(options.saveTimeout)throw Error('save timeout');
    state.draft.url='https://www.junfeikuajing.com/#/goods/amazon/draft';
   }
  }};
 const saveLedger={create:async r=>{if(state.saveRecords.length)throw Error('existing image save');state.saveRecords.push(structuredClone(r));},
  write:async r=>{if(options.diskFull&&r.status==='image_save_unknown')throw Error('disk full');state.saveRecords.push(structuredClone(r));}};
 return{state,page,ledger,saveLedger};
}

test('upload staging journals before effects and never saves or publishes',async t=>{
 const a=await asset(t),s=scenario();const result=await stageImageLibrary(s.page,request,[a],s.ledger);
 assert.equal(result.status,'image_staged_not_saved');assert.equal(result.saved,false);assert.equal(result.published,false);
 assert.equal(result.uploads[0].url,url(3));assert.equal(result.uploads[0].sha256,a.sha256);assert.equal(s.state.uploads,1);
 assert.equal(result.uploads[0].remote.sha256,a.sha256);assert.ok(result.uploads[0].remote.bytes>0);
});
test('same-size wrong-content server object is retained as uncertain and never retried',async t=>{
 const a=await asset(t),s=scenario();
 const other=await sharp({create:{width:1600,height:1600,channels:3,background:'black'}}).png().toBuffer();
 t.mock.method(globalThis,'fetch',async address=>responseFor(other,address));
 await assert.rejects(stageImageLibrary(s.page,request,[a],s.ledger),/SHA256/);
 const record=s.state.records.at(-1);
 assert.equal(record.status,'upload_unknown');assert.equal(record.pendingAsset,a.sha256);
 assert.equal(record.observedUpload.url,url(3));assert.equal(record.uploads.length,0);
 await assert.rejects(stageImageLibrary(s.page,request,[a],s.ledger),/existing operation/);
 assert.equal(s.state.uploads,1);
});
test('remote verification rejects untrusted hosts before making requests',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;throw Error('unexpected request');});
 for(const address of ['https://example.com/a.png','http://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/a.png','https://user@junfeikuajing.oss-cn-shenzhen.aliyuncs.com/a.png']){
  await assert.rejects(verifyRemoteAsset(address,{}),/地址不合法/);
 }
 assert.equal(calls,0);
});
test('remote read rejects HTTP failure, changed address, empty content and oversized responses',async t=>{
 const a=await asset(t);
 for(const make of [
  ()=>responseFor('unavailable',url(3),{status:503}),
  ()=>responseFor('redirected',url(4)),
  ()=>responseFor('',url(3)),
  ()=>responseFor('large',url(3),{headers:{'content-length':String(20*1024*1024+1)}}),
  ()=>responseFor(new ReadableStream({start(c){c.enqueue(new Uint8Array(20*1024*1024));c.enqueue(new Uint8Array(1));c.close();}}),url(3))
 ]){
  t.mock.method(globalThis,'fetch',async(address,options)=>{assert.equal(options.redirect,'error');assert.ok(options.signal);return make();});
  await assert.rejects(verifyRemoteAsset(url(3),a),/回读失败|SHA256|大小限制/);
 }
});
test('source hash, real dimensions, and rights are checked before browser effects',async t=>{
 const a=await asset(t);
 for(const change of [{sha256:'a'.repeat(64)},{width:800},{purpose:'reviewed_product_image'},{purpose:'unknown'}]){
  const s=scenario();await assert.rejects(stageImageLibrary(s.page,request,[{...a,...change}],s.ledger));
  assert.equal(s.state.uploads,0);assert.equal(s.state.records.length,0);
 }
 await assert.rejects(validateAssets([a,a]),/重复/);
});
test('accepted product transport requires explicit rights and review evidence',async t=>{
 const a=await asset(t),s=scenario();
 const result=await stageImageLibrary(s.page,request,[{...a,purpose:'reviewed_product_image',reviewed:true,rightsVerified:true,evidence:'test-only original artwork review'}],s.ledger);
 assert.equal(result.saved,false);assert.equal(result.uploads.length,1);
});
test('other store, SKU or route prevents uploading',async t=>{
 const a=await asset(t);
 for(const change of [{store:'Other'},{erpSku:'Other'},{url:'https://example.com/#/amazon/product/123?type=draft'}]){
  const s=scenario();Object.assign(s.state.draft,change);
  await assert.rejects(stageImageLibrary(s.page,request,[a],s.ledger),/身份不匹配/);assert.equal(s.state.uploads,0);
 }
});
test('changed or selected image controls stop before upload',async t=>{
 const a=await asset(t);
 for(const opts of [{badInput:true},{selected:true}]){
  const s=scenario(opts);await assert.rejects(stageImageLibrary(s.page,request,[a],s.ledger));assert.equal(s.state.uploads,0);
 }
});
test('timeout keeps original uncertain operation, without retrying',async t=>{
 const a=await asset(t),s=scenario({timeout:true});
 await assert.rejects(stageImageLibrary(s.page,request,[a],s.ledger),/timeout/);
 assert.equal(s.state.records.at(-1).status,'upload_unknown');assert.equal(s.state.uploads,1);
 await assert.rejects(stageImageLibrary(s.page,request,[a],s.ledger),/existing operation/);assert.equal(s.state.uploads,1);
});
test('partial, reordered, duplicate, resized and unrelated field changes stop without save',async t=>{
 const a=await asset(t);
 for(const opts of [{reorder:true},{duplicate:true},{resize:true},{changePrice:true}]){
  const s=scenario(opts);await assert.rejects(stageImageLibrary(s.page,request,[a],s.ledger));
  assert.equal(s.state.records.at(-1).status,'upload_unknown');assert.equal(s.state.records.at(-1).saved,false);assert.equal(s.state.uploads,1);
 }
});
test('library reads original checkbox URLs instead of thumbnail data URLs',async()=>{
 const s=scenario();const result=await inspectImageLibrary(s.page,request);
 assert.deepEqual(Array.from(result.images,i=>i.url),[url(1),url(2)]);
 assert.equal(result.maxPerVariant,9);
});

test('native-free metadata parser accepts JPEG and rejects truncated, animated or trailing PNG',async t=>{
 const a=await asset(t),png=await fs.readFile(a.path);
 const jpeg=await sharp(png).jpeg().toBuffer();
 assert.deepEqual(imageDimensions(jpeg),{format:'jpeg',width:1600,height:1600});
 assert.throws(()=>imageDimensions(png.subarray(0,png.length-12)),/不完整/);
 assert.throws(()=>imageDimensions(Buffer.concat([png,Buffer.from('extra')])),/结束标记/);
 const chunk=Buffer.alloc(20);chunk.writeUInt32BE(8,0);chunk.write('acTL',4);chunk.writeUInt32BE(2,8);
 assert.throws(()=>imageDimensions(Buffer.concat([png.subarray(0,33),chunk,png.subarray(33)])),/多帧/);
 assert.throws(()=>imageDimensions(Buffer.from('not a picture')),/仅接受/);
});

const reviewed=a=>({...a,purpose:'reviewed_product_image',reviewed:true,rightsVerified:true,evidence:'Original product artwork; reviewed against supplier facts'});
test('user default supplier image basis remains distinct from a verified supplier license',async t=>{
 const a={...await asset(t),purpose:'reviewed_product_image',reviewed:true,
  rightsBasis:'user_default_supplier_use_not_supplier_license',sourceUrl:'https://detail.1688.com/offer/952542058876.html',
  noUnauthorizedMarks:true,evidence:'User instruction 2026-11-02; supplier source reviewed'};
 await validateAssets([a]);assert.equal(a.rightsVerified,undefined);
 for(const change of [{sourceUrl:'https://www.amazon.com/dp/B012345678'},{noUnauthorizedMarks:false},{reviewed:false}])
  await assert.rejects(validateAssets([{...a,...change}]),/使用依据/);
});
test('reviewed staged image library saves once and verifies persisted order without claiming variant assignment',async t=>{
 const a=reviewed(await asset(t)),s=scenario();
 const staged=await stageImageLibrary(s.page,request,[a],s.ledger);
 const result=await saveStagedImageLibrary(s.page,request,staged,s.saveLedger);
 assert.equal(result.status,'image_library_saved_reopened_verified');assert.equal(result.saved,true);
 assert.equal(result.published,false);assert.equal(result.variantImagesVerified,false);assert.equal(result.productionImageCompleted,false);
 assert.equal(result.library.images.length,3);assert.equal(s.state.saves,1);assert.equal(s.state.uploads,1);
 await assert.rejects(saveStagedImageLibrary(s.page,request,staged,s.saveLedger),/existing image save/);
 assert.equal(s.state.saves,1);assert.equal(s.state.uploads,1);
});
test('calibration, uncertain upload and incomplete remote evidence never reach save',async t=>{
 const a=await asset(t),s=scenario(),calibration=await stageImageLibrary(s.page,request,[a],s.ledger);
 const reviewedStaged={...calibration,assets:[reviewed(a)]};
 for(const bad of [calibration,{...reviewedStaged,pendingAsset:a.sha256},
  {...reviewedStaged,uploads:[{...calibration.uploads[0],remote:undefined}]},
  {...reviewedStaged,before:{...calibration.before,draft:{...calibration.before.draft,copy:{}}}}]){
  await assert.rejects(saveStagedImageLibrary(s.page,request,bad,s.saveLedger));
 }
 assert.equal(s.state.saves,0);assert.equal(s.state.saveRecords.length,0);
});
test('save timeout, wrong row, lost persisted image and changed copy retain unknown save and never replay',async t=>{
 const a=reviewed(await asset(t));
 for(const options of [{saveTimeout:true},{wrongRow:true},{missingPersistedImage:true},{copyChangedOnReopen:true}]){
  const s=scenario(options),staged=await stageImageLibrary(s.page,request,[a],s.ledger);
  await assert.rejects(saveStagedImageLibrary(s.page,request,staged,s.saveLedger));
  assert.equal(s.state.saveRecords.at(-1).status,'image_save_unknown');
  await assert.rejects(saveStagedImageLibrary(s.page,request,staged,s.saveLedger),/existing image save/);
  assert.equal(s.state.saves,1);assert.equal(s.state.uploads,1);
 }
});
test('changed image order or draft copy and journal failure stop before save',async t=>{
 const a=reviewed(await asset(t));
 for(const change of ['order','copy','disk']){
  const s=scenario({diskFull:change==='disk'}),staged=await stageImageLibrary(s.page,request,[a],s.ledger);
  if(change==='order')s.state.cards.reverse();
  if(change==='copy')s.state.draft.copy.title='changed';
  await assert.rejects(saveStagedImageLibrary(s.page,request,staged,s.saveLedger));
  assert.equal(s.state.saves,0);assert.equal(s.state.uploads,1);
 }
});
