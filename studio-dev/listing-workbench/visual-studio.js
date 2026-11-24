// Image-grounded visual storyboards; generation and QC continue on the shared server.
let visualPollTimer;
async function visualApi(action,data,scope='visual'){const r=await fetch('/api/'+scope+'/'+action,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});const result=await r.json();if(!r.ok)throw Error(result.error||'视觉工作台请求失败');return result}
const mountBeforeVisualStudio=mountImageGeneration;
mountImageGeneration=function(){mountBeforeVisualStudio();mountVisualStudio()};
function mountVisualStudio(){
 clearTimeout(visualPollTimer);const p=product();
 const panel=document.createElement('section');panel.id='visualStudio';panel.className='panel box';panel.style.cssText='margin:20px 0;border:2px solid #c8d7eb';
 panel.innerHTML=`<h2>智能套图 · 视觉策划与质检</h2><p>①在真实素材库指定主体图 → ②AI读图策划 → ③核对分镜与图上文案 → ④生成成图 → ⑤AI质检 → ⑥人工确认</p><p class="sub">副图直接生成图文排版，主图无营销文字。AI会读取主体图、已保存产品资料和当前站点文案；不确定的事实需人工确认。</p><label class="field"><span>本套创意要求</span><textarea id="studioBrief" style="width:100%;min-height:75px" placeholder="受众、真实场景、风格、色调、需要强调的事实；不填写也可由AI结合产品规划"></textarea></label><button id="planVisual" class="btn primary">AI读取主体图并制定整套分镜</button><p id="visualStatus" role="status"></p><div class="actions" style="margin-top:18px"><label>方案版本 <select id="visualVersion"><option value="">暂无方案</option></select></label><button class="btn" id="refreshVisual">刷新方案与任务</button></div><div id="visualEditor"></div><div id="visualRuns"></div>`;
 const asset=document.getElementById('assetInput')?.closest('section');(asset||document.querySelector('.notice')).after(panel);
 // The detailed prior controls remain available for manual prompt workflows.
 const legacy=[document.getElementById('visualBrief')?.closest('section'),document.getElementById('planColor')?.closest('section')];
 const manual=document.createElement('details');manual.className='panel box';manual.style.margin='18px 0';const manualSummary=document.createElement('summary');manualSummary.textContent='手动提示词模式（可选，不经过智能质检）';manual.append(manualSummary);panel.after(manual);for(const x of legacy){if(x)manual.append(x)}const manualNote=document.createElement('p');manualNote.textContent='真实素材库的参考图与下方模型设置同样供智能套图使用；手动生成按钮只执行当前提示词。';manual.append(manualNote);
 let projects=[],runs=[],current,planningId='',lastPlanId='';
 const status=panel.querySelector('#visualStatus'),version=panel.querySelector('#visualVersion'),editor=panel.querySelector('#visualEditor');
 const planButton=panel.querySelector('#planVisual');
 panel.querySelector('#studioBrief').value=p.visualBrief||'';
 planButton.onclick=async()=>{
  const refs=selectedImageReferences();
  if(!refs.length||refs.length>4)return toast('请在真实素材库设定主体图，并选择 1–4 张同款同色图片');
  if(!confirm('将实拍交给视觉模型识别，再由当前文案模型编排分镜。策划使用模型额度，生图需另行确认。是否开始？'))return;
  planButton.disabled=true;
  status.innerHTML=generationProgressHTML('running','正在提交分镜策划');
  try{
   const task=await visualApi('plan',{productId:p.id,references:refs,target_count:7,brief:panel.querySelector('#studioBrief').value},'studio');
   planningId=task.id;
   status.innerHTML=generationProgressHTML('running',task.message);
  }catch(error){planButton.disabled=false;status.innerHTML=generationProgressHTML('failed',error.message)}
 };
 function addPreflight(plan){
  const preflight=current.preflight||{},analysis=preflight.sourceAnalysis;
  const angleLabels=preflight.sceneDirectionFields?.angle?.[1]||{};
  const report=document.createElement('details');
  report.className='panel box';
  const heading=document.createElement('summary');heading.textContent='生图前的素材分析';report.append(heading);
  const add=(text)=>{const p=document.createElement('p');p.textContent=text;report.append(p)};
  if(analysis){
   for(const view of analysis.views){
    const identity={primary:'主体真值',same_sku:'同款实拍',different_sku:'不同款式',unverified:'同款未核实'}[view.identity];
    add(['素材 '+(view.index+1),identity,angleLabels[view.angle]||'角度未核实',...view.visible].join(' · '));
   }
   if(analysis.layoutCount)add('已识别 '+analysis.layoutCount+' 张竞品版式，仅供排版参考。');
  }else add('这份历史分镜没有逐张实拍角度记录。重做场景图前请重新策划。');
  for(const item of preflight.quality?.skipped_analyses||[])add(item.message);
  for(const item of preflight.quality?.issues||[])if(item.severity==='error')add(item.message);
  editor.insertBefore(report,editor.querySelector('#visualIdentity'));
  const slots=[...editor.querySelectorAll('#visualSlots > details')];
  for(const [i,details] of slots.entries()){
   const card=current.uiPlan?.images?.[i],evidence=preflight.cards?.[i];
   if(card){
    details.querySelector('summary').textContent=(i+1)+' · '+(card.role||card.shot_type)+' — '+plan.slots[i].question;
   }
   const button=details.querySelector('button');
   if(evidence?.sourceIssue){
    const note=document.createElement('p');note.className='notice';note.textContent=evidence.sourceIssue;
    details.insertBefore(note,button);button.disabled=true;
   }
   if(evidence?.sourceObservation){
    const note=document.createElement('p');note.textContent='附图 1 · '+(angleLabels[evidence.sourceObservation.angle]||'商品实拍')+' · '+evidence.sourceObservation.visible.join('、');
    details.insertBefore(note,button);
   }
   if(!evidence?.sourceIssue&&evidence?.product_source_url){
    const refs=document.createElement('div');refs.className='actions';
    for(const [url,label] of [[evidence.product_source_url,'附图 1 · 商品实拍'],[card?.template_url,'附图 2 · 仅参考版式']]){
     if(!url)continue;
     const link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noopener';link.textContent=label;
     refs.append(link);
    }
    details.insertBefore(refs,button);
   }
   if(evidence?._isScene&&card&&preflight.sceneDirectionFields){
    for(const [key,[name,options]] of Object.entries(preflight.sceneDirectionFields)){
     const label=document.createElement('label');label.className='field';label.textContent=name;
     const field=document.createElement('select');field.dataset.direction=key;field.dataset.index=String(i);
     field.append(new Option('请选择',''),...Object.entries(options).map(([value,text])=>new Option(text,value)));
     field.value=card.scene_direction?.[key]||'';field.dataset.original=field.value;
     label.append(field);details.insertBefore(label,button);
    }
   }
  }
 }
 function draw(){
  current=projects.find(x=>x.id===version.value);editor.replaceChildren();if(!current)return;
  const plan=current.plan;
  editor.innerHTML=`<p style="margin-top:16px"><strong>${current.confirmed?'✓ 此版本已确认':'待核对分镜'}</strong> · 修改并保存会创建新版本；旧图片留在历史版本。</p><p class="notice">${esc((plan.warnings||[]).join('；')||'仍需核对外观、事实和文字。AI判断不能替代人工审核。')}</p><div id="visualIdentity"></div><div id="visualSlots"></div><label style="display:block;margin:18px 0"><input type="checkbox" id="confirmVisualFacts"> 我已核对主体、事实依据、图上文案，未确认尺寸和配件不作宣传</label><button class="btn primary" id="saveVisual">保存修改并确认分镜</button><label style="display:block;margin-top:18px"><input type="checkbox" id="visualAutoRepair"> AI质检未通过时，允许自动重画一次（额外计费，每张最多2次生成）</label><button class="btn primary" id="generateVisualSet" style="margin-top:12px" ${current.confirmed?'':'disabled'}>生成此版本剩余图片</button><p class="sub">使用下方图片模型、比例、分辨率。以本版本保存的主体和细节图为准；更换主体图请重新策划。生成后后台持续质检，关闭页面仍可继续。</p>`;
  const identity=editor.querySelector('#visualIdentity');for(const [key,label]of [['identity','产品视觉身份（不可变细节与疑点）'],['palette','整套5色背景色板（逗号分隔）'],['lighting','统一光线'],['typography','字体与排版气质'],['audience','目标受众']]){const l=document.createElement('label');l.className='field';const span=document.createElement('span');span.textContent=label;const t=document.createElement('textarea');t.dataset.planKey=key;t.style.cssText='width:100%;min-height:55px';t.value=key==='palette'?plan[key].join(', '):plan[key];l.append(span,t);identity.append(l)}
  const slots=editor.querySelector('#visualSlots');for(const s of plan.slots){const d=document.createElement('details');d.className='panel box';d.style.marginTop='12px';const summary=document.createElement('summary');summary.textContent=(s.index+1)+' · '+['白底主图','生活场景图','核心卖点图','尺寸说明图','材质细节图','配件与包装图','颜色展示图'][s.index]+' — '+s.question;d.append(summary);for(const [key,label]of [['question','要回答的购买问题'],['evidence','事实依据'],['composition','构图与文字位置'],['headline','图上主标题'],['caption','图上辅助说明']]){const l=document.createElement('label');l.className='field';const span=document.createElement('span');span.textContent=label;const t=document.createElement('textarea');t.dataset.slot=String(s.index);t.dataset.key=key;const card=current.uiPlan?.images?.[s.index];t.value=key==='composition'&&card&&s.composition.includes('[SHOT DESIGN]')?(card.camera_direction||card.visual_concept||s.question):s[key];t.defaultValue=t.value;t.style.cssText='width:100%;min-height:50px';if(s.index===0&&['headline','caption'].includes(key)){t.disabled=true;t.placeholder='白底主图无营销文字'}l.append(span,t);d.append(l)}const b=document.createElement('button');b.className='btn';b.textContent='生成这一张';b.disabled=!current.confirmed;b.onclick=()=>submitSlots([s.index],b);d.append(b);slots.append(d)}
  addPreflight(plan);
  editor.querySelectorAll('textarea, select[data-direction]').forEach(t=>t.addEventListener('input',()=>{editor.dataset.dirty='1';editor.querySelectorAll('#generateVisualSet, #visualSlots button').forEach(b=>b.disabled=true)}));
  editor.querySelector('#saveVisual').onclick=async e=>{
   if(!editor.querySelector('#confirmVisualFacts').checked)return toast('请先勾选事实与文案确认');
   const changed=structuredClone(plan),sceneDirections={};
   for(const t of editor.querySelectorAll('[data-plan-key]'))changed[t.dataset.planKey]=t.dataset.planKey==='palette'?t.value.split(/[,，]/).map(x=>x.trim()):t.value;
   for(const t of editor.querySelectorAll('[data-slot]'))if(t.dataset.key!=='composition'||t.value!==t.defaultValue)changed.slots[Number(t.dataset.slot)][t.dataset.key]=t.value;
   const directionFields=[...editor.querySelectorAll('select[data-direction]')];
   const changedSlots=new Set(directionFields.filter(field=>field.value!==field.dataset.original).map(field=>field.dataset.index));
   for(const index of changedSlots){
    sceneDirections[index]=Object.fromEntries(directionFields.filter(field=>field.dataset.index===index&&field.value)
     .map(field=>[field.dataset.direction,field.value]));
   }
   e.target.disabled=true;
   try{
    const d=await visualApi('save',{id:current.id,plan:changed,sceneDirections,confirmed:true});
    editor.dataset.dirty='';await refresh(d.id);toast('已保存新版本并确认分镜');
   }catch(error){toast(error.message)}finally{e.target.disabled=false}
  };
  editor.querySelector('#generateVisualSet').onclick=e=>{const existing=runs.filter(r=>r.projectId===current.id);const ids=plan.slots.map(s=>s.index).filter(i=>!existing.some(r=>r.slot===i&&['submitting','generating','reviewing','repairing','awaiting_manual','approved','submit_unknown','interrupted','review_error','needs_revision'].includes(r.status)));if(!ids.length)return toast('各用途已有任务或待处理记录，请查看下方状态；需要返工可展开对应分镜单独生成');submitSlots(ids,e.target)};
 }
 async function submitSlots(ids,button){
  if(editor.dataset.dirty==='1')return toast('请先保存修改并确认分镜');
  const sourceIssues=ids.map(i=>current.preflight?.cards?.[i]?.sourceIssue).filter(Boolean);
  if(sourceIssues.length){status.textContent=sourceIssues.join(' ');return;}
  const auto=editor.querySelector('#visualAutoRepair').checked,projectId=current.id;
  const config={model:document.getElementById('imageModel').value,size:document.getElementById('imageSize').value,resolution:document.getElementById('imageResolution').value};
  if(!confirm(`按图位顺序生成并质检 ${ids.length} 张。每张最多 ${auto?2:1} 次生图，是否继续？`))return;
  button.disabled=true;
  try{
   const response=await fetch('/api/studio/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({productId:p.id,projectId,deliverable:current.deliverable||'gallery',indices:ids,confirmed:true,autoRepair:auto,reviewCompleteSet:ids.length>1,config})});
   const result=await response.json();
   if(!response.ok)throw Error(result.error||'生成任务未提交');
   status.innerHTML=generationProgressHTML('running','已启动逐张生成和质检，可在任务记录查看进度');
   await refresh(projectId);
  }catch(error){status.innerHTML=generationProgressHTML('failed',error.message)}finally{button.disabled=false}
 }
 function drawRuns(){const area=panel.querySelector('#visualRuns');const checkedByRun=new Map([...area.querySelectorAll('[data-run]')].map(card=>[card.dataset.run,[...card.querySelectorAll('input')].map(c=>c.checked)]));area.innerHTML='<h3 style="margin-top:24px">成图与质检 · 当前方案版本</h3>';const relevant=runs.filter(r=>r.projectId===current?.id);if(!relevant.length){const p=document.createElement('p');p.textContent='此版本暂无成图任务。';area.append(p);return}const labels={submitting:'正在提交',generating:'模型生成中',reviewing:'AI视觉质检中',repairing:'质检未过，自动返工中',awaiting_manual:'AI质检通过 · 待人工确认',approved:'已人工确认 · 可交付',needs_revision:'AI质检未通过 · 需修改',review_error:'质检或查询失败 · 待处理',submit_unknown:'提交未确认 · 先核对服务商',interrupted:'服务中断 · 先核对服务商',failed:'生成失败'};for(const r of relevant){const card=document.createElement('section');card.className='panel box';card.dataset.run=r.id;card.style.marginTop='14px';const title=document.createElement('h4');const localCheck=r.status==='awaiting_manual' && (r.qc?.at(-1)?.reviewMode==='technical_only' || (r.technicalReview?.ready && !r.qc?.length));title.textContent=(r.slot+1)+' · '+(localCheck?'技术检查通过 · 待人工确认':labels[r.status])+(r.attempt?' · 已返工1次':'');card.append(title);if(r.image){const a=document.createElement('a');a.href=r.image;a.target='_blank';a.rel='noopener noreferrer';const img=document.createElement('img');img.src=r.image;img.referrerPolicy='no-referrer';img.alt='第'+(r.slot+1)+'张成图';img.style.cssText='max-width:100%;width:340px;max-height:420px;object-fit:contain';a.append(img);card.append(a)}const detail=document.createElement('p');detail.style.whiteSpace='pre-wrap';detail.textContent=r.error||(r.qc||[]).map((q,i)=>'第'+(i+1)+'次质检：'+(q.pass?'通过':'未通过')+'\n'+q.issues.join('；')).join('\n');card.append(detail);if(r.status==='awaiting_manual'){const checks=['产品外观与颜色一致','图上文字准确且手机端可读','尺寸、卖点和配件有事实依据','整套风格与当前站点一致'];for(const text of checks){const l=document.createElement('label');l.style.cssText='display:block;margin:8px 0';const c=document.createElement('input');c.type='checkbox';c.checked=checkedByRun.get(r.id)?.[checks.indexOf(text)]||false;l.append(c,document.createTextNode(' '+text));card.append(l)}const b=document.createElement('button');b.className='btn primary';b.textContent='人工确认并标记可交付';b.onclick=async()=>{if([...card.querySelectorAll('input')].some(c=>!c.checked))return toast('请逐项完成核对');try{await visualApi('approve',{runId:r.id,checked:true});await refresh(current.id)}catch(error){toast(error.message)}};card.append(b)}area.append(card)}}
 const productQuery='?productId='+encodeURIComponent(p.id);
 async function refresh(wanted){if(!panel.isConnected)return;const d=await visualApi('projects'+productQuery+'&preflight=1');projects=d.projects;runs=d.runs;const chosen=wanted||version.value||projects[0]?.id;version.replaceChildren(...projects.map(x=>new Option(new Date(x.created*1000).toLocaleString('zh-CN')+' · '+(x.confirmed?'已确认':'待确认'),x.id)));if(projects.some(x=>x.id===chosen))version.value=chosen;draw();drawRuns()}
 version.onchange=()=>{editor.dataset.dirty='';draw();drawRuns()};panel.querySelector('#refreshVisual').onclick=()=>{if(editor.dataset.dirty==='1'&&!confirm('刷新会丢弃尚未保存的分镜修改，是否继续？'))return;editor.dataset.dirty='';refresh().catch(e=>toast(e.message))};
 async function poll(){
  if(!panel.isConnected)return;
  try{
   const [data,view]=await Promise.all([visualApi('projects'+productQuery),visualApi('view'+productQuery,null,'studio')]);
   const task=view.jobs?.plan;
   if(task?.status==='running'){
    planningId=task.id;planButton.disabled=true;
    status.innerHTML=generationProgressHTML('running',task.message+' · '+Math.round(task.progress*100)+'%');
   }else if(task&&(task.id===planningId||(!lastPlanId&&task.status==='failed'))){
    lastPlanId=task.id;planningId='';planButton.disabled=false;
    if(task.status==='done'){
     if(editor.dataset.dirty!=='1')await refresh(task.projectId);
     status.innerHTML=generationProgressHTML('completed','分镜已完成，请核对各图位的实拍依据和图上文案');
    }else status.innerHTML=generationProgressHTML('failed',task.error||task.message);
   }
   runs=data.runs;drawRuns();
  }catch(error){
   if(planningId)status.textContent='无法读取策划状态，后台任务可能仍在运行。'+error.message;
  }finally{if(panel.isConnected)visualPollTimer=setTimeout(poll,planningId?2000:10000)}
 }
 refresh().catch(e=>{status.textContent=e.message});void poll();
}
