// Colour page rendering and interaction. HTTP lives in colour-api.js.
let colourPollTimer=null;
function mountColourVariants(){
 clearTimeout(colourPollTimer);
 const host=document.getElementById('nativeVisualStudio');if(!host)return;
 const p=product(),panel=document.createElement('section');panel.className='panel box colour-variant-panel';panel.dataset.automaticVariantFlow='true';
 const fold=(label,className)=>{
  const details=document.createElement('details'),summary=document.createElement('summary');
  details.className=className;summary.textContent=label;details.append(summary);return details;
 };
 const master=fold('母版：读取中…','colour-master');
 const masterBody=document.createElement('div');master.append(masterBody);
 const readiness=document.createElement('p');readiness.className='sub colour-readiness';readiness.setAttribute('role','status');
 const fields=document.createElement('div');fields.className='colour-fields';
 const colorLabel=document.createElement('label');colorLabel.textContent='目标颜色';
 const color=document.createElement('select');color.setAttribute('aria-label','换色目标颜色');
 colorLabel.append(color);fields.append(colorLabel);
 const referenceCard=document.createElement('div');referenceCard.className='colour-reference';referenceCard.hidden=true;
 const preview=document.createElement('img');preview.alt='目标颜色参考图';
 const referenceBody=document.createElement('div');
 const referenceLabel=document.createElement('strong');referenceLabel.textContent='同色参考图';
 const source=document.createElement('p');source.className='sub';
 const referenceNotice=document.createElement('p');referenceNotice.className='sub';referenceNotice.setAttribute('role','status');
 const reinstateButton=document.createElement('button');reinstateButton.className='btn';reinstateButton.hidden=true;
 const changeReference=fold('更换参考图','colour-reference-choice');
 const reference=document.createElement('select');reference.setAttribute('aria-label','目标颜色真实素材');changeReference.append(reference);
 referenceBody.append(referenceLabel,source,referenceNotice,reinstateButton,changeReference);referenceCard.append(preview,referenceBody);
 const children=fold('查看关联明细','colour-children');children.hidden=true;
 const childList=document.createElement('ul'),childIssues=document.createElement('p');childIssues.className='sub';children.append(childList,childIssues);
 const batch=fold('批量换色','colour-batch');
 const advanced=fold('母版一键换色 · 自动读取变体主图颜色','colour-advanced');advanced.open=true;
 let refreshPixelSources;
 let groups=[],masterKey='',active=false;
 function updateControls(){
  const group=groups.find(row=>row.key===color.value);
  const ref=group?.references.find(item=>item.url===reference.value);
  button.disabled=!ColourViewRules.canGenerate(group,active,reference.value,masterKey);
  allButton.disabled=!ColourViewRules.canGenerateAll(groups,active,masterKey);
  referenceCard.hidden=!group;preview.hidden=!ref;
  if(ref)preview.src=ref.url;else preview.removeAttribute('src');
  source.replaceChildren();
  if(ref?.referenceType==='amazon_variant_main'){
   const link=document.createElement('a');link.href=ref.sourceUrl;link.target='_blank';link.rel='noopener noreferrer';
   link.textContent='Amazon 主图 · '+ref.sourceAsin;source.append(link);
  }else source.textContent=ref?(ref.url.startsWith('/uploads/')?'来源：已上传素材':'来源：已关联素材'):'待补同色参考图';
  referenceNotice.hidden=!group||group.ready;
  reinstateButton.hidden=group?.listingEligible!==false;
  reinstateButton.disabled=active;
  reinstateButton.textContent=group?.canReinstate?'核对后重新纳入制作':'补录货源核对资料';
  referenceNotice.textContent=group?.listingEligible===false?
   group.canReinstate?'已保存的货源和同色资料满足校验，可确认重新纳入；原排除记录保留。':
    '暂不能重新纳入：'+(group.reinstatementIssues||group.issues).join('；')+'。请补录实际货源选项、时间和来源证据。':
   group&&!group.ready?'暂不能换色：'+group.issues.join('；'):'';
  changeReference.hidden=(group?.references.length||0)<2;
  children.hidden=!group;
  if(group){
   children.querySelector('summary').textContent='查看关联明细 · '+group.children.length+' 个子体';
   childList.replaceChildren(...group.children.map(row=>{
    const li=document.createElement('li');li.textContent=[row.size||'待补尺码',row.asin&&'子 ASIN '+row.asin,row.sku?'SKU '+row.sku:'待补 SKU'].filter(Boolean).join(' · ');return li;
   }));
   childIssues.textContent=group.issues.length?'待核对：'+group.issues.join('；'):'';
  }
 }
 function updateReferences(previous=''){
  const group=groups.find(row=>row.key===color.value);
  const refs=(group?.references||[]).filter(ref=>ref.referenceType==='amazon_variant_main');
  reference.replaceChildren(new Option('选择该颜色的参考图',''),
    ...refs.map((ref,index)=>new Option(group.color+' · '+(ref.referenceType==='amazon_variant_main'?
      'Amazon 主图 '+ref.sourceAsin:'参考图 '+(index+1)),ref.url)));
  reference.value=refs.some(ref=>ref.url===previous)?previous:refs.find(r=>r.referenceType==='amazon_variant_main')?.url||refs[0]?.url||'';
  updateControls();
 }
 color.onchange=()=>{children.open=false;changeReference.open=false;updateReferences()};
 reference.onchange=updateControls;
 reinstateButton.onclick=async()=>{
  const group=groups.find(row=>row.key===color.value);if(!group||active)return;
  if(!group.canReinstate){editFacts();return}
  if(!confirm('已核对 '+group.color+' 的货源选项、同色参考图和 '+group.children.length+' 个子体，确认重新纳入制作？原排除记录将保留；本操作不生图、不上传。'))return;
  active=true;updateControls();
  try{await saveColourAssociation(p,'reinstate',group.key);toast('该颜色已重新纳入，原排除记录已保留');await refresh()}
  catch(error){toast(error.message)}finally{active=false;updateControls()}
 };
 const button=document.createElement('button');button.className='btn primary';button.textContent='一键制作当前色套图';
 const allButton=document.createElement('button');allButton.className='btn';allButton.textContent='一键制作全部变体颜色';batch.append(allButton);
 const localSettings=fold('颜色微调（可选）','colour-local-settings');
 localSettings.innerHTML+=`<p>默认自动读取变体主图中的衣料颜色，无需设置。需要时可在这里微调；后续图片质检仍可能消耗模型额度。</p><div class="actions" style="flex-wrap:wrap;gap:12px"><label>目标色 <input type="color" value="#808080" aria-label="本地套图目标色"></label><label>曝光 <input type="number" min="-15" max="15" step=".5" value="0" aria-label="本地套图曝光"></label><label>纹理 <input type="number" min="0" max="2" step=".05" value="1" aria-label="本地套图纹理"></label><label>图案 <select aria-label="本地套图图案"><option value="solid">纯色</option><option value="dark">深底浅点</option><option value="light">浅底深点</option></select></label><label>波点色 <input type="color" value="#ffffff" aria-label="本地套图波点色"></label><label>分界 <input type="number" min="10" max="90" value="55" aria-label="本地套图波点分界"></label><button class="btn" data-local-save>保存本色参数</button></div><p role="status" data-local-readiness>选择颜色后读取本地准备状态。</p>`;
 const lq=s=>localSettings.querySelector(s),localInfo=lq('[data-local-readiness]');
 localSettings.insertAdjacentHTML('beforeend',colourToneMarkup());bindColourTuning(localSettings);
 const sampleButton=document.createElement('button');sampleButton.className='btn';sampleButton.textContent='从同色参考图取色';sampleButton.type='button';
 lq('[data-local-save]').before(sampleButton);
 const masksButton=document.createElement('button');masksButton.className='btn';masksButton.textContent='查看自动识别与细节调整';masksButton.hidden=true;localSettings.append(masksButton);
 const localPreparation=document.createElement('div');localPreparation.className='colour-local-preparation';localPreparation.hidden=true;localPreparation.append(localInfo,masksButton);
 masksButton.onclick=()=>{advanced.open=true;if(!refreshPixelSources)refreshPixelSources=mountPixelRecolour(advanced,p,panel);advanced.scrollIntoView({behavior:'smooth',block:'start'})};
 let localKey='',localDirty=false,localEpoch=0;
 for(const input of localSettings.querySelectorAll('input,select'))input.oninput=()=>{localDirty=true;localInfo.textContent='参数尚未保存，请先对照参考图保存本色参数。'};
 async function localCall(action,extra={}){return ColourApi.post('local/'+action,{productId:p.id,colorKey:color.value,reference:reference.value,...extra},'本地换色不可用；未调用生图API')}
 async function loadLocal(){
  const group=groups.find(row=>row.key===color.value);
  localSettings.hidden=!group?.ready;localPreparation.hidden=!group?.ready;if(!group?.ready)return;
  const key=color.value+'|'+reference.value;if(key===localKey&&localDirty)return;
  if(active){localInfo.textContent='正在按已保存的变体主图颜色批量制作；本批完成前保留当前选区。';return}
  const epoch=++localEpoch;localKey=key;refreshPixelSources?.clearRecipe();localInfo.textContent='正在从该变体主图自动识别衣料颜色，并准备母版选区…';
  try{const slot=+(panel.querySelector('[aria-label="本地换色原图"]')?.value||0),d=await localCall('prepare',{slot:Math.max(0,slot)});if(epoch!==localEpoch||localDirty||key!==color.value+'|'+reference.value)return;
   const recipe=d.recipe;
   lq('[aria-label="本地套图目标色"]').value=recipe.target;lq('[aria-label="本地套图曝光"]').value=recipe.exposure;lq('[aria-label="本地套图纹理"]').value=recipe.texture;lq('[aria-label="本地套图图案"]').value=recipe.pattern?.kind||'solid';lq('[aria-label="本地套图波点色"]').value=recipe.pattern?.color||'#ffffff';lq('[aria-label="本地套图波点分界"]').value=recipe.pattern?.threshold||55;loadColourTuning(localSettings,recipe);
   localDirty=false;localSettings.open=false;masksButton.hidden=true;
   localInfo.textContent='已从变体 '+(recipe.referenceSourceAsin||'主图')+' 的衣料自动取色 '+recipe.target+'；选区已自动识别，可直接制作当前色或全部颜色。';
   refreshPixelSources?.applyRecipe(recipe,d.selection);
  }catch(e){if(epoch===localEpoch)localInfo.textContent='自动准备未完成：'+e.message}
 }
 panel.addEventListener('colour-master-slot',()=>{if(!localDirty)void loadLocal()});
 sampleButton.onclick=()=>{
  if(!color.value||!reference.value){localInfo.textContent='请选择颜色和同色参考图';return}
  const key=color.value,ref=reference.value;
  openColourReferenceSampler(ref,box=>ColourApi.post('local/sample-reference',{productId:p.id,colorKey:key,reference:ref,box}),sample=>{
   lq('[aria-label="本地套图目标色"]').value=sample.target;localDirty=true;localSettings.open=true;
   localInfo.textContent='已从面料取色 '+sample.target+'，请对照参考图保存本色参数。';
  },()=>color.value===key&&reference.value===ref&&panel.isConnected);
 };
 lq('[data-local-save]').onclick=async()=>{
  const saveButton=lq('[data-local-save]'),key=color.value,ref=reference.value;
  try{if(!key||!ref)throw Error('请选择颜色和同色参考图');const kind=lq('[aria-label="本地套图图案"]').value;
   const data={confirmed:true,target:lq('[aria-label="本地套图目标色"]').value,exposure:+lq('[aria-label="本地套图曝光"]').value,texture:+lq('[aria-label="本地套图纹理"]').value,...readColourTuning(localSettings),pattern:kind==='solid'?null:{kind,color:lq('[aria-label="本地套图波点色"]').value,threshold:+lq('[aria-label="本地套图波点分界"]').value}};
   const submitted=JSON.stringify(data);saveButton.disabled=true;
   await localCall('configure',data);
   if(color.value!==key||reference.value!==ref)return;
   const currentKind=lq('[aria-label="本地套图图案"]').value;
   const current={confirmed:true,target:lq('[aria-label="本地套图目标色"]').value,exposure:+lq('[aria-label="本地套图曝光"]').value,texture:+lq('[aria-label="本地套图纹理"]').value,...readColourTuning(localSettings),pattern:currentKind==='solid'?null:{kind:currentKind,color:lq('[aria-label="本地套图波点色"]').value,threshold:+lq('[aria-label="本地套图波点分界"]').value}};
   if(JSON.stringify(current)!==submitted){localInfo.textContent='已保存提交时的参数；后续调整尚未保存。';return}
   localDirty=false;await loadLocal();
  }catch(e){localInfo.textContent=e.message}finally{saveButton.disabled=false}
 };
 const beforeLocalColor=color.onchange,beforeLocalReference=reference.onchange;
 color.onchange=()=>{refreshPixelSources?.clearRecipe();beforeLocalColor();localDirty=false;void loadLocal()};reference.onchange=()=>{refreshPixelSources?.clearRecipe();beforeLocalReference();localDirty=false;void loadLocal()};
 const status=document.createElement('p');status.setAttribute('role','status');status.className='colour-action-status';
 const resultsHeading=document.createElement('h3');resultsHeading.textContent='换色结果';
 const results=document.createElement('div');results.className='colour-results';
 panel.append(master,readiness,fields,referenceCard,advanced,children,localPreparation,localSettings,button,status,resultsHeading,results,batch);
 host.after(panel);updateControls();
 advanced.addEventListener('toggle',()=>{if(advanced.open&&!refreshPixelSources)refreshPixelSources=mountPixelRecolour(advanced,p,panel)});if(advanced.open&&!refreshPixelSources)refreshPixelSources=mountPixelRecolour(advanced,p,panel);
 async function refresh(){
  if(!panel.isConnected)return;
  try{
   const data=await ColourApi.sets(p.id);
   results.replaceChildren();groups=data.colors||[];
   masterKey=data.masterReferenceMatches&&groups.some(row=>row.key===data.masterColorKey&&row.ready)?data.masterColorKey:'';
   active=data.sets.some(s=>['queued','validating','generating','reviewing','local_preparing','local_rendering'].includes(s.status));
   const previousColor=color.value,previousRef=reference.value;
   const targets=ColourViewRules.targets(groups,data.masterColorKey);
   color.replaceChildren(new Option('选择目标颜色',''),...targets.map(row=>new Option(row.color+(row.listingEligible===false?' · 货源待确认':''),row.key)));
   color.value=targets.some(row=>row.key===previousColor)?previousColor:'';
   updateReferences(previousRef);
   const issueTypes=new Set(groups.flatMap(row=>row.issues.map(issue=>issue.includes('子 SKU')?'子 SKU':
    issue.includes('参考图')?'同色参考图':issue.startsWith('该颜色的尺码')?'尺码':'货源确认')));
   if(groups.length&&!masterKey)issueTypes.add('母版颜色与主体图核对');
   readiness.textContent=groups.length?[groups.filter(row=>row.references.length).length+' 色已关联参考图',
    targets.filter(row=>row.listingEligible===false).length?targets.filter(row=>row.listingEligible===false).length+' 色货源待确认':'',
    issueTypes.size?'待补：'+[...issueTypes].join('、'):''].filter(Boolean).join(' · '):'待补：颜色、尺码和子 SKU';
   if(!data.sets.length){const empty=document.createElement('p');empty.className='sub';empty.textContent='暂无换色结果';results.append(empty)}
   if(data.sets.length){const progress=document.createElement('p');const made=data.sets.reduce((n,s)=>n+s.items.filter(i=>i.image).length,0),total=data.sets.reduce((n,s)=>n+s.items.length,0);progress.textContent='换色总进度：'+made+' / '+total+' 张 · '+data.sets.length+' 个颜色（母版另计）';results.append(progress)}
   if(data.qualityPolicy){const policy=document.createElement('p');policy.className='sub';policy.textContent=data.qualityPolicy.label;results.append(policy)}
   // Correction records remain in the ledger; show each finished image once in its colour set.
   for(const issue of data.errors||[]){const notice=document.createElement('p');notice.setAttribute('role','alert');notice.textContent=issue.error+' · '+issue.id;results.append(notice)}
   for(const s of data.sets.sort((a,b)=>(a.created||0)-(b.created||0))){
    const section=document.createElement('section');section.style.cssText='border-top:1px solid #dce3ec;margin-top:16px;padding-top:16px';
    const linked=s.skuBinding?.status==='linked';
    if(s.bindingPending)active=true;
    const h=document.createElement('h3');const done=s.items.filter(i=>i.image).length;h.textContent=s.color+' · '+done+'/'+s.items.length+' 张 · '+(linked?'已自动关联 '+s.skuBinding.skus.length+' 个子 SKU':({queued:'排队中',local_preparing:'本地准备中',local_rendering:'本地换色中',local_paused:'本地处理已暂停',validating:'核对同款与目标颜色',generating:'换色中',reviewing:'检查中',done:'待自动关联',awaiting_manual:'待自动关联',approved:'已关联',needs_attention:'需要处理'})[s.status]);section.append(h);
    if(['queued','validating','generating','reviewing','local_preparing','local_rendering'].includes(s.status))active=true;
    if(s.model==='local-pixel'&&['local_preparing','local_rendering','local_paused'].includes(s.status)){
     const control=document.createElement('button'),action=s.status==='local_paused'?'resume':'pause';control.className='btn';control.textContent=action==='pause'?'暂停本地处理':'继续本地处理';
     control.onclick=async()=>{if(!confirm(action==='pause'?'暂停后保存当前一张，不再启动后续图位。继续？':'从保存图位继续；不会调用生图API，后续AI质检可能消耗额度。继续？'))return;control.disabled=true;try{await localCall(action,{id:s.id,confirmed:true});await refresh()}catch(e){toast(e.message)}finally{control.disabled=false}};section.append(control)
    }
    if(s.error){const error=document.createElement('p');error.textContent=s.error;section.append(error)}
    if(s.status==='needs_attention'&&s.items.some(i=>i.status==='queued')&&s.items.some(i=>i.status==='needs_revision')&&!s.items.some(i=>['submitting','submit_unknown','generating','reviewing'].includes(i.status))){const proceed=document.createElement('button');proceed.className='btn';proceed.textContent='继续制作其他图';proceed.onclick=async()=>{if(!confirm('继续制作尚未提交的其他图片并计费；需修改的图片仍保留问题，不自动通过审核。继续？'))return;proceed.disabled=true;try{const d=await ColourApi.post('continue',{productId:p.id,id:s.id,confirmed:true});await refresh()}catch(e){toast(e.message);proceed.disabled=false}};section.append(proceed)}
    if(s.referenceWarnings?.length){const warning=document.createElement('p');warning.textContent=s.referenceEvidenceType==='amazon_variant_main'?'Amazon 主图来源 '+s.referenceSourceAsin+' · 成图请对照本款实物核对颜色。':s.referenceEvidenceType==='supplier_ai_preview'?'供应商AI预览仅作颜色参考；版型与纹理沿用母版，仍需对照实物核对颜色。':s.model==='local-source-layout'?'实物图复用版式：请核对款式、颜色、素材清晰度与使用授权。':'颜色编辑审核草稿：请对照实物核对面料、结构与颜色。';section.append(warning)}
    if(s.status==='needs_attention'&&!s.validated){const retry=document.createElement('button');retry.className='btn';retry.textContent='重新核对同款素材';retry.onclick=async()=>{try{const d=await ColourApi.post('retry',{productId:p.id,id:s.id,confirmed:true,revalidate:true,reference:reference.value||s.reference});await refresh()}catch(e){toast(e.message)}};section.append(retry)}
    const gallery=document.createElement('div');gallery.style.cssText='display:flex;gap:12px;flex-wrap:wrap;margin:12px 0';
    for(const item of s.items){const card=document.createElement('div');card.style.width='150px';const text=document.createElement('p');text.textContent=(item.slot+1)+' · '+({queued:'待制作',local_pending:'待本地换色',local_ready:'本地换色完成，待检查',local_failed:'本地处理失败',submitting:'提交中',generating:'换色中',reviewing:'检查中',done:'已制作',awaiting_manual:'检查通过',approved:'检查通过',needs_revision:'需修改',failed:'失败',submit_unknown:'请核对计费任务'})[item.status];card.append(text);
     if(item.image){const a=document.createElement('a');a.href='/api/colours/image?id='+encodeURIComponent(s.id)+'&slot='+item.slot;a.target='_blank';a.rel='noopener';const img=document.createElement('img');img.src=a.href;img.alt=s.color+' 第'+(item.slot+1)+'张';img.style.cssText='width:150px;height:150px;object-fit:contain';a.append(img);card.append(a)}
     if(item.qc?.issues?.length){const issues=document.createElement('p');issues.className='sub';issues.textContent=item.qc.issues.join('；');card.append(issues)}
     if(item.qc?.warnings?.length){const warning=document.createElement('p');warning.className='sub';warning.style.color='#8c641e';warning.textContent='通过，有提醒：'+item.qc.warnings.join('；');card.append(warning)}
     if(item.status==='needs_revision'&&item.localCorrection&&data.qualityPolicy&&item.qc?.policy!==data.qualityPolicy.id){const review=document.createElement('button');review.className='btn';review.textContent='按常规标准复核';review.onclick=async()=>{review.disabled=true;try{const result=await ColourApi.post('review-local',{productId:p.id,id:s.id,slots:[item.slot],confirmed:true,policyReview:data.qualityPolicy.id});await refresh()}catch(e){toast(e.message);review.disabled=false}};card.append(review)}
     if(item.error){const e=document.createElement('p');e.textContent=item.error;card.append(e)}
     if(item.status==='needs_revision'){
      const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';input.hidden=true;
      const repair=document.createElement('button');repair.className='btn';repair.textContent='上传修正版并检查';repair.onclick=()=>input.click();
      input.onchange=async()=>{const file=input.files[0];if(!file)return;const note=prompt('说明这张图修改了什么；上传后会重新检查，不自动通过审核。');if(!note?.trim())return;repair.disabled=true;try{if(file.size>15*1024*1024)throw Error('图片请控制在15 MB以内');const asset=await ColourApi.upload(file);const result=await ColourApi.post('repair-local',{productId:p.id,id:s.id,slot:item.slot,previousImage:item.image,image:asset.url,note,confirmed:true});await refresh()}catch(e){toast(e.message);repair.disabled=false}};
      card.append(input,repair);
     }
     if(s.model!=='local-pixel'&&['needs_revision','failed'].includes(item.status)){const retry=document.createElement('button');retry.className='btn';retry.textContent='重做此张';retry.onclick=async()=>{if(!confirm('重新调用图片模型制作这一张并审核，会再次计费，是否继续？'))return;try{const d=await ColourApi.post('retry',{productId:p.id,id:s.id,slot:item.slot,confirmed:true});await refresh()}catch(e){toast(e.message)}};card.append(retry)}gallery.append(card)
    }
    section.append(gallery);
    if(linked){const note=document.createElement('p');note.className='sub colour-sku-binding';note.textContent=s.items.length+' 张图片已按顺序关联同色子 SKU';section.append(note)}
    else if(s.skuBindingError&&['done','awaiting_manual','approved'].includes(s.status)){const note=document.createElement('p');note.setAttribute('role','status');note.textContent='尚未关联：'+s.skuBindingError;section.append(note)}
    if(s.items.some(i=>i.image)){const a=document.createElement('a');a.className='btn';a.textContent=linked||s.status==='approved'?'下载此颜色套图':'下载现有图片';a.href='/api/colours/export?id='+encodeURIComponent(s.id);a.download=p.id+'-'+s.color+'.zip';section.append(a)}results.append(section)
   }
   try{await appendMasterColour(master,masterBody,p,groups,data.masterColorKey,refresh)}catch(e){master.querySelector('summary').textContent='母版：读取失败';masterBody.textContent=e.message}
   refreshPixelSources?.();updateControls();void loadLocal();if(active)colourPollTimer=setTimeout(refresh,8000);
  }catch(e){status.textContent=e.message}
 }
 button.onclick=async()=>{
  if(!color.value||!reference.value)return toast('请选择已确认的颜色和同色参考图');
  if(localDirty)return toast('请先保存可选微调参数，或切换颜色恢复自动取色');
  if(!confirm('从当前变体主图自动取色，自动识别母版衣服后制作整套；已过检图保留。后续AI质检仍可能消耗模型额度。继续？'))return;
  button.disabled=true;status.textContent='正在创建换色任务…';
  try{await flushWorkspace();const data=await localCall('start',{confirmed:true});status.textContent=data.createdColors?'本地任务已保存，后台换色后进入AI质检；未提交生图API。':'该颜色已有过检套图，已保留原图。';await refresh()}catch(e){status.textContent=e.message;updateControls()}
 };
 allButton.onclick=async()=>{if(localDirty)return toast('请先保存可选微调参数，或切换颜色恢复自动取色');if(!confirm('逐色读取变体主图的衣料颜色，自动识别母版后批量制作，保留已过检图。AI质检仍可能消耗额度。继续？'))return;allButton.disabled=true;status.textContent='正在核对本地选区和颜色参数…';try{await flushWorkspace();const d=await localCall('start-all',{confirmed:true});status.textContent='已创建 '+d.createdColors+' 个本地颜色任务，保留 '+d.skipped.length+' 套已有过检图片；未提交生图API。';await refresh()}catch(e){status.textContent=e.message;updateControls()}};
 void refresh();
}

async function appendMasterColour(master,body,p,groups,masterKey,onSaved){
 const data=await ColourApi.masterView(p.id);
 let plan=data.sets?.gallery;
 if(p.generatedGallerySelection){
  const accountId=signedUser?.id,jobs=await imageApi('jobs');
  if(!body.isConnected||signedUser?.id!==accountId||product()?.id!==p.id)return;
  const images=(p.generatedGallerySelection.items||[]).map(row=>{
   const job=jobs.jobs.find(j=>j.id===row.jobId&&j.productId===p.id&&j.status==='completed');
   return {final_url:job?.images?.[row.imageIndex||0]};
  });
  plan={images,product_profile:{product_colours:[]}};
 }
 body.replaceChildren();
 const known={original_reference_olive_brown:'橄榄褐色',black:'黑色',white:'白色',brown:'褐色',blue:'蓝色',red:'红色',green:'绿色',grey:'灰色',gray:'灰色',navy:'藏蓝色'};
 const colors=plan?.product_profile?.product_colours||[];const detected=colors.length===1?(known[colors[0]]||''):'';
 master.querySelector('summary').textContent='母版：'+(p.masterColor||'颜色待确认')+' · 查看／更换';
 if(!plan){const note=document.createElement('p');note.className='sub';note.textContent='还没有母版分镜，请先在「母版套图」制作。';body.append(note);return;}
 const label=document.createElement('label');label.textContent='母版颜色：';
 const input=document.createElement(groups.length?'select':'input');
 const confirmed=ColourViewRules.confirmedMasters(groups);
 if(groups.length){
  const empty=new Option('选择已确认的母版颜色','');empty.disabled=true;
  input.replaceChildren(empty,...confirmed.map(row=>new Option(row.color,row.key)));
  input.value=confirmed.some(row=>row.key===masterKey)?masterKey:'';
  input.disabled=!confirmed.length;
 }else{
  input.value=p.masterColor||detected;input.placeholder='填写真实颜色名称';
 }
 input.onchange=async()=>{
  if(groups.length){
   if(!confirmed.some(row=>row.key===input.value))return toast('母版只能选择已确认颜色');
   input.disabled=true;
   try{await saveColourAssociation(p,'master',input.value);await onSaved()}
   catch(error){input.value=masterKey;toast(error.message)}finally{input.disabled=!confirmed.length}
   return;
  }
  p.masterColor=groups.length?(groups.find(row=>row.key===input.value)?.color||''):input.value.trim().slice(0,60);
  persist();
  try{await flushWorkspace();await onSaved()}catch(error){toast(error.message)}
 };
 label.append(input);body.append(label);
 const gallery=document.createElement('div');gallery.className='colour-master-thumbnails';
 for(const [i,item] of (plan.images||[]).entries()){if(!item.final_url)continue;const a=document.createElement('a');a.href=item.final_url;a.target='_blank';a.rel='noopener';const image=document.createElement('img');image.src=item.final_url;image.alt='母版第'+(i+1)+'张';a.append(image);gallery.append(a)}
 if(gallery.childElementCount)body.append(gallery);
}

// Existing references retain editable colour associations within the visual step.
function mountColourBindings(){
 const p=product(),asset=document.getElementById('assetInput')?.closest('section');if(!p||!asset)return;
 const section=document.createElement('details');section.className='panel box';
 const title=document.createElement('summary');title.textContent='关联颜色 · 已上传 / 采集素材';section.append(title);
 const hint=document.createElement('p');hint.textContent='Amazon 已核对的同色变体主图会自动关联。需要补充其他素材时，可以在这里填写对应颜色。';section.append(hint);
 const grid=document.createElement('div');grid.style.cssText='display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px';
 const refs=[...(p.supplierColorReferences||[]).map(a=>({url:a.url,name:(p.assetColorBindings?.[a.url]||a.color)+' · 供应商素材'})),...(p.assets||[]).map(a=>({url:a.url,name:a.name,asset:a})),...collectedProductImages(p).map((url,i)=>({url,name:'采集素材 '+(i+1)}))],entries=[];
 for(const item of new Map(refs.map(r=>[r.url,r])).values()){
  const card=document.createElement('label'),img=document.createElement('img');img.src=item.url;img.alt=item.name;img.style.cssText='width:100%;height:140px;object-fit:contain';
  const name=document.createElement('span');name.textContent=item.name;
  const input=document.createElement('input');input.setAttribute('aria-label',item.name+'关联颜色');input.placeholder='填写关联颜色';input.maxLength=100;input.value=item.asset?.color||p.assetColorBindings?.[item.url]||'';
  card.append(img,name,input);grid.append(card);entries.push({item,input});
 }
 const save=document.createElement('button');save.className='btn';save.textContent='保存颜色关联';
 save.onclick=async()=>{save.disabled=true;try{p.assetColorBindings||={};for(const {item,input} of entries){const value=input.value.trim();if(value)p.assetColorBindings[item.url]=value;else delete p.assetColorBindings[item.url];if(item.asset)item.asset.color=value}persist();await flushWorkspace();render();toast('颜色关联已保存')}catch(e){toast('颜色关联保存失败：'+e.message);save.disabled=false}};
 section.append(grid,save);asset.append(section);
}
