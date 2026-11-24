// The driver supplies authenticated API/rendering and durable state writes.
export async function automaticColour({job,input,source,manualMask,api,render,persist}){
 const step=async(key,kind,inputs)=>{
  job.toolSteps=job.toolSteps||{};let saved=job.toolSteps[key];const signature=JSON.stringify({kind,inputs});
  if(saved&&saved.signature!==signature)throw Error('自动处理阶段输入改变，请创建新版本');
  if(!saved){saved=job.toolSteps[key]={requestId:crypto.randomUUID(),signature,kind,inputs};await persist();}
  if(!saved.taskId){const result=await api('/api/image-tools/start',{...inputs,productId:input.productId,kind,requestId:saved.requestId});saved.taskId=result.task.id;saved.task=result.task;await persist();}
  else saved.task=(await api('/api/image-tools/task?id='+encodeURIComponent(saved.taskId))).task;
  if(saved.task.status==='failed'&&saved.task.upgradeAllowed){const prior=saved.taskId;const result=await api('/api/image-tools/retry',{productId:input.productId,taskId:prior});saved.priorTaskIds=[...(saved.priorTaskIds||[]),prior];saved.taskId=result.task.id;saved.task=result.task;await persist();}
  const deadline=Date.now()+1800000;
  while(!['completed','failed','interrupted'].includes(saved.task?.status)){
   saved.task=(await api('/api/image-tools/task?id='+encodeURIComponent(saved.taskId))).task;await persist();
   if(Date.now()>deadline)throw Error('自动处理仍在后台；原意图已保存，继续查询同一输出目录');
   if(!['completed','failed','interrupted'].includes(saved.task.status))await new Promise(r=>setTimeout(r,3000));
  }
  if(saved.task.status!=='completed')throw Error(saved.task.error||'自动处理未通过，已保存原诊断，不重发未知模型调用');
  return {id:saved.taskId,...saved.task.result};
 };
 if(!job.normalized){job.normalized=await api('/api/image-templates/prepare-source',{productId:input.productId,source});await persist();}
 const normalized=job.normalized.source.url;
 let target=input.target,reference;
 if(job.uploads?.targetReference){
  if(!job.normalizedTarget){job.normalizedTarget=await api('/api/image-templates/prepare-source',{productId:input.productId,source:job.uploads.targetReference.url});await persist();}
  reference=job.normalizedTarget.source.url;
  job.targetReferenceSample=await step('target-reference-sample','reference_sample',{source:reference,role:'target_colour_reference'});await persist();
  target=job.targetReferenceSample.target;
 }
 if(!target)throw Error('需要真实同款目标参考图或实测目标RGB');
 let selection=manualMask?null:await step('source-selection','selection',{source:normalized});
 let mask=manualMask||selection.mask.url;
 job.selections=job.selections||[];job.colourAttempts=job.colourAttempts||[];
 let final;
 for(let attempt=0;attempt<2;attempt++){
  const record=job.colourAttempts[attempt]||{number:attempt+1,mask,selectionTaskId:selection?.id};
  job.colourAttempts[attempt]=record;job.selection=selection?{...selection,toolTaskId:selection.id}:undefined;await persist();
  if(!record.recipe){record.recipe=await api('/api/image-templates/colour-recipe',{productId:input.productId,source:normalized,mask,target});await persist();}
  const base=input.matchTargetSample===false?{'2':{sigma:0},'3':{sigma:0}}:record.recipe.settings;
  let settings=Object.fromEntries([...new Set([...Object.keys(base),...Object.keys(input.colourSettings||{})])].map(k=>[k,{...base[k],...input.colourSettings?.[k]}]));
  if(!record.initial){record.initial=await render({source:normalized,mask,target,settings});await persist();}
  let rendered=record.initial;
  if(input.matchTargetSample!==false){
   if(!record.feedback){record.feedback=await api('/api/image-templates/colour-recipe',{productId:input.productId,source:normalized,mask,target,renderedImage:rendered.renderedImage,settings});await persist();}
   if(record.feedback.audit.applied){
    settings=record.feedback.settings;
    if(!record.corrected){record.corrected=await render({source:normalized,mask,target,settings});await persist();}
    rendered=record.corrected;
   }
  }
  const quality=await step('colour-check-'+attempt,'colour_check',{source:normalized,mask,renderedImage:rendered.renderedImage,target,...(reference?{reference}:{}),...(selection?{selectionTaskId:selection.id}:{})});
  record.quality=quality;await persist();
  final={references:[normalized],mask,target,renderedImage:rendered.renderedImage,
   shaderReceipt:{...rendered.shaderReceipt,skuCalibration:record.recipe.audit,skuFeedback:record.feedback?.audit},
   qualityCheckId:quality.id,selectionTaskId:selection?.id,referencePhoto:reference};
  if(quality.passed||attempt===1||manualMask||quality.nextAction!=='selection')break;
  job.selections.push(selection);selection=await step('source-selection-correction','selection',{source:normalized,force:true,feedback:{qualityCheckId:quality.id,previousSelectionTask:selection.id}});
  mask=selection.mask.url;await persist();
 }
 const history=[...job.selections,job.selection].filter(Boolean),hashes=history.map(s=>s.receipt?.maskPixelSha256);
 const local=job.selection?.receipt?.localGrounding;
 const maskCorrections=manualMask?0:hashes.every(Boolean)?hashes.filter((hash,i)=>i>0&&hash!==hashes[i-1]).length:null;
 const evidenceClarifications=local?.auditOnly===true?1:0,passed=job.colourAttempts.at(-1).quality.passed;
 job.automaticQuality={passed,manualSelectionProvided:!!manualMask,outputAttempts:job.colourAttempts.length,
  maskCorrections,evidenceClarifications,maskChangedPixels:local?.maskChangedPixels??null,
  passedFirstAttempt:passed&&job.colourAttempts.length===1,
  passedAfterPixelCorrection:passed&&maskCorrections>0,
  passedAfterEvidenceClarification:passed&&evidenceClarifications>0&&maskCorrections===0};await persist();
 return final;
}
