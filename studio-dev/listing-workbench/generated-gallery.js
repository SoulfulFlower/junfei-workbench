// Explicit export selection for completed jobs; does not grant image approval.
const renderBeforeGeneratedGallery=render;
render=function(){
 renderBeforeGeneratedGallery();
 if(view==='images'||(view==='listing'&&listingWorkspaceStep==='delivery'))mountGeneratedGallery();
};
async function mountGeneratedGallery(){
 const p=product(),accountId=signedUser?.id;
 const parent=document.querySelector('.wb-main')||document.getElementById('content');
 if(!p||!parent||!accountId)return;
 const panel=document.createElement('section');panel.className='panel box';panel.id='generatedGalleryExport';
 panel.innerHTML='<h2>生成图片导出顺序</h2><p>选择已完成任务的图片，第一张为主图。保存选择不会标为审核通过，也不会重新生图。未选择时沿用视觉套图。</p><p role="status">正在读取生成记录…</p>';
 parent.append(panel);
 try{
  const [data,studio]=await Promise.all([imageApi('jobs'),fetch('/api/studio/view?productId='+encodeURIComponent(p.id)).then(r=>{if(!r.ok)throw Error('读取视觉方案失败');return r.json()})]);
  if(!panel.isConnected||signedUser?.id!==accountId||product()?.id!==p.id)return;
  const rejected=data.jobs.filter(j=>j.productId===p.id&&j.providerRejection);
  if(rejected.length){
   const history=document.createElement('details'),summary=document.createElement('summary');
   summary.textContent='历史请求被服务商拒绝 · '+rejected.length+' 条（未重发）';history.append(summary);
   const explanation=document.createElement('p');explanation.textContent='这些原请求已收到明确拒绝，保留原始记录，不表示当前图片仍在生成。费用结算仍保留原服务商对账状态。';history.append(explanation);
   for(const j of rejected){const line=document.createElement('p');line.textContent=j.slot+' · '+j.providerRejection.label+' · 错误记录 '+(j.providerRejection.diagnosticId||j.id);history.append(line)}
   panel.prepend(history);
  }
  const unresolved=data.jobs.filter(j=>j.productId===p.id&&['submitting','submission_unknown'].includes(j.status)&&!j.providerRejection);
  if(unresolved.length){
   const notes=document.createElement('section');notes.id='imageSubmissionDiagnostics';notes.className='notice';
   const heading=document.createElement('h3');heading.textContent='生图提交待核对';notes.append(heading);
   const explanation=document.createElement('p');explanation.textContent='以下请求尚未拿到可确认的结果，请先核对原请求。页面不会自动重提，也不表示图片仍在生成。';notes.append(explanation);
   for(const job of unresolved){
    const item=document.createElement('details'),summary=document.createElement('summary'),body=document.createElement('p');
    summary.textContent=job.slot+' · 提交待核对';item.open=true;item.append(summary);
    const error=job.proxyDiagnostic;
    body.textContent=error?`${error.provider} HTTP ${error.httpStatus}：${error.message}\n错误记录：${error.id}\n提交记录：${job.id}`:`${job.error||'服务商结果未确认'}\n提交记录：${job.id}`;
    body.style.whiteSpace='pre-wrap';body.style.overflowWrap='anywhere';item.append(body);notes.append(item);
   }
   panel.prepend(notes);
  }
  const candidates=data.jobs.filter(j=>j.productId===p.id&&j.status==='completed').flatMap(j=>(j.images||[]).map((url,index)=>({jobId:j.id,imageIndex:index,url,label:j.slot+' · '+j.id.slice(-10)})));
  const saved=p.generatedGallerySelection;
  let chosen=(saved?.items||[]).map(x=>({...x}));
  const form=document.createElement('div'),status=panel.querySelector('[role=status]');
  const controls=document.createElement('div');controls.className='actions';
  const add=document.createElement('button');add.className='btn';add.textContent='增加图位';
  const save=document.createElement('button');save.className='btn';save.textContent='保存导出顺序';
  const restore=document.createElement('button');restore.className='btn';restore.textContent='改用视觉套图导出';
  controls.append(add,save,restore);panel.append(form,controls);
  function draw(){
   form.replaceChildren();
   chosen.forEach((item,i)=>{
    const row=document.createElement('div');row.className='actions';row.style.margin='12px 0';
    const label=document.createElement('label');label.textContent=(i===0?'主图':'辅图'+i)+' ';
    const select=document.createElement('select');select.setAttribute('aria-label','导出图位'+(i+1));select.append(new Option('请选择图片',''));
    candidates.forEach((c,n)=>select.append(new Option(c.label,String(n))));
    const n=candidates.findIndex(c=>c.jobId===item.jobId&&c.imageIndex===item.imageIndex);select.value=n<0?'':String(n);
    const preview=document.createElement('img');preview.style.cssText='width:100px;height:100px;object-fit:contain';preview.alt='导出候选图'+(i+1);if(n>=0)preview.src=candidates[n].url;else preview.hidden=true;
    select.onchange=()=>{const c=candidates[Number(select.value)];chosen[i]=select.value===''?{}:{jobId:c.jobId,imageIndex:c.imageIndex};draw()};
    const remove=document.createElement('button');remove.className='btn';remove.textContent='移除';remove.onclick=()=>{chosen.splice(i,1);draw()};
    label.append(select);row.append(label,preview,remove);form.append(row);
   });
  }
  add.onclick=()=>{if(chosen.length>=20)return;chosen.push({});draw()};
  async function store(value){
   if(signedUser?.id!==accountId||product()?.id!==p.id)throw Error('账号或产品已变化，请刷新');
   if(value)p.generatedGallerySelection=value;else delete p.generatedGallerySelection;
   persist();await flushWorkspace();
  }
  save.onclick=async()=>{
   if(!chosen.length||chosen.some(i=>!i.jobId))return toast('请为每个图位选择已完成图片');
   if(new Set(chosen.map(i=>i.jobId+':'+i.imageIndex)).size!==chosen.length)return toast('同一图片不能重复占用图位');
   save.disabled=true;
   try{await store({version:1,sourceStudioProjectId:studio.sets?.gallery?._projectId??null,items:chosen,updatedAt:new Date().toISOString()});status.textContent='已保存 '+chosen.length+' 张导出图片顺序；仍需审核。';}
   catch(e){status.textContent=e.message}finally{save.disabled=false}
  };
  restore.onclick=async()=>{try{await store(null);chosen=[];draw();status.textContent='已改用当前视觉套图导出。'}catch(e){status.textContent=e.message}};
  status.textContent=saved?'已保存 '+chosen.length+' 张导出候选，仍需审核。':'当前沿用视觉套图。可在这里指定已完成任务图片。';
  draw();
 }catch(e){if(panel.isConnected)panel.querySelector('[role=status]').textContent=e.message}
}
