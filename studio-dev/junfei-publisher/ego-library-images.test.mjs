import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import sharp from 'sharp';
import {stageLibraryImages,validateLibraryBinding,stageLibraryVariantImages,inspectLibraryPicker,validateLibraryAssets} from './ego-library-images.mjs';
import {validateAssets} from './ego-draft-images.mjs';
import vm from 'node:vm';

test('multi-colour gallery accepts 42 distinct files while per-variant limit remains nine',async t=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'colour-gallery-test-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
 const assets=[];
 for(let n=0;n<42;n++){
  const bytes=await sharp({create:{width:1600,height:1600,channels:3,background:{r:n,g:110,b:155}}}).png().toBuffer();
  const file=path.join(dir,n+'.png');await fs.writeFile(file,bytes);
  assets.push({path:file,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),width:1600,height:1600,purpose:'reviewed_product_image',reviewed:true,rightsVerified:true,evidence:'Synthetic colour gallery regression fixture'});
 }
 assert.equal(await validateLibraryAssets(assets),assets);
 await assert.rejects(validateAssets(assets),/1至9/);
 await assert.rejects(validateLibraryAssets([...assets,assets[0]]),/重复/);
 const changed=structuredClone(assets);changed[20].purpose='calibration_only';
 await assert.rejects(validateLibraryAssets(changed),/不能混入/);
});

async function fixture(t,options={}){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'library-image-test-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
 const raw=await sharp({create:{width:1600,height:1600,channels:3,background:'white'}}).png().toBuffer();
 const file=path.join(dir,'calibration.png');await fs.writeFile(file,raw);
 const asset={path:file,sha256:crypto.createHash('sha256').update(raw).digest('hex'),width:1600,height:1600,purpose:'calibration_only'};
 const request={accountId:1,productId:'p',sku:'PARENT'};
 const before={url:'https://www.junfeikuajing.com/#/product/library',form:{sku:options.sku||'PARENT'},shipping:{price:''},variants:options.variants||[],variantSkuControlCount:1,imageCount:0};
 const image={url:'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/test.png',width:1600,height:1600};
 const writes=[];let uploads=0,created=false;
 const page={
  evaluate:async fn=>fn.toString().includes('const dialogs=')?{...structuredClone(before),...(options.changed&&uploads?{shipping:{price:'edited'}}:{})}:{images:options.existing||uploads?[image]:[],uploadSelector:'[data-amazon-library-active="true"] input[type=file]'},
  setInputFiles:async()=>{assert.equal(writes.at(-1).status,'library_image_upload_unknown');assert.equal(writes.at(-1).pendingAsset,asset.sha256);uploads++;},
  waitForFunction:async()=>{if(options.timeout)throw Error('fixture observation timeout');},
  click:async()=>assert.fail('upload tool must not click Save')
 };
 const ledger={create:async record=>{if(created||options.diskFailure)throw Error('fixture durable create failure');created=true;writes.push(structuredClone(record));},write:async record=>writes.push(structuredClone(record))};
 // verifyRemoteAsset requires response.url to match its requested OSS URL.
 t.mock.method(globalThis,'fetch',async()=>{const r=new Response(options.wrongBytes?Buffer.from('different content'):raw,{status:200});Object.defineProperty(r,'url',{value:image.url});return r;});
 return {page,request,asset,ledger,writes,uploads:()=>uploads,file};
}

test('upload journals intent, verifies exact bytes and leaves a staged unsaved receipt',async t=>{
 const f=await fixture(t);const r=await stageLibraryImages(f.page,f.request,[f.asset],f.ledger);
 assert.equal(r.status,'library_images_staged_not_saved');assert.equal(r.saved,false);assert.equal(r.published,false);
 assert.equal(r.uploads[0].remote.sha256,f.asset.sha256);assert.equal(f.uploads(),1);
 assert.equal(r.pendingAsset,null);assert.equal(r.observedUpload,null);
 assert.deepEqual(validateLibraryBinding(f.request,r,'CHILD',[0]),[r.uploads[0].url]);
 for(const change of [{accountId:2},{productId:'other'},{pendingAsset:'unknown'},{observedUpload:{url:'unknown'}},{status:'library_image_upload_unknown'}])assert.throws(()=>validateLibraryBinding(f.request,{...r,...change},'CHILD',[0]));
 for(const indices of [[],[0,0],[-1],[1],[0.5]])assert.throws(()=>validateLibraryBinding(f.request,r,'CHILD',indices));
});

test('wrong parent identity and existing library stop before uploads or ledger creation',async t=>{
 for(const options of [{sku:'OTHER'},{existing:true}]){
  const f=await fixture(t,options);await assert.rejects(stageLibraryImages(f.page,f.request,[f.asset],f.ledger));
  assert.equal(f.uploads(),0);assert.equal(f.writes.length,0);
 }
});

test('durable create failure prevents server upload',async t=>{
 const f=await fixture(t,{diskFailure:true});await assert.rejects(stageLibraryImages(f.page,f.request,[f.asset],f.ledger),/durable create/);assert.equal(f.uploads(),0);
});

test('timeout is retained as unknown and never permits an automatic re-upload',async t=>{
 const f=await fixture(t,{timeout:true});await assert.rejects(stageLibraryImages(f.page,f.request,[f.asset],f.ledger),/observation timeout/);
 assert.equal(f.writes.at(-1).status,'library_image_upload_unknown');assert.equal(f.uploads(),1);
 await assert.rejects(stageLibraryImages(f.page,f.request,[f.asset],f.ledger),/空图库/);assert.equal(f.uploads(),1);
});

test('wrong server bytes retain observed object for reconciliation',async t=>{
 const f=await fixture(t,{wrongBytes:true});await assert.rejects(stageLibraryImages(f.page,f.request,[f.asset],f.ledger),/SHA256/);
 assert.equal(f.writes.at(-1).status,'library_image_upload_unknown');assert.ok(f.writes.at(-1).observedUpload.url);assert.equal(f.uploads(),1);
});

test('unrelated edits during upload prevent successful staging',async t=>{
 const f=await fixture(t,{changed:true});await assert.rejects(stageLibraryImages(f.page,f.request,[f.asset],f.ledger),/字段变化/);
 assert.equal(f.writes.at(-1).saved,false);assert.equal(f.uploads(),1);
});

test('changed source bytes stop before browser effects',async t=>{
 const f=await fixture(t);await fs.writeFile(f.file,Buffer.from('changed'));
 await assert.rejects(stageLibraryImages(f.page,f.request,[f.asset],f.ledger));assert.equal(f.uploads(),0);
});

test('valid large PNG hits ERP five MB limit before browser effects',async t=>{
 const f=await fixture(t);
 const raw=await sharp(crypto.randomBytes(1600*1600*3),{raw:{width:1600,height:1600,channels:3}}).png().toBuffer();
 assert.ok(raw.length>=5*1024*1024);await fs.writeFile(f.file,raw);
 const asset={...f.asset,sha256:crypto.createHash('sha256').update(raw).digest('hex')};
 await assert.rejects(stageLibraryImages(f.page,f.request,[asset],f.ledger),/小于5MB/);assert.equal(f.uploads(),0);assert.equal(f.writes.length,0);
});

test('binding durable intent failure stops before opening or changing the picker',async t=>{
 const f=await fixture(t,{variants:[{sku:'CHILD',color:'Clear',size:'50x100',price:'1.23',images:[]}]});
 const upload=await stageLibraryImages(f.page,f.request,[f.asset],f.ledger);
 await assert.rejects(stageLibraryVariantImages(f.page,f.request,upload,'CHILD',[0],{create:async()=>{throw Error('binding intent unavailable');}}),/binding intent unavailable/);
 assert.equal(f.uploads(),1);
});

test('binding cannot use unrelated or already mapped variant',async t=>{
 const f=await fixture(t,{variants:[{sku:'OTHER',images:[]}]});
 const upload=await stageLibraryImages(f.page,f.request,[f.asset],f.ledger);
 let creates=0;await assert.rejects(stageLibraryVariantImages(f.page,f.request,upload,'CHILD',[0],{create:async()=>creates++}),/空变体图库/);assert.equal(creates,0);
});

test('picker waits for async thumbnails, ignores hidden previews and keeps original URL order',async()=>{
 let loaded=false,waited=false;
 const first='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/first.png',second='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/second.png';
 const thumb=url=>({getAttribute:()=>loaded?url+'?x-oss-process=image/resize,w_36':'',complete:true,naturalWidth:36});
 const all=[thumb(first),thumb(second)];
 const group=(name,images,buttons=[])=>({querySelector:()=>({innerText:name}),querySelectorAll:s=>s==='th .el-popover__reference img'?images:buttons});
 const groups=[group('变体图片',[all[1],all[0]]),group('图库',all,[{setAttribute(){}},{setAttribute(){}}])];
 const d={getBoundingClientRect:()=>({width:100}),setAttribute(){},querySelectorAll:s=>s==='.el-descriptions'?groups:s==='th .el-popover__reference img'?all:[]};
 const document={querySelectorAll:s=>s.includes('role="dialog"')?[d]:[]};
 const page={waitForFunction:async fn=>{assert.equal(vm.runInNewContext(`(${fn.toString()})()`,{document}),false);loaded=true;assert.equal(vm.runInNewContext(`(${fn.toString()})()`,{document}),true);waited=true;},evaluate:async fn=>{assert.ok(waited);return vm.runInNewContext(`(${fn.toString()})()`,{document,URL});}};
 const result=JSON.parse(JSON.stringify(await inspectLibraryPicker(page)));
 assert.deepEqual(result.available,[first,second]);assert.deepEqual(result.selected,[second,first]);
});
