import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import sharp from 'sharp';
import {validateLibraryPackage,stageLibraryPackage,assertLibraryPackageState,saveLibraryPackage} from './ego-library-package.mjs';

async function fixture(t){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'package-test-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
 const bytes=await sharp({create:{width:1600,height:1600,channels:3,background:'white'}}).png().toBuffer();
 const file=path.join(dir,'fixture.png');await fs.writeFile(file,bytes);
 const assets=[{path:file,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),width:1600,height:1600,purpose:'reviewed_product_image',reviewed:true,rightsVerified:true,evidence:'Synthetic test fixture only'}];
 const request={accountId:1,productId:'fixture-product',store:'fixture-store',marketplace:'US',mode:'library_draft',sourceUrl:'https://detail.1688.com/offer/952542058876.html',sku:'FIXTURE',brand:'Generic',manufacturer:'Generic',title:'Fixture mat',description:'Fixture description',bullets:['One','Two','Three','Four','Five'],terms:'fixture',notes:'Test only',evidence:Object.fromEntries(['sourceUrl','title','description','bullets','terms'].map(k=>[k,'test fixture'])),commerce:{currency:'USD',price:'1.23',variants:[{sku:'CHILD',color:'Clear',size:'50 x 100 cm',price:'1.23'}],evidence:{price:'Synthetic test amount',variants:'Synthetic test variant'}}};
 return {input:{request,assets,bindings:[{sku:'CHILD',indices:[0]}]},bytes};
}

test('whole package rejects calibration, unreviewed assets and incomplete or foreign mappings before browser actions',async t=>{
 const {input}=await fixture(t);
 assert.equal(await validateLibraryPackage(input),input);
 for(const mutate of [x=>x.assets[0].purpose='calibration_only',x=>x.assets[0].reviewed=false,x=>delete x.request.commerce,x=>x.bindings=[],x=>x.bindings[0].sku='OTHER',x=>x.bindings[0].indices=[0,0],x=>x.bindings[0].indices=[1],x=>x.extra=true]){
  const bad=structuredClone(input);mutate(bad);
  await assert.rejects(stageLibraryPackage({evaluate:()=>assert.fail('browser must remain untouched')},bad,{create:()=>assert.fail('invalid input must not create operation')}));
 }
});

test('existing aggregate receipt prevents all browser effects, without bypassing prior attempts',async t=>{
 const {input}=await fixture(t);let creates=0;
 await assert.rejects(stageLibraryPackage({evaluate:()=>assert.fail('no replay'),goto:()=>assert.fail('do not open form before receipt')},input,{create:async()=>{creates++;throw Error('existing uncertain operation');}},{openNew:true}),/existing uncertain/);
 assert.equal(creates,1);
});

test('durable child receipt failure preserves reconciliation state and stops before typing',async t=>{
 const {input}=await fixture(t);let record;
 const blank={url:'https://www.junfeikuajing.com/#/product/library',form:{source:'1688',sourceUrl:'',sku:'',brand:'',manufacturer:'',title:'',description:'',terms:'',notes:'',bullets:['','','','','']},shipping:{'价格':''},variants:[],imageCount:0,variantSkuControlCount:1};
 let failed=false;
 await assert.rejects(stageLibraryPackage({evaluate:async()=>blank,fill:()=>assert.fail('intent first')},input,{create:async r=>{record=structuredClone(r);},write:async r=>{if(!failed){failed=true;throw Error('disk failure');}record=structuredClone(r);}}),/disk failure/);
 assert.equal(record.status,'library_package_requires_reconciliation');assert.equal(record.copy.status,'library_staging');assert.equal(record.saved,false);
});

test('final aggregate check verifies every variant receipt, full image order, fields and account scope',async t=>{
 const {input}=await fixture(t),url='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/test.png';
 input.request.commerce.variants.push({sku:'SECOND',color:'Clear',size:'50 x 100 cm',price:'1.23'});input.bindings.push({sku:'SECOND',indices:[0]});
 const base={url:'https://www.junfeikuajing.com/#/product/library',form:{sku:'FIXTURE'},shipping:{'价格':'1.23'},variantSkuControlCount:1,variants:input.request.commerce.variants.map(v=>({...v,images:[]})),imageCount:0};
 const upload={...input.request,status:'library_images_staged_not_saved',saved:false,published:false,assets:input.assets,uploads:[{url,width:1600,height:1600,sha256:input.assets[0].sha256,remote:{sha256:input.assets[0].sha256,bytes:123}}]};
 const record={input,status:'library_package_staging',copy:{staged:base},upload,bindings:input.bindings.map(b=>({...input.request,variantSku:b.sku,status:'library_variant_images_staged_reopened_verified',saved:false,published:false,boundUrls:[url]}))};
 const form={...base,variants:base.variants.map(v=>({...v,images:[url]})),imageCount:3},gallery={images:[{url}]};
 assert.doesNotThrow(()=>assertLibraryPackageState(record,form,gallery));
 for(const mutate of [r=>r.bindings[1].accountId=2,r=>r.bindings[1].boundUrls=['other'],r=>r.upload.pendingAsset='unknown',r=>r.bindings.pop()]){
  const bad=structuredClone(record);mutate(bad);assert.throws(()=>assertLibraryPackageState(bad,form,gallery));
 }
 for(const changed of [{...form,imageCount:2},{...form,shipping:{'价格':'9.99'}},{...form,variants:[form.variants[0],{...form.variants[1],images:['other']}]}])assert.throws(()=>assertLibraryPackageState(record,changed,gallery));
});

test('composed operation stages copy, commerce, upload and reopened binding without product save; timeout keeps original upload intent',async t=>{
 const {input,bytes}=await fixture(t),url='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/test.png';
 t.mock.method(globalThis,'fetch',async()=>{const r=new Response(bytes);Object.defineProperty(r,'url',{value:url});return r;});
 for(const timeout of [false,true]){
  const state={url:'https://www.junfeikuajing.com/#/product/library',form:{source:'1688',...Object.fromEntries(['sourceUrl','sku','brand','manufacturer','title','description','terms','notes'].map(k=>[k,''])),bullets:['','','','','']},shipping:{'价格':''},variantSkuControlCount:1,variants:[],imageCount:0};
  let uploaded=false,selected=[],uploads=0,latest,exists=false;const history=[];
  const gallery=()=>({images:uploaded?[{url,width:1600,height:1600}]:[],uploadSelector:'input[type=file]'});
  const page={
   evaluate:async(fn,arg)=>{
    const s=fn.toString();
    if(s.includes('const dialogs='))return structuredClone(state);
    if(s.includes('const files='))return gallery();
    if(s.includes('data-amazon-variant-control'))return ['sku','color','size','price'].map(k=>'variant:'+k);
    if(s.includes('const rows='))return 'variant-target';
    if(s.includes('const ds='))return {available:[url],selected:[...selected]};
    throw Error('unexpected fixture evaluation: '+s);
   },
   fill:async(selector,value)=>{
    if(selector.startsWith('variant:')){state.variants[0][selector.split(':')[1]]=value;return;}
    const p=/placeholder="([^"]+)"/.exec(selector)?.[1];
    if(p==='五点描述'){state.form.bullets[Number(selector.split('nth=')[1])]=value;return;}
    const key=Object.entries({sourceUrl:'来源链接',sku:'SKU',brand:'品牌',manufacturer:'制造商',title:'标题',description:'描述',terms:'关键词',notes:'备注'}).find(([,v])=>v===p)?.[0];
    if(key)state.form[key]=value;else if(p==='价格')state.shipping[p]=value;else assert.fail(selector);
   },
   click:async selector=>{
    if(selector.includes('添加变体'))state.variants.push({sku:'',color:'',size:'',price:'',images:[]});
    else if(selector.includes('data-amazon-image-add'))selected.push(url);
    else if(selector.includes('has-text("保存")')){
     assert.ok(selector.startsWith('[data-amazon-variant-picker='),'only local picker may save');
     state.variants[0].images=[selected[0]];state.imageCount=2;
    }else assert.ok(selector==='variant-target'||selector.includes('取 消'),selector);
   },
   setInputFiles:async()=>{assert.equal(latest.upload.status,'library_image_upload_unknown');uploads++;uploaded=true;state.imageCount=1;},
   waitForFunction:async()=>{if(timeout&&uploaded)throw Error('fixture upload observation timeout');}
  };
  const ledger={create:async r=>{if(exists)throw Error('operation exists');exists=true;latest=structuredClone(r);},write:async r=>{latest=structuredClone(r);history.push(latest);}};
  if(timeout){
   await assert.rejects(stageLibraryPackage(page,input,ledger),/observation timeout/);
   assert.equal(latest.status,'library_package_requires_reconciliation');assert.equal(latest.upload.pendingAsset,input.assets[0].sha256);
  }else{
   const result=await stageLibraryPackage(page,input,ledger);
   assert.equal(result.status,'library_package_staged_not_saved');assert.equal(result.saved,false);assert.equal(result.bindings.length,1);
   assert.equal(result.final.form.title,input.request.title);assert.equal(result.final.shipping['价格'],'1.23');
   assert.ok(history.some(r=>r.upload?.observedUpload));
   // Exercise persistence separately: only the outer product-save selector may
   // submit. Both preflight and reopened checks must inspect the full picker.
   for(const scenario of ['success','wrong_hidden_image','wrong_account','disk_failure','timeout','reopened_changed','rejected422']){
    const packageRecord=structuredClone(result);let productSaves=0,pickerReads=0;
    if(scenario==='wrong_account')packageRecord.accountId=2;
    const savePage={evaluate:async fn=>{
     const source=fn.toString();
     if(source.includes('const dialogs='))return scenario==='reopened_changed'&&productSaves?{...result.final,shipping:{'价格':'9.99'}}:structuredClone(result.final);
     if(source.includes('const files='))return gallery();
     if(source.includes('const ds=')){pickerReads++;return {available:[url],selected:scenario==='wrong_hidden_image'?[url,'unapproved-hidden-image']:[url]};}
     if(source.includes('const rows=')){
      if(source.includes('const cells='))return {id:'123',text:'fixture row',selector:'edit-saved'};
      return 'variant-target';
     }
     if(source.includes('const buttons='))return 'product-save';
     if(source.includes('const capture=window'))return scenario==='rejected422'?{messages:[],responses:[{status:422,validationErrors:{items:['fixture missing item']}}],requests:[{responseStatus:422}]}:{messages:[],responses:[],requests:[{responseStatus:200}]};
     if(source.includes('window.__amazonLibrarySaveObserver'))return 100;
     throw Error('unexpected save fixture evaluation: '+source);
    },click:async selector=>{if(selector==='product-save')productSaves++;else assert.ok(selector==='edit-saved'||selector==='variant-target'||selector.includes('取 消'));},waitForFunction:async()=>{if(scenario==='timeout'&&productSaves)throw Error('fixture save observation timeout');}};
    const saveLedger={write:async()=>{if(scenario==='disk_failure')throw Error('fixture disk failure');}};
    if(scenario==='success'){
     await saveLibraryPackage(savePage,packageRecord,saveLedger);
     assert.equal(packageRecord.status,'library_package_saved_reopened_verified');assert.equal(packageRecord.saved,true);assert.equal(packageRecord.published,false);assert.equal(packageRecord.libraryId,'123');assert.equal(pickerReads,2);
    }else{
     await assert.rejects(saveLibraryPackage(savePage,packageRecord,saveLedger));assert.equal(packageRecord.saved,false);
    }
    assert.equal(productSaves,['success','timeout','reopened_changed','rejected422'].includes(scenario)?1:0);
    if(scenario==='rejected422')assert.deepEqual(packageRecord.save.saveObservation.responses[0].validationErrors,{items:['fixture missing item']});
    await assert.rejects(saveLibraryPackage(savePage,packageRecord,saveLedger),/不能重复保存/);
   }
  }
  await assert.rejects(stageLibraryPackage(page,input,ledger),/operation exists/);assert.equal(uploads,1);
 }
});
