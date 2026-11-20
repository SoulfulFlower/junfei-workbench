/* The preview and password are scoped to the exact publication request. */
window.confirmPublicationOperation = async function(accountId, action, request) {
 const headers = {'Content-Type':'application/json','X-Workspace-Account':String(accountId)};
 async function post(path, value) {
  const response = await fetch('/api/publication/'+path, {method:'POST', headers, body:JSON.stringify(value)});
  const result = await response.json();
  if(!response.ok)throw Error(result.error||'发布请求失败');
  return result;
 }
 const {preview}=await post('preview',{action,request});
 const dialog=document.createElement('dialog');
 const form=document.createElement('form');
 form.method='dialog';
 form.className='ds-panel ds-feedback';
 const title=document.createElement('h2');
 title.textContent=action==='start'?'确认美国发布并接续英国':'确认继续原发布任务';
 const summary=document.createElement('p');
 summary.textContent=[preview.productName||preview.productId,preview.sourceStore+' → '+preview.targetStore,
  preview.parentSku,preview.variantCount+' 个子 SKU',preview.draftId&&'草稿 '+preview.draftId,
  preview.id&&'原任务 '+preview.id,preview.phase].filter(Boolean).join(' · ');
 const label=document.createElement('label');
 label.className='field';
 label.textContent='当前工作台账号密码';
 const input=document.createElement('input');
 input.type='password';
 input.autocomplete='current-password';
 input.required=true;
 label.append(input);
 const actions=document.createElement('div');
 actions.className='ds-actions';
 const cancel=document.createElement('button');
 cancel.type='button';
 cancel.className='ds-button';
 cancel.textContent='取消';
 cancel.onclick=()=>dialog.close();
 const approve=document.createElement('button');
 approve.className='ds-button ds-button-primary';
 approve.textContent='确认执行';
 actions.append(cancel,approve);
 form.append(title,summary,label,actions);
 dialog.append(form);
 document.body.append(dialog);
 const password=await new Promise(resolve=>{
  form.onsubmit=event=>{event.preventDefault();dialog.close('approved');};
  dialog.onclose=()=>{resolve(dialog.returnValue==='approved'?input.value:null);input.value='';dialog.remove();};
  dialog.showModal();
 });
 return password===null?null:post(action,{...request,confirmationDigest:preview.digest,operatorPassword:password});
};
