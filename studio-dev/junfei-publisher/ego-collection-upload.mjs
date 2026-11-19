import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {verifyRemoteAsset} from './ego-draft-images.mjs';

export function managedUploadKey(generated,uid,asset){
 const prefix=String(generated).slice(0,String(generated).lastIndexOf('/')+1);
 if(!new RegExp('^u/'+String(uid).replace(/[^0-9]/g,'')+'/[0-9]{2}/[0-9]{2}/$').test(prefix)||!/^\d+$/.test(String(uid))||!/^[a-f0-9]{64}$/.test(asset.sha256))throw Error('上传目录或本地图片身份不符');
 // Keep stable content-addressed names close to the native uploader's length.
 return prefix+'s_'+asset.sha256.slice(0,32)+(asset.mime==='image/jpeg'?'.jpg':'.png');
}

export async function stageFinishedUploads(page,input,record,persist){
 record.uploads??={};const urls={};
 // Old successful receipts are adopted by hash, not by a product-specific file.
 for(const i of record.imageChecks||[])if(i.remote?.sha256===i.sha256&&!record.uploads[i.sha256])record.uploads[i.sha256]={url:i.url,status:'verified',remote:i.remote};
 let formOpen=false;
 for(const asset of input.assets){
  if(crypto.createHash('sha256').update(await fs.readFile(asset.path)).digest('hex')!==asset.sha256)throw Error('本地成品文件内容发生变化');
  let prior=record.uploads[asset.sha256];
  const compact=prior?.url?.includes('/studio_')&&prior.url.length>120;
  if(prior?.url){
   const head=await fetch(prior.url,{method:'HEAD',redirect:'error',signal:AbortSignal.timeout(15000)});
   if(head.status===200){
    prior.remote=await verifyRemoteAsset(prior.url,asset);prior.status='verified';await persist();
    if(!compact){urls[asset.sha256]=prior.url;continue;}
    ((record.mediaRevisions??={})[asset.sha256]??=[]).push({url:prior.url,remote:prior.remote,reason:'native_length_object_key'});await persist();
   }else if(head.status!==404)throw Error('原图片状态不明，保留检查点，不新增上传');
  }
  if(!formOpen){await page.goto('https://www.junfeikuajing.com/#/product/add');await page.waitForSelector('input[placeholder="请输入品牌名"]',{state:'visible'});formOpen=true;}
  record.phase='上传成品图片 '+(Object.keys(urls).length+1)+'/'+input.assets.length;await persist();
  const filename=path.basename(asset.path);
  await page.evaluate(({filename,uid,asset,previousUrl,keyFunction})=>{
   if(window.__studioUpload)throw Error('已有图片上传正在处理');
   const keyFor=(0,eval)('('+keyFunction+')'),open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,targets=new WeakMap();
   const s={open,send,pending:null,result:null,error:null,released:false,feedback:[],fileInput:null};window.__studioUpload=s;
   s.onInput=event=>{const input=event.target;if(input?.matches?.('input[type="file"].el-upload__input'))s.fileInput=[...input.files].map(file=>({name:file.name,size:file.size,type:file.type}));};
   document.addEventListener('change',s.onInput,true);
   s.observer=new MutationObserver(()=>{
    for(const el of document.querySelectorAll('.el-message__content,.el-notification__content')){
     const label=el.textContent?.trim();if(label&&!s.feedback.includes(label)&&s.feedback.length<10)s.feedback.push(label.slice(0,240));
    }
   });
   s.observer.observe(document.body,{childList:true,subtree:true});
   XMLHttpRequest.prototype.open=function(m,u,...r){const url=new URL(u,location.href);targets.set(this,String(m).toUpperCase()==='POST'&&/^junfeikuajing\.oss-[a-z0-9-]+\.aliyuncs\.com$/.test(url.hostname)?url.origin:null);
    if(url.origin==='https://app.junfeikuajing.com'&&url.pathname==='/api/common/upload-get-sign')this.addEventListener('loadend',()=>{
     if(this.status===401||this.status===403){
      let quota=false;try{quota=/容量超限|图片空间不足/.test(String(JSON.parse(this.responseText)?.message??''));}catch{}
      s.error=quota?'ERP图片空间容量超限，尚未传输图片；空间恢复后沿原任务继续':'ERP图片上传签名请求返回 HTTP '+this.status+'，未取得上传授权';
     }
    },{once:true});
    return open.call(this,m,u,...r);
   };
   XMLHttpRequest.prototype.send=function(body){const origin=targets.get(this);if(!origin)return send.call(this,body);
    try{
     if(!(body instanceof FormData)||body.get('file')?.name!==filename||s.pending)throw Error('非本次图片或重复上传');
     const key=keyFor(body.get('key'),uid,asset),url=origin+'/'+key;
     if(previousUrl&&previousUrl.includes('/studio_')&&url!==previousUrl)throw Error('旧图片跨上传目录失效，不能改变已有提交的图片地址');
     body.set('key',key);body.set('name',key.split('/').pop());
     const xhr=this;s.pending={url,key};
     // Signed fields stay inside the normal uploader and are never inspected.
     s.release=()=>{if(s.released)throw Error('禁止重复发送上传');s.released=true;xhr.addEventListener('loadend',()=>{s.result={status:xhr.status};},{once:true});return send.call(xhr,body);};
    }catch(e){s.error=e.message;throw e;}
   };
  },{filename,uid:input.destination.erpUserId,asset:{sha256:asset.sha256,mime:asset.mime},previousUrl:compact?null:prior?.url,keyFunction:managedUploadKey.toString()});
  try{
   await page.setInputFiles('input[type="file"].el-upload__input',[asset.path]);
   try{await page.waitForFunction(()=>window.__studioUpload?.pending||window.__studioUpload?.error,undefined,{timeout:20000});}
   catch(error){
    const observation=await page.evaluate(()=>({fileInput:window.__studioUpload?.fileInput,feedback:window.__studioUpload?.feedback}))
     .catch(()=>({fileInput:null,feedback:[]}));
    record.uploadPreflight={sha256:asset.sha256,observedAt:new Date().toISOString(),...observation};await persist();
    if(observation.feedback?.length)throw Error('ERP图片传输前置未通过：'+observation.feedback.join('、'));
    throw error;
   }
   const plan=await page.evaluate(()=>({pending:window.__studioUpload.pending,error:window.__studioUpload.error}));if(plan.error)throw Error(plan.error);
   const existing=await fetch(plan.pending.url,{method:'HEAD',redirect:'error',signal:AbortSignal.timeout(15000)});
   if(existing.status===200)await verifyRemoteAsset(plan.pending.url,asset);
   else if(existing.status!==404)throw Error('确定性图片对象状态不明，未覆盖');
   // Durable URL and source hash precede the actual upload. A crash can be
   // reconciled with HEAD + SHA; retrying uses the same content-addressed key.
   prior={url:plan.pending.url,key:plan.pending.key,status:'upload_unknown',sha256:asset.sha256};record.uploads[asset.sha256]=prior;await persist();
   (record.uploadAttempts??=[]).push({sha256:asset.sha256,url:prior.url,startedAt:new Date().toISOString()});await persist();
   await page.evaluate(()=>window.__studioUpload.release());
   await page.waitForFunction(()=>window.__studioUpload?.result,undefined,{timeout:45000});
   const result=await page.evaluate(()=>window.__studioUpload.result);prior.response=result;await persist();if(result.status!==200)throw Error('ERP图片上传失败，已保留对象地址');
   prior.remote=await verifyRemoteAsset(prior.url,asset);prior.status='verified';urls[asset.sha256]=prior.url;await persist();
  }finally{await page.evaluate(()=>{const s=window.__studioUpload;if(s){s.observer.disconnect();document.removeEventListener('change',s.onInput,true);XMLHttpRequest.prototype.open=s.open;XMLHttpRequest.prototype.send=s.send;delete window.__studioUpload;}});}
 }
 return urls;
}
