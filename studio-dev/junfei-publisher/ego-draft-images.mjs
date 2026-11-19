// Ego image-library transport. Staging does not save; the separate guarded
// persistence function saves reviewed product assets only. Neither publishes.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {inspectDraft,clickSaveUnchangedDraft,reopenSavedDraft} from './ego-existing-draft.mjs';

// Ego's embedded Node runtime cannot load the native sharp addon. Read only
// container metadata here; the server preflight and browser decode the pixels.
export function imageDimensions(data){
  if(data.length>=33&&data.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))){
    let offset=8,dimensions=null,hasData=false;
    while(offset+12<=data.length){
      const length=data.readUInt32BE(offset),type=data.toString('ascii',offset+4,offset+8);
      if(offset+12+length>data.length)throw Error('PNG分块不完整');
      if(offset===8&&(type!=='IHDR'||length!==13))throw Error('PNG尺寸头无效');
      if(type==='IHDR'){
        if(dimensions||length!==13)throw Error('PNG尺寸头重复或无效');
        dimensions={format:'png',width:data.readUInt32BE(offset+8),height:data.readUInt32BE(offset+12)};
      }
      if(type==='acTL')throw Error('不接受多帧PNG');
      if(type==='IDAT'&&length)hasData=true;
      offset+=12+length;
      if(type==='IEND'){
        if(length||offset!==data.length||!dimensions||!hasData)throw Error('PNG结束标记无效');
        return dimensions;
      }
    }
    throw Error('PNG文件不完整');
  }
  if(data.length>4&&data[0]===255&&data[1]===216){
    let offset=2;
    while(offset+4<=data.length){
      if(data[offset++]!==255)throw Error('JPEG标记无效');
      while(data[offset]===255)offset++;
      const marker=data[offset++];
      if(marker===217||marker===218)break;
      if(marker===1||(marker>=208&&marker<=215))continue;
      if(offset+2>data.length)break;
      const length=data.readUInt16BE(offset);
      if(length<2||offset+length>data.length)throw Error('JPEG分段不完整');
      if([192,193,194].includes(marker)){
        if(length<8)throw Error('JPEG尺寸头无效');
        return{format:'jpeg',height:data.readUInt16BE(offset+3),width:data.readUInt16BE(offset+5)};
      }
      offset+=length;
    }
  }
  throw Error('仅接受可解析的单帧PNG或JPEG文件');
}

export async function validateAssets(assets) {
  if(!Array.isArray(assets)||!assets.length||assets.length>9)throw Error('必须明确1至9张待传图片');
  const seen=new Set();
  for(const asset of assets){
    if(!asset||typeof asset.path!=='string'||!path.isAbsolute(asset.path)||
       !/\.(png|jpe?g)$/i.test(asset.path)||!/^([a-f0-9]{64})$/.test(asset.sha256||'')||
       !['calibration_only','reviewed_product_image'].includes(asset.purpose))throw Error('图片路径、用途或哈希不完整');
    if(seen.has(asset.sha256))throw Error('图片重复，未重复上传');seen.add(asset.sha256);
    let userDefault=false;
    if(asset.rightsBasis==='user_default_supplier_use_not_supplier_license'){
      try{const u=new URL(asset.sourceUrl);userDefault=asset.noUnauthorizedMarks===true&&u.protocol==='https:'&&
        !u.username&&!u.password&&!u.port&&u.hostname==='detail.1688.com'&&/^\/offer\/\d+\.html$/.test(u.pathname);}catch{}
    }
    if(asset.purpose==='reviewed_product_image'&&
       (asset.reviewed!==true||!(asset.rightsVerified===true||userDefault)||typeof asset.evidence!=='string'||!asset.evidence.trim()))throw Error('商品图片缺少审核及使用依据');
    const data=await fs.readFile(asset.path);
    if(!data.length||data.length>20*1024*1024||crypto.createHash('sha256').update(data).digest('hex')!==asset.sha256)throw Error('图片文件变化或大小不合法');
    const meta=imageDimensions(data);
    if(!['png','jpeg'].includes(meta.format)||!meta.width||!meta.height||
       Math.min(meta.width,meta.height)<1600||meta.width!==asset.width||meta.height!==asset.height||
       (meta.pages||1)!==1)throw Error('图片真实格式、尺寸或帧数不合格');
  }
  if(assets.some(a=>a.purpose==='calibration_only')&&(assets.length!==1||assets[0].purpose!=='calibration_only'))throw Error('校准图不能混入商品套图');
  return assets;
}

export async function inspectImageLibrary(page,request){
  await inspectDraft(page,request);
  return page.evaluate(()=>{
    const files=[...document.querySelectorAll('input[type=file]')];
    if(files.length!==1||!files[0].multiple||files[0].accept!=='.jpg, .jpeg, .png'||
       !files[0].closest('form')?.innerText.includes('每个变体最多选择9张图片'))throw Error('图片库上传控件变化，停止操作');
    const boxes=[...document.querySelectorAll('.image-box')];
    if(!boxes.length||boxes.some(e=>e.parentElement!==boxes[0].parentElement))throw Error('图片库结构变化，停止操作');
    const images=boxes.map((box,index)=>{
      const check=box.querySelector('input[type=checkbox]'),img=box.querySelector('img.el-image__inner');
      const remove=box.querySelectorAll('i[title="删除图片"]');
      if(!check||!img||remove.length!==1)throw Error('图片库卡片不完整');
      const url=new URL(check.value);
      if(url.protocol!=='https:'||!/^junfeikuajing\.oss-[a-z0-9-]+\.aliyuncs\.com$/.test(url.hostname))throw Error('图片库来源地址异常');
      if(!img.complete||!img.naturalWidth||!img.naturalHeight)throw Error('图片库仍在加载，未继续操作');
      return{index,url:check.value,width:img.naturalWidth,height:img.naturalHeight,selected:check.checked};
    });
    if(new Set(images.map(i=>i.url)).size!==images.length)throw Error('图片库地址重复，未继续操作');
    return{images,uploadSelector:'input[type="file"].el-upload__input',maxPerVariant:9};
  });
}

export function assertDraftUnchanged(before,after){
  for(const key of ['url','store','erpSku','copy','description','price','quantity','shippingTemplate','handlingDays'])
    if(JSON.stringify(before[key])!==JSON.stringify(after[key]))throw Error('上传期间草稿字段变化: '+key);
}

export async function verifyRemoteAsset(url,asset){
  const parsed=new URL(url);
  if(parsed.protocol!=='https:'||parsed.username||parsed.password||parsed.port||
     !/^junfeikuajing\.oss-[a-z0-9-]+\.aliyuncs\.com$/.test(parsed.hostname))throw Error('回读图片地址不合法');
  const response=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(20000)});
  if(!response.ok||response.url!==url){await response.body?.cancel().catch(()=>{});throw Error('服务器图片回读失败或地址变化');}
  const maxBytes=20*1024*1024;
  if(Number(response.headers.get('content-length'))>maxBytes){await response.body?.cancel().catch(()=>{});throw Error('服务器图片超过大小限制');}
  if(!response.body)throw Error('服务器图片内容为空');
  const reader=response.body.getReader(),hash=crypto.createHash('sha256');let bytes=0;
  try{
    while(true){
      const chunk=await reader.read();if(chunk.done)break;
      bytes+=chunk.value.byteLength;
      if(bytes>maxBytes)throw Error('服务器图片超过大小限制');
      hash.update(chunk.value);
    }
  }catch(error){await reader.cancel().catch(()=>{});throw error;}
  finally{reader.releaseLock();}
  const sha256=hash.digest('hex');
  if(!bytes||sha256!==asset.sha256)throw Error('服务器图片内容与源文件SHA256不一致');
  return{sha256,bytes,verifiedAt:new Date().toISOString()};
}

export async function stageImageLibrary(page,request,assets,ledger){
  await validateAssets(assets);
  const draft=await inspectDraft(page,request,{allCopy:true});
  const library=await inspectImageLibrary(page,request);
  if(library.images.some(i=>i.selected))throw Error('图片库有已勾选项目，请先核查原操作');
  const record={draftId:request.draftId,store:request.store,erpSku:request.erpSku,
    assets:assets.map(a=>({...a})),before:{draft,library},uploads:[],
    status:'prepared',saved:false,published:false,createdAt:new Date().toISOString()};
  await ledger.create(record);
  try{
    for(const asset of assets){
      const expected=[...library.images.map(i=>i.url),...record.uploads.map(i=>i.url)];
      const before=await inspectImageLibrary(page,request);
      if(JSON.stringify(before.images.map(i=>i.url))!==JSON.stringify(expected))throw Error('上传前图片库已变化，未覆盖原操作');
      record.status='upload_unknown';record.pendingAsset=asset.sha256;await ledger.write(record);
      await page.setInputFiles(before.uploadSelector,[asset.path]);
      await page.waitForFunction(count=>{
        const boxes=[...document.querySelectorAll('.image-box')];
        return boxes.length===count+1&&boxes.every(e=>{const i=e.querySelector('img.el-image__inner');return i?.complete&&i.naturalWidth>0;});
      },expected.length,{timeout:20000});
      const after=await inspectImageLibrary(page,request),urls=after.images.map(i=>i.url);
      if(JSON.stringify(urls.slice(0,-1))!==JSON.stringify(expected)||expected.includes(urls.at(-1)))throw Error('上传后图片库数量或顺序不符');
      const uploaded=after.images.at(-1);
      if(uploaded.width!==asset.width||uploaded.height!==asset.height)throw Error('上传后图片尺寸与源文件不符');
      // Persist the observed server object before the read: on failure this
      // remains an uploaded object to reconcile, never permission to re-upload.
      record.observedUpload={...uploaded,sourceSha256:asset.sha256};await ledger.write(record);
      const remote=await verifyRemoteAsset(uploaded.url,asset);
      assertDraftUnchanged(draft,await inspectDraft(page,request,{allCopy:true}));
      record.uploads.push({...uploaded,sha256:asset.sha256,remote});delete record.pendingAsset;delete record.observedUpload;
      record.status='image_staged_not_saved';await ledger.write(record);
    }
    record.stagedAt=new Date().toISOString();await ledger.write(record);return record;
  }catch(error){record.error=error.message;await ledger.write(record);throw error;}
}

// This persists the product image LIBRARY only. Variant assignments remain a
// separate observed UI operation; library persistence is not listing completion.
export async function saveStagedImageLibrary(page,request,staged,ledger){
  if(staged?.status!=='image_staged_not_saved'||staged.saved!==false||staged.published!==false||
     ['draftId','store','erpSku'].some(k=>staged[k]!==request[k]))throw Error('缺少同一草稿已暂存未保存的图片回执');
  await validateAssets(staged.assets);
  if(staged.assets.some(a=>a.purpose!=='reviewed_product_image')||staged.pendingAsset||staged.observedUpload||
     !Array.isArray(staged.uploads)||staged.uploads.length!==staged.assets.length)throw Error('只有全部审核及权利通过的商品图片才能保存；校准图或未知上传不能保存');
  for(let i=0;i<staged.assets.length;i++){
    const a=staged.assets[i],u=staged.uploads[i];
    if(u.sha256!==a.sha256||u.remote?.sha256!==a.sha256||!(u.remote.bytes>0)||
       u.width!==a.width||u.height!==a.height)throw Error('图片回读证据或尺寸不匹配');
  }
  const fullKeys=['title','highlights','description','brand','manufacturer','bullets','terms'];
  if(!staged.before?.draft?.copy||fullKeys.some(k=>!Object.hasOwn(staged.before.draft.copy,k)))throw Error('原草稿缺少完整文案快照；请核查旧回执，不重传');
  const expected=[...staged.before.library.images,...staged.uploads].map(({url,width,height})=>({url,width,height}));
  if(new Set(expected.map(i=>i.url)).size!==expected.length)throw Error('图片地址重复，停止保存');
  const record={draftId:request.draftId,store:request.store,erpSku:request.erpSku,
    staged,expected,status:'image_save_started',saved:false,published:false,
    variantImagesVerified:false,productionImageCompleted:false,createdAt:new Date().toISOString()};
  await ledger.create(record);
  try{
    const checkLibrary=async()=>{
      const actual=await inspectImageLibrary(page,request);
      if(actual.images.some(i=>i.selected)||JSON.stringify(actual.images.map(({url,width,height})=>({url,width,height})))!==JSON.stringify(expected))throw Error('图片库内容、顺序或勾选状态变化');
      return actual;
    };
    assertDraftUnchanged(staged.before.draft,await inspectDraft(page,request,{allCopy:true}));
    await checkLibrary();
    record.remote=[];
    for(let i=0;i<staged.uploads.length;i++)record.remote.push(await verifyRemoteAsset(staged.uploads[i].url,staged.assets[i]));
    await checkLibrary();
    record.status='image_save_unknown';await ledger.write(record);
    await clickSaveUnchangedDraft(page,request,staged.before.draft);
    record.listRow=(await reopenSavedDraft(page,request)).text;
    record.reopened=await inspectDraft(page,request,{allCopy:true});
    assertDraftUnchanged(staged.before.draft,record.reopened);
    record.library=await checkLibrary();
    record.status='image_library_saved_reopened_verified';record.saved=true;
    record.verifiedAt=new Date().toISOString();await ledger.write(record);return record;
  }catch(error){
    record.error=error.message;
    if(record.status==='image_save_started')record.status='stopped_before_image_save';
    await ledger.write(record);throw error;
  }
}
