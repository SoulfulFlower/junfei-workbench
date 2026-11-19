// Product workflow additions. No model calls or credentials in this module.
const workflowLists=s=>[...new Set(String(s||'').split(/[,，]/).map(x=>x.trim()).filter(Boolean))];
const listingFields=[['title','产品标题'],['highlights','商品亮点'],['bullets','五点描述'],['description','产品描述'],['terms','后台搜索词']];
function listingLocked(copy,field){return Array.isArray(copy?.lockedFields)&&copy.lockedFields.includes(field)}
function listingWithLocks(current,candidate){
 const result=structuredClone(candidate);
 delete result.lockedFields;
 const locks=listingFields.map(([field])=>field).filter(field=>listingLocked(current,field));
 if(locks.length){
  result.lockedFields=locks;
  result.translations={...result.translations};
  for(const field of locks){
   result[field]=current[field]??'';
   result.translations[field]=current.translations?.[field]??'';
  }
  delete result.contentAudit;
  result.zh='';
 }
 return result;
}
function workflowVariants(p){const colors=workflowLists(p.colorNames),sizes=workflowLists(p.sizeNames);if(!colors.length||!sizes.length)return [];return colors.flatMap((color,c)=>sizes.map((size,s)=>({color,size,sku:`${p.id}-C${String(c+1).padStart(2,'0')}-S${String(s+1).padStart(2,'0')}`,assets:(p.assets||[]).filter(a=>(a.color||'').trim()===color).length})))}
function workflowSnapshot(p,source,targetMarket=market,workspace=state){const copy=workspace.copy[p.id+'-'+targetMarket];if(!copy)return false;p.copyHistory||=[];p.copyHistory.push({market:targetMarket,date:new Date().toISOString(),source,copy:structuredClone(copy)});return true}
const workflowEnhanceBefore=enhance;
enhance=function(){workflowEnhanceBefore();if(view!=='listing')return;const p=product(),facts=[['material','材质'],['dimensions','尺寸'],['packageContents','包装内容'],['colorNames','颜色名称'],['sizeNames','尺码/规格'],['keywords','关键词']];const missing=facts.filter(([k])=>!String(p[k]||'').trim()).map(([,n])=>n);const notice=document.createElement('section');notice.className='panel box';notice.dataset.workspacePanel='product';const heading=document.createElement('h2');heading.textContent='产品图片与素材';notice.append(heading);const photos=[...(p.assets||[]).filter(a=>typeof a.url==='string'&&a.url.startsWith('/uploads/')).map(a=>({url:a.url,label:a.name||'已上传素材'})),...collectedProductImages(p).map(url=>({url,label:url.includes('alicdn.com')?'1688 采集图':'ASIN 采集图'}))];const unique=[...new Map(photos.map(a=>[a.url,a])).values()];const note=document.createElement('p');note.textContent=unique.length?'共 '+unique.length+' 张图片，点击可查看大图。':'还没有产品图片，请先采集商品或在图片工作台上传。';notice.append(note);const gallery=document.createElement('div');gallery.className='listing-source-gallery';for(const photo of unique){const link=document.createElement('a');link.href=photo.url;link.target='_blank';link.rel='noopener';const image=document.createElement('img');image.src=photo.url;image.alt=photo.label;image.loading='lazy';image.referrerPolicy='no-referrer';const caption=document.createElement('span');caption.textContent=photo.label;link.append(image,caption);gallery.append(link)}notice.append(gallery);const button=document.createElement('button');button.className='btn';button.textContent='前往图片工作台';button.style.marginTop='16px';button.onclick=()=>go('images');notice.append(button);document.querySelector('.grid').before(notice);const copyNotice=document.querySelector('[data-fold-title="文案说明与资料提示"]')||document.createElement('div');copyNotice.className='notice';copyNotice.dataset.foldTitle='文案说明与资料提示';copyNotice.style.whiteSpace='pre-wrap';copyNotice.textContent=`文案资料完整度 ${facts.length-missing.length}/${facts.length} · `+(missing.length?'待补充：'+missing.join('、'):'基础字段已填写，请核对真实性')+'\n\n'+copyNotice.textContent;notice.before(copyNotice);const actions=document.querySelector('.titlebar .actions');for(const [id,label,action]of [['workspaceVariants','变体明细',()=>workflowShowVariants(p)],['workspaceSaveVersion','保存版本',()=>{if(!workflowSnapshot(p,'手动保存'))return toast('请先编辑或生成文案');persist();toast('当前站点文案版本已保存')}],['workspaceHistory','历史版本',()=>workflowHistory(p)]]){const b=document.createElement('button');b.className='btn';b.id=id;b.textContent=label;b.onclick=action;actions.append(b)}};
function workflowShowVariants(p){const rows=workflowVariants(p),modal=document.getElementById('modal');modal.style.width='850px';const tooMany=rows.length>2000;modal.innerHTML=`<h2>颜色 × 尺码变体</h2><p style="margin:12px 0">${esc(p.name)} · ${rows.length} 个组合。SKU 为预览建议；修改颜色或尺码排序会改变编号，尚未写入刊登记录。</p>${!rows.length?'<div class="notice">请先在“编辑资料与变体”填写颜色名称和尺码名称，用逗号分隔。</div>':`<div class="tablewrap" style="max-height:400px;overflow:auto"><table><thead><tr><th>建议子 SKU</th><th>颜色</th><th>尺码/规格</th><th>对应素材</th></tr></thead><tbody>${rows.slice(0,2000).map(r=>`<tr><td>${esc(r.sku)}</td><td>${esc(r.color)}</td><td>${esc(r.size)}</td><td>${r.assets?r.assets+' 张':'待绑定颜色素材'}</td></tr>`).join('')}</tbody></table></div>${tooMany?'<p>仅预览前 2000 行，下载包含全部组合。</p>':''}`}<div class="actions" style="margin-top:18px"><button class="btn" id="closeVariants">关闭</button><button class="btn primary" id="exportVariants" ${rows.length?'':'disabled'}>导出变体 JSON</button></div>`;modal.showModal();document.getElementById('closeVariants').onclick=()=>{modal.close();modal.style.width=''};document.getElementById('exportVariants').onclick=()=>download(p.id+'-variants.json',JSON.stringify({parentSku:p.id,previewOnly:true,variants:rows},null,2))}
function workflowHistory(p){
 const targetMarket=market,key=p.id+'-'+targetMarket,modal=document.getElementById('modal');
 const entries=(p.copyHistory||[]).filter(item=>item.market===targetMarket&&item.copy).reverse();
 const options='<option value="current">当前稿</option>'+entries.map((item,i)=>`<option value="${i}">${esc(new Date(item.date).toLocaleString('zh-CN'))} · ${esc(item.source||'历史版本')}</option>`).join('');
 modal.style.width='850px';
 modal.innerHTML=`<h2>${esc(targetMarket)} 站版本对比</h2><p>选择任意两个版本，逐字段核对原文和中文翻译。恢复右侧版本会保留当前锁定内容。</p>
 <div class="grid"><label class="field">左侧版本<select id="historyLeft">${options}</select></label>
 <label class="field">右侧版本<select id="historyRight">${options}</select></label></div>
 <div id="historyPreview" style="max-height:55vh;overflow:auto"></div>
 <div class="actions"><button class="btn" id="closeHistory">关闭</button><button class="btn primary" id="restoreHistory">恢复右侧版本</button></div>`;
 const left=modal.querySelector('#historyLeft'),right=modal.querySelector('#historyRight'),restore=modal.querySelector('#restoreHistory');
 const get=value=>value==='current'?(state.copy[key]||{}):entries[Number(value)].copy;
 const renderComparison=()=>{
  const a=get(left.value),b=get(right.value),current=get('current');
  restore.disabled=right.value==='current';
  const rows=listingFields.map(([field,label])=>{
   const av=a[field]??'',bv=b[field]??'',az=a.translations?.[field]??'',bz=b.translations?.[field]??'';
   const changed=av!==bv||az!==bz;
   return `<details ${changed?'open':''}><summary>${esc(label)} · ${changed?'有变更':'相同'}${listingLocked(current,field)?' · 当前已锁定':''}</summary>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px"><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(av||'（空）')}${az?'\n\n中文 · '+esc(az):''}</pre>
    <pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(bv||'（空）')}${bz?'\n\n中文 · '+esc(bz):''}</pre></div></details>`;
  });
  modal.querySelector('#historyPreview').innerHTML=entries.length?rows.join(''):'<p>暂无历史版本。先保存当前文案版本。</p>';
 };
 if(entries.length)right.value='0';
 left.onchange=right.onchange=renderComparison;
 modal.onclose=()=>{modal.style.width='';modal.onclose=null};
 modal.querySelector('#closeHistory').onclick=()=>modal.close();
 restore.onclick=()=>{
  if(right.value==='current'||market!==targetMarket||!state.products.includes(p))return;
  const next=listingWithLocks(get('current'),get(right.value));
  workflowSnapshot(p,'恢复前自动备份');
  state.copy[key]=next;p.status='制作中';
  state.reviews[p.id]={...state.reviews[p.id],copy:false,note:'历史文案已恢复，需要重新审核'};
  persist();modal.close();render();toast('已恢复右侧版本，当前版本已备份');
 };
 renderComparison();modal.showModal();
}
