// Product-library upload transport. This module never clicks product Save or
// publishes. Uploads create server objects even when the form is later cancelled.
import fs from 'node:fs/promises';
import {inspectLibraryForm,validLibraryVariantSku} from './ego-library-draft.mjs';
import {validateAssets,verifyRemoteAsset} from './ego-draft-images.mjs';

const ROOT='[data-amazon-library-active="true"]';

// A product gallery contains images for every colour; the nine-image limit
// belongs to each variant, not the shared gallery. Keep the single-variant
// validator unchanged and validate each gallery file with the same rules.
export async function validateLibraryAssets(assets){
  if(!Array.isArray(assets)||!assets.length||assets.length>24*9)throw Error('产品图库需明确1至216张图片');
  const hashes=new Set();
  for(const asset of assets){
    await validateAssets([asset]);
    if(hashes.has(asset.sha256))throw Error('产品图库图片重复，未重复上传');
    hashes.add(asset.sha256);
    if(asset.purpose==='calibration_only'&&assets.length!==1)throw Error('校准图不能混入商品套图');
  }
  return assets;
}

export async function inspectLibraryImages(page){
  return page.evaluate(()=>{
    const d=document.querySelector('[data-amazon-library-active="true"]');
    if(!d||d.getBoundingClientRect().width<=0)throw Error('产品库活动表单不存在');
    const files=[...d.querySelectorAll('input[type=file]')];
    if(files.length!==1||files[0].accept!=='.jpg, .jpeg, .png'||!files[0].multiple)throw Error('产品库上传控件结构变化');
    const images=[...d.querySelectorAll('.img-info ul > li img')].map(img=>{
      if(!img.complete||!img.naturalWidth||!img.naturalHeight)throw Error('产品库图片尚未加载');
      const url=img.getAttribute('src');let parsed;try{parsed=new URL(url);}catch{}
      if(!parsed||parsed.protocol!=='https:'||parsed.username||parsed.password||parsed.port||!/^junfeikuajing\.oss-[a-z0-9-]+\.aliyuncs\.com$/.test(parsed.hostname))throw Error('产品库图片来源异常');
      return {url,width:img.naturalWidth,height:img.naturalHeight};
    });
    if(new Set(images.map(i=>i.url)).size!==images.length)throw Error('产品库图片重复');
    return {images,uploadSelector:'[data-amazon-library-active="true"] input[type=file]'};
  });
}

function assertFields(before,after){
  for(const key of ['url','form','shipping','variants','variantSkuControlCount'])if(JSON.stringify(before[key])!==JSON.stringify(after[key]))throw Error('上传期间产品库字段变化: '+key);
}

export async function stageLibraryImages(page,request,assets,ledger){
  if(!request||!Number.isSafeInteger(request.accountId)||request.accountId<1||typeof request.productId!=='string'||!request.productId.trim()||!/^[-A-Za-z0-9_]{1,40}$/.test(request.sku||''))throw Error('缺少明确账号、产品及父SKU');
  await validateLibraryAssets(assets);
  for(const asset of assets)if((await fs.stat(asset.path)).size>=5*1024*1024)throw Error('产品库单图必须小于5MB');
  const before=await inspectLibraryForm(page);
  if(before.form.sku!==request.sku)throw Error('产品库父SKU不匹配');
  const library=await inspectLibraryImages(page);
  if(library.images.length||before.imageCount)throw Error('只接受空图库，已有图片需核对原操作，不重传');
  const record={...request,assets:structuredClone(assets),before,status:'library_images_prepared',uploads:[],saved:false,published:false,createdAt:new Date().toISOString()};
  await ledger.create(record);
  try{
    for(const asset of assets){
      assertFields(before,await inspectLibraryForm(page));
      const current=await inspectLibraryImages(page),expected=record.uploads.map(i=>i.url);
      if(JSON.stringify(current.images.map(i=>i.url))!==JSON.stringify(expected))throw Error('上传前产品图库变化，停止覆盖');
      await validateAssets([asset]);
      record.status='library_image_upload_unknown';record.pendingAsset=asset.sha256;await ledger.write(record);
      await page.setInputFiles(current.uploadSelector,[asset.path]);
      await page.waitForFunction(count=>{
        const d=document.querySelector('[data-amazon-library-active="true"]');
        const images=[...d.querySelectorAll('.img-info ul > li img')];
        return images.length===count+1&&images.every(i=>i.complete&&i.naturalWidth>0);
      },expected.length,{timeout:20000});
      const after=await inspectLibraryImages(page),uploaded=after.images.at(-1);
      if(after.images.length!==expected.length+1||JSON.stringify(after.images.slice(0,-1).map(i=>i.url))!==JSON.stringify(expected)||expected.includes(uploaded.url))throw Error('上传后图库数量或顺序异常');
      record.observedUpload={...uploaded,sourceSha256:asset.sha256};await ledger.write(record);
      if(uploaded.width!==asset.width||uploaded.height!==asset.height)throw Error('上传后图片尺寸与源文件不符');
      const remote=await verifyRemoteAsset(uploaded.url,asset);
      assertFields(before,await inspectLibraryForm(page));
      // Explicit null also clears fields in receipt stores that merge updates.
      record.uploads.push({...uploaded,sha256:asset.sha256,remote});record.pendingAsset=null;record.observedUpload=null;
      record.status='library_images_staged_not_saved';await ledger.write(record);
    }
    record.stagedAt=new Date().toISOString();await ledger.write(record);return record;
  }catch(error){record.error=error.message;await ledger.write(record);throw error;}
}

export function validateLibraryBinding(request,upload,sku,indices){
  if(!upload||upload.status!=='library_images_staged_not_saved'||upload.pendingAsset||upload.observedUpload||
     ['accountId','productId','sku'].some(k=>upload[k]!==request?.[k])||upload.saved!==false||upload.published!==false)throw Error('缺少同账号产品已核对的未保存上传回执');
  if(!validLibraryVariantSku(sku)||!Array.isArray(indices)||!indices.length||indices.length>9||new Set(indices).size!==indices.length)throw Error('变体SKU或图片顺序无效');
  if(!Array.isArray(upload.assets)||!Array.isArray(upload.uploads)||upload.assets.length!==upload.uploads.length)throw Error('上传结果不完整');
  for(let n=0;n<upload.assets.length;n++){
    const a=upload.assets[n],u=upload.uploads[n];
    if(u.sha256!==a.sha256||u.remote?.sha256!==a.sha256||!(u.remote.bytes>0)||u.width!==a.width||u.height!==a.height)throw Error('上传图片核对证据不匹配');
  }
  if(indices.some(i=>!Number.isSafeInteger(i)||i<0||i>=upload.uploads.length))throw Error('变体图片序号无效');
  return indices.map(i=>upload.uploads[i].url);
}

export async function inspectLibraryPicker(page){
  // BaseImg sets thumbnail src asynchronously after the dialog opens or a new
  // selection is added. Hidden popover previews must not count as gallery cards.
  await page.waitForFunction(()=>{
    const ds=[...document.querySelectorAll('[role="dialog"][aria-label="选择图片"]')].filter(d=>d.getBoundingClientRect().width>0);
    if(ds.length!==1)return false;
    const thumbs=[...ds[0].querySelectorAll('th .el-popover__reference img')];
    return thumbs.length>0&&thumbs.every(i=>i.getAttribute('src')?.startsWith('https://')&&i.complete&&i.naturalWidth>0);
  },undefined,{timeout:10000});
  return page.evaluate(()=>{
    const ds=[...document.querySelectorAll('[role="dialog"][aria-label="选择图片"]')].filter(d=>d.getBoundingClientRect().width>0);
    if(ds.length!==1)throw Error('选择图片对话框不唯一');const d=ds[0];
    document.querySelectorAll('[data-amazon-variant-picker]').forEach(e=>e.removeAttribute('data-amazon-variant-picker'));d.setAttribute('data-amazon-variant-picker','true');
    const groups=[...d.querySelectorAll('.el-descriptions')];
    const group=name=>{const g=groups.filter(e=>e.querySelector('.el-descriptions__title')?.innerText.trim()===name);if(g.length!==1)throw Error('图片选择表结构变化');return g[0];};
    const urls=g=>[...g.querySelectorAll('th .el-popover__reference img')].map(img=>{
      const u=new URL(img.getAttribute('src'));if(u.protocol!=='https:'||u.username||u.password||u.port||!/^junfeikuajing\.oss-[a-z0-9-]+\.aliyuncs\.com$/.test(u.hostname)||[...u.searchParams.keys()].some(k=>k!=='x-oss-process'))throw Error('图片选择来源异常');
      u.search='';return u.href;
    });
    const gallery=group('图库'),selected=group('变体图片'),available=urls(gallery);
    const plus=[...gallery.querySelectorAll('td .el-icon-plus')];
    if(plus.length!==available.length)throw Error('图库添加按钮数量异常');
    plus.forEach((e,i)=>e.setAttribute('data-amazon-image-add',String(i)));
    return {available,selected:urls(selected)};
  });
}

async function variantImageTarget(page,sku){
  return page.evaluate(sku=>{
    const d=document.querySelector('[data-amazon-library-active="true"]');
    const rows=[...d.querySelectorAll('.el-table__body tr')].filter(row=>{
      const inputs=[...row.querySelectorAll('input')].filter(e=>e.type!=='checkbox');return inputs.length===4&&inputs[0].value===sku;
    });
    if(rows.length!==1)throw Error('变体SKU行不唯一');const target=rows[0].querySelector('.main_image');if(!target)throw Error('变体配图按钮缺失');
    d.querySelectorAll('[data-amazon-variant-image-target]').forEach(e=>e.removeAttribute('data-amazon-variant-image-target'));target.setAttribute('data-amazon-variant-image-target','true');
    // Reveal the exact row inside both the variant table and the product dialog.
    target.scrollIntoView({block:'center',inline:'nearest'});
    return '[data-amazon-library-active="true"] [data-amazon-variant-image-target="true"]';
  },sku);
}

// Read the complete variant image list, since the parent table renders only
// its first image. Closing the picker cancels; this never confirms or saves.
export async function verifyLibraryVariantImages(page,sku,desired,available){
  await page.click(await variantImageTarget(page,sku),{label:'读取变体完整配图顺序'});
  const picker=await inspectLibraryPicker(page);
  if(JSON.stringify(picker.selected)!==JSON.stringify(desired)||JSON.stringify(picker.available)!==JSON.stringify(available))throw Error('变体完整图片或图库顺序不符');
  await page.click('[data-amazon-variant-picker="true"] .el-dialog__footer button:has-text("取 消")',{label:'关闭配图核对窗口'});
  await page.waitForFunction(()=>![...document.querySelectorAll('[role="dialog"][aria-label="选择图片"]')].some(e=>e.getBoundingClientRect().width>0),undefined,{timeout:5000});
  return picker;
}

export async function stageLibraryVariantImages(page,request,upload,sku,indices,ledger){
  const desired=validateLibraryBinding(request,upload,sku,indices);
  await validateLibraryAssets(upload.assets);
  const before=await inspectLibraryForm(page),gallery=await inspectLibraryImages(page);
  if(before.form.sku!==request.sku||JSON.stringify(gallery.images.map(i=>i.url))!==JSON.stringify(upload.uploads.map(i=>i.url)))throw Error('配图前父SKU或图库已变化');
  const variants=before.variants.filter(v=>v.sku===sku);
  if(variants.length!==1||variants[0].images.length)throw Error('仅接受明确SKU的空变体图库');
  const record={...request,variantSku:sku,indices,desired,before,status:'library_variant_binding_unknown',phase:'before_open',error:null,saved:false,published:false,createdAt:new Date().toISOString()};
  await ledger.create(record);
  try{
    await page.click(await variantImageTarget(page,sku),{label:'打开指定变体图库'});
    record.phase='picker_opened';await ledger.write(record);
    let picker=await inspectLibraryPicker(page);
    if(picker.selected.length||JSON.stringify(picker.available)!==JSON.stringify(upload.uploads.map(i=>i.url)))throw Error('变体选择器已有图片或图库不符');
    for(const i of indices)await page.click('[data-amazon-variant-picker="true"] [data-amazon-image-add="'+i+'"]',{label:'按顺序加入变体图片'});
    picker=await inspectLibraryPicker(page);
    if(JSON.stringify(picker.selected)!==JSON.stringify(desired))throw Error('变体所选图片顺序不符');
    record.phase='selection_verified_before_local_confirm';await ledger.write(record);
    // This confirms only the local picker, never the product-detail Save button.
    await page.click('[data-amazon-variant-picker="true"] .el-dialog__footer button:has-text("保存")',{label:'确认表单内变体配图'});
    await page.waitForFunction(()=>![...document.querySelectorAll('[role="dialog"][aria-label="选择图片"]')].some(e=>e.getBoundingClientRect().width>0),undefined,{timeout:5000});
    // The parent renders only the first image. Reopen to verify the entire list.
    await page.click(await variantImageTarget(page,sku),{label:'重开核对完整配图顺序'});
    picker=await inspectLibraryPicker(page);
    if(JSON.stringify(picker.selected)!==JSON.stringify(desired)||JSON.stringify(picker.available)!==JSON.stringify(upload.uploads.map(i=>i.url)))throw Error('重开后变体图片顺序不符');
    await page.click('[data-amazon-variant-picker="true"] .el-dialog__footer button:has-text("取 消")',{label:'关闭已核对配图窗口'});
    await page.waitForFunction(()=>![...document.querySelectorAll('[role="dialog"][aria-label="选择图片"]')].some(e=>e.getBoundingClientRect().width>0),undefined,{timeout:5000});
    const after=await inspectLibraryForm(page);
    for(const key of ['url','form','shipping','variantSkuControlCount'])if(JSON.stringify(before[key])!==JSON.stringify(after[key]))throw Error('配图期间产品字段变化: '+key);
    const expected=before.variants.map(v=>v.sku===sku?{...v,images:[desired[0]]}:v);
    if(JSON.stringify(after.variants)!==JSON.stringify(expected))throw Error('变体首图或其他变体字段变化');
    record.status='library_variant_images_staged_reopened_verified';record.boundUrls=picker.selected;record.after=after;record.verifiedAt=new Date().toISOString();await ledger.write(record);return record;
  }catch(error){record.error=error.message;await ledger.write(record);throw error;}
}
