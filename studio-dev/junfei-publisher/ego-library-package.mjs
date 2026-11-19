// Compose the calibrated components into one durable operation. This prepares
// the local form only; product Save and store publication remain separate.
import fs from 'node:fs/promises';
import {validateLibraryRequest,stageLibraryDraft,inspectLibraryForm,saveStagedLibraryDraft,openNewLibraryForm} from './ego-library-draft.mjs';
import {stageLibraryImages,stageLibraryVariantImages,inspectLibraryImages,validateLibraryBinding,verifyLibraryVariantImages,validateLibraryAssets} from './ego-library-images.mjs';

export async function validateLibraryPackage(input){
  if(!input||Object.keys(input).some(k=>!['request','assets','bindings'].includes(k)))throw Error('产品库整包字段无效');
  validateLibraryRequest(input.request);
  if(!input.request.commerce)throw Error('产品库整包需要明确价格与变体');
  await validateLibraryAssets(input.assets);
  for(const a of input.assets){
    if(a.purpose!=='reviewed_product_image')throw Error('生产整包不能使用校准图片');
    if((await fs.stat(a.path)).size>=5*1024*1024)throw Error('产品库单图必须小于5MB');
  }
  const variants=input.request.commerce.variants;
  if(!Array.isArray(input.bindings)||input.bindings.length!==variants.length)throw Error('每个变体必须有明确配图');
  const seen=new Set();
  for(const b of input.bindings){
    if(!b||Object.keys(b).some(k=>!['sku','indices'].includes(k))||seen.has(b.sku)||!variants.some(v=>v.sku===b.sku)||
      !Array.isArray(b.indices)||!b.indices.length||b.indices.length>9||new Set(b.indices).size!==b.indices.length||
      b.indices.some(i=>!Number.isSafeInteger(i)||i<0||i>=input.assets.length))throw Error('变体配图映射无效');
    seen.add(b.sku);
  }
  return input;
}

export function assertLibraryPackageState(record,form,gallery){
  if(!['library_package_staging','library_package_staged_not_saved'].includes(record.status)||!record.copy||!record.upload||record.bindings.length!==record.input.bindings.length)throw Error('整包回执不完整');
  const {request,bindings}=record.input,base=record.copy.staged;
  const urls=record.upload.uploads.map(u=>u.url);
  if(JSON.stringify(gallery.images.map(i=>i.url))!==JSON.stringify(urls))throw Error('整包图库顺序变化');
  for(const key of ['url','form','shipping','variantSkuControlCount'])if(JSON.stringify(base[key])!==JSON.stringify(form[key]))throw Error('整包字段变化: '+key);
  const expected=base.variants.map(v=>{
    const b=bindings.find(b=>b.sku===v.sku),receipt=record.bindings.find(r=>r.variantSku===v.sku);
    const desired=validateLibraryBinding(request,record.upload,v.sku,b.indices);
    if(receipt?.status!=='library_variant_images_staged_reopened_verified'||receipt.saved!==false||receipt.published!==false||
      ['accountId','productId','sku'].some(k=>receipt[k]!==request[k])||JSON.stringify(receipt.boundUrls)!==JSON.stringify(desired))throw Error('整包变体回执不符');
    return {...v,images:[desired[0]]};
  });
  if(JSON.stringify(form.variants)!==JSON.stringify(expected)||form.imageCount!==urls.length+expected.length)throw Error('整包变体或图片数量变化');
}

export async function verifyLibraryPackageForSave(page,save,actual){
  const p=save.mediaPackage;
  if(!p||p.status!=='library_package_staged_not_saved'||p.saved!==false||p.published!==false||
    ['accountId','productId','sku'].some(k=>p[k]!==save[k])||
    JSON.stringify(p.input.request)!==JSON.stringify(save.request)||JSON.stringify(p.copy.before)!==JSON.stringify(save.before))throw Error('保存与整包身份或原始请求不符');
  await validateLibraryPackage(p.input);
  assertLibraryPackageState(p,actual,await inspectLibraryImages(page));
  const urls=p.upload.uploads.map(u=>u.url);
  for(const b of p.input.bindings)await verifyLibraryVariantImages(page,b.sku,validateLibraryBinding(p.input.request,p.upload,b.sku,b.indices),urls);
  // Catch edits made while the child dialogs were open.
  if(JSON.stringify(await inspectLibraryForm(page))!==JSON.stringify(actual))throw Error('读取完整配图期间表单变化');
}

export async function saveLibraryPackage(page,record,ledger){
  if(record.status!=='library_package_staged_not_saved'||record.save)throw Error('整包已提交或需先核对，不能重复保存');
  const save={...structuredClone(record.copy),mediaPackage:structuredClone(record)};
  record.status='library_package_save_unknown';record.save=save;
  // Durable aggregate intent precedes even the save preflight. A failure keeps
  // this operation non-replayable; reconciliation must inspect the original SKU.
  await ledger.write(record);
  try{
    await saveStagedLibraryDraft(page,save,{write:async value=>{record.save=structuredClone(value);await ledger.write(record);}});
    record.save=structuredClone(save);record.libraryId=save.libraryId;
    record.saved=true;record.status='library_package_saved_reopened_verified';
    record.verifiedAt=new Date().toISOString();await ledger.write(record);return record;
  }catch(error){record.error=error.message;await ledger.write(record);throw error;}
}

export async function stageLibraryPackage(page,input,ledger,{openNew=false}={}){
  // Freeze the operation's input before the first await. A renderer cannot swap
  // account, SKU or image order while files are being checked or uploaded.
  input=structuredClone(input);
  if(typeof openNew!=='boolean')throw Error('产品库打开模式无效');
  await validateLibraryPackage(input);
  const record={accountId:input.request.accountId,productId:input.request.productId,sku:input.request.sku,
    input,status:'library_package_staging',phase:'before_copy',bindings:[],saved:false,published:false,createdAt:new Date().toISOString()};
  // create must reject any existing operation, including uncertain attempts.
  await ledger.create(record);
  const child=key=>({
    create:async value=>{if(record[key])throw Error('整包子操作已存在，请先对账');record[key]=structuredClone(value);await ledger.write(record);},
    write:async value=>{record[key]=structuredClone(value);await ledger.write(record);}
  });
  try{
    // Persist the SKU replay barrier before opening a new ERP form.
    if(openNew)await openNewLibraryForm(page);
    await stageLibraryDraft(page,input.request,child('copy'));
    record.phase='before_upload';await ledger.write(record);
    await stageLibraryImages(page,input.request,input.assets,child('upload'));
    for(const b of input.bindings){
      record.phase='before_binding:'+b.sku;await ledger.write(record);
      const slot='bindingInProgress';
      await stageLibraryVariantImages(page,input.request,record.upload,b.sku,b.indices,child(slot));
      record.bindings.push(record[slot]);record[slot]=null;await ledger.write(record);
    }
    const final=await inspectLibraryForm(page),gallery=await inspectLibraryImages(page);
    assertLibraryPackageState(record,final,gallery);
    record.final=final;record.status='library_package_staged_not_saved';record.phase='verified';
    record.verifiedAt=new Date().toISOString();await ledger.write(record);return record;
  }catch(error){
    // Never replay this aggregate: even a failed upload may have created a
    // server object. Child receipts preserve the last durable side-effect intent.
    record.status='library_package_requires_reconciliation';record.error=error.message;await ledger.write(record);throw error;
  }
}
