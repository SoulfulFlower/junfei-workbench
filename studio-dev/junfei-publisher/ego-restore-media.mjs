// Restore only this product's missing OSS objects with identical source bytes.
// The ERP's normal uploader supplies its own authentication and signed form.
// Keys, file names and HTTP results are observed; signing fields are untouched.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {verifyRemoteAsset} from './ego-draft-images.mjs';

export async function restoreMissingMedia(page,input,urls,file){
 const assets=input.assets.map(a=>({...a,url:urls[a.sha256]}));
 const journal={productId:input.productId,accountId:input.accountId,draftId:input.destination.draftId,status:'checking',objects:[],published:false};
 const persist=()=>fs.writeFile(file,JSON.stringify(journal,null,2));
 for(const a of assets){
  if(crypto.createHash('sha256').update(await fs.readFile(a.path)).digest('hex')!==a.sha256)throw Error('原文件内容变化');
  const u=new URL(a.url);if(u.origin!=='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com'||!/^\/u\/19335\/26\/11\/[a-f0-9]{32}\.png$/.test(u.pathname))throw Error('恢复对象超出本次产品上传范围');
 }
 let next=0;await Promise.all(Array.from({length:4},async()=>{while(next<assets.length){const a=assets[next++],r=await fetch(a.url,{method:'HEAD',redirect:'error',signal:AbortSignal.timeout(15000)});if(![200,404].includes(r.status))throw Error('图片状态不明，不覆盖');journal.objects.push({sha256:a.sha256,url:a.url,path:a.path,missing:r.status===404});}}));
 await persist();const missing=journal.objects.filter(a=>a.missing);
 if(!missing.length){journal.status='nothing_missing';await persist();return journal;}
 const form=Object.fromEntries(missing.map(a=>[path.basename(a.path),{key:new URL(a.url).pathname.slice(1),sha256:a.sha256}]));
 await page.evaluate(form=>{
  if(window.__restoreMedia)throw Error('已有图片恢复任务');
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap(),state={open,send,results:[],sent:new Set()};window.__restoreMedia=state;
  XMLHttpRequest.prototype.open=function(m,u,...r){targets.set(this,String(m).toUpperCase()==='POST'&&new URL(u,location.href).origin==='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com');return open.call(this,m,u,...r);};
  XMLHttpRequest.prototype.send=function(body){
   if(!targets.get(this))return send.call(this,body);
   if(!(body instanceof FormData))throw Error('图片恢复请求不是正常上传表单');
   const file=body.get('file'),match=form[file?.name];if(!match||state.sent.has(file.name))throw Error('禁止非本款或重复图片上传');
   const generated=body.get('key');if(typeof generated!=='string'||!generated.startsWith('u/19335/26/11/'))throw Error('上传目录与本账号不符');
   body.set('key',match.key);body.set('name',match.key.split('/').pop().replace(/\.png$/,''));state.sent.add(file.name);
   this.addEventListener('loadend',()=>{let filename;try{filename=JSON.parse(this.responseText).data?.filename;}catch{}state.results.push({sha256:match.sha256,status:this.status,filename});},{once:true});
   return send.call(this,body);
  };
 },form);
 journal.status='uploading_same_keys';await persist();
 try{
  await page.setInputFiles('input[type="file"].el-upload__input',missing.map(a=>a.path));
  await page.waitForFunction(count=>window.__restoreMedia?.results.length===count,missing.length,{timeout:55000});
  journal.uploads=await page.evaluate(()=>window.__restoreMedia.results);await persist();
  if(journal.uploads.some(r=>r.status!==200))throw Error('部分图片上传失败，保留逐图回执');
 }finally{await page.evaluate(()=>{const s=window.__restoreMedia;if(s){XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__restoreMedia;}});}
 next=0;await Promise.all(Array.from({length:4},async()=>{while(next<assets.length){const a=assets[next++],proof=await verifyRemoteAsset(a.url,a);const row=journal.objects.find(r=>r.sha256===a.sha256);row.remote=proof;}}));
 journal.status='all_original_bytes_restored';await persist();return journal;
}
