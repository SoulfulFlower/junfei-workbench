// Connect the React editor to the account-scoped workspace and existing actions.
const renderOutsideProductEditor = render;
let productEditorHost;
const editorSteps = {product:'素材与洞察',copy:'Listing 文案',visual:'视觉套图',delivery:'交付'};

function mergeCapturedAmazonCategory(product,reference){
 const source=product.sourceImport,evidence=reference.categoryEvidence;
 if(!source?.asin||source.asin!==reference.asin||source.market!==reference.market||typeof reference.category!=='string'||!reference.category.trim()||evidence?.source!=='amazon_wayfinding_breadcrumbs'||!Array.isArray(evidence.breadcrumbs)||!evidence.breadcrumbs.length)return false;
 source.amazon={...source.amazon,category:reference.category,categoryEvidence:{...evidence,sourceUrl:reference.url,capturedAt:reference.capturedAt}};
 return true;
}

function editorContext(p, step){
 const targetMarket=market,key=p.id+'-'+targetMarket;
 const current=()=>state.products.find(item=>item.id===p.id);
 const draft=()=>state.copy[key]||defaults(p);
 const invalidate=note=>{
  const target=current();
  target.status='制作中';
  state.reviews[p.id]={...state.reviews[p.id],copy:false,note};
  persist();
 };
 return {
  product:p,accountId:signedUser?.id,step,market:targetMarket,products:state.products,identity:productIdentity,copy:draft(),getCopy:draft,pending:p.pendingCopy?.[targetMarket]?.copy,
  review:state.reviews[p.id]||{},completed:productDisplayStatus(p)==='已完成',online:serverReady,
  prepareCollection:async()=>{const owner=signedUser;await flushWorkspace();if(signedUser!==owner||!current())throw Error('账号或产品已变化，请刷新后再采集');},
  savePublicationCommerce:async details=>{
   const owner=signedUser;await flushWorkspace();
   if(signedUser!==owner||!current())throw Error('账号或产品已变化');
   const revision=serverRevision;
   const r=await fetch('/api/publication/commerce',{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Account':String(owner.id)},body:JSON.stringify({productId:p.id,revision,details})});
   const result=await r.json();if(!r.ok)throw Error(result.error||'英国经营资料未保存');
   if(signedUser!==owner||syncPending||syncBusy||syncConflict||serverRevision!==revision)throw Error('英国资料已保存在服务端；本地另有修改，请刷新后核对');
   state=result.state;serverRevision=result.revision;syncLabel('已保存到数据库');
  },
  busy:activeListingGeneration.has(key),notify:toast,goBack:()=>go('products'),
  navigate:(id,next)=>openListingWorkspace(id,next),
  assets:()=>[...new Map([...(p.assets||[]),...collectedProductImages(p).map(url=>({url,name:'采集参考图'}))].map(item=>[item.url,item])).values()],
  updateFacts:patch=>{
   const target=current();if(!target)return;
   if('name' in patch&&!patch.name.trim())return;
   Object.assign(target,patch);persist();
  },
  updateCopy:(field,value,translation)=>{
   if(!current())return;
   const copy=state.copy[key]||={...defaults(p)};
   if(listingLocked(copy,field))return;
   if(translation){(copy.translations||={})[field]=value;copy.zh='';persist();return}
   if(copy[field]===value)return;
   copy[field]=value;
   if(copy.translations)delete copy.translations[field];
   copy.zh='';delete copy.contentAudit;invalidate('文案有修改，待复核');
  },
  toggleLock:async field=>{
   const owner=signedUser;
   await flushWorkspace();
   if(signedUser!==owner||!current())throw Error('账号或产品已变化');
   const copy={...draft()},locks=new Set(copy.lockedFields||[]);
   if(locks.has(field))locks.delete(field);else locks.add(field);
   copy.lockedFields=[...locks];state.copy[key]=copy;
   persist({invalidateReview:false});
   await flushWorkspace();
   return copy;
  },
  generate:()=>generateCurrent(p,targetMarket,document.createElement('button')),
  batchGenerate:listingBatchDialog,
  insights:async(action,details={})=>{
   const owner=signedUser;
   await flushWorkspace();
   if(signedUser!==owner||!current())throw Error('账号或产品已变化');
   const response=await fetch('/api/product-insights',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action,productId:p.id,...details})});
   const result=await response.json();
   if(!response.ok)throw Error(result.error);
   return result;
  },
  progress:mountListingProgress,
  adopt:(candidate,base)=>{
   if(!current()||JSON.stringify(draft())!==base)return toast('文案已变化，请重新对比');
   workflowSnapshot(p,'采用候选前备份');
   state.copy[key]=listingWithLocks(draft(),candidate);
   if(p.pendingCopy?.[targetMarket]?.copy===candidate)delete p.pendingCopy[targetMarket];
   invalidate('采用新文案，待复核');render();
  },
  rewrite:async(field,value,mode)=>{
   await flushWorkspace();
   if(!current()||listingLocked(draft(),field))throw Error('该字段已锁定或产品已变化');
   const response=await fetch('/api/listing/rewrite',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({field,text:value,currentTitle:draft().title||'',market:targetMarket,mode,productId:p.id,product:listingGenerationProduct(p,targetMarket)})});
   const result=await response.json();if(!response.ok)throw Error(result.error);return result.text;
  },
  translate:async(field,value)=>{
   const response=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts:{[field]:value}})});
   const result=await response.json();if(!response.ok)throw Error(result.error);
   return result.translations?.[field]||'';
  },
  upload:async files=>{
   for(const file of files){
    const response=await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
    const result=await response.json();if(!response.ok)throw Error(result.error);
    const target=current();if(!target)return;
    (target.assets||=[]).push({url:result.url,name:file.name,source:'产品实拍',color:''});persist();
   }
  },
  readAsin:async(asin,site)=>{
   const owner=signedUser;
   await flushWorkspace();
   const target=current();
   if(signedUser!==owner||!target)throw Error('账号或产品已变化');
   const previous=target.editorAsinReference;
   const response=await fetch('/api/asin-reference/capture',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({productId:p.id,asin,market:site})});
   const result=await response.json();if(!response.ok)throw Error(result.error);
   if(signedUser!==owner||current()!==target||target.editorAsinReference!==previous)throw Error('ASIN 资料已变化，请重新采集');
   target.editorAsinReference=result;
   mergeCapturedAmazonCategory(target,result);
   persist({invalidateReview:false});
   await flushWorkspace();
   return result;
  },
  analyzeAsin:async()=>{
   const owner=signedUser;
   await flushWorkspace();
   const target=current(),reference=target?.editorAsinReference;
   if(signedUser!==owner||!reference)throw Error('请先保存 ASIN 采集资料');
   const response=await fetch('/api/asin-reference/analyse',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({productId:p.id})});
   const result=await response.json();if(!response.ok)throw Error(result.error);
   if(signedUser!==owner||current()!==target||target.editorAsinReference!==reference)throw Error('ASIN 资料已变化，请重新运行洞察');
   const updated={...reference,insight:result};
   target.editorAsinReference=updated;
   persist({invalidateReview:false});
   await flushWorkspace();
   return updated;
  },
  editFacts,capture:openSupplierForProduct,variants:()=>workflowShowVariants(p),
  quotes:()=>showSupplierQuotes(p),history:()=>workflowHistory(p),saveVersion:()=>{
   if(workflowSnapshot(p,'手动保存版本')){persist();toast('已保存文案版本')}
  },
  listingSkills:()=>openCreativeSkills('listing'),
  exportZip:()=>exportProductDelivery(null),openReview:()=>go('reviews'),
  submit:()=>{
   if(!checkTitleFields(draft())||String(draft().bullets||'').split(/\r?\n/).filter(line=>line.trim()).length!==5||!draft().description?.trim())
    return toast('请先填写合规的标题、亮点、五点和描述');
   p.status='制作中';
   persist();toast('已保存，继续自动处理流程');
  },
  mountTools:(element,kind)=>{
   if(kind==='research'){
    element.innerHTML='<div class="titlebar" hidden></div>';
    mountCompetitorResearch(element);
    mountBuyerInsights();
   }else if(kind==='visual'){
    element.innerHTML='<div class="notice"></div><div class="gallery"></div>';
    addAssets();
    mountImageGeneration();
    mountGeneratedGallery();
   }else mountGeneratedGallery();
   return ()=>{if(kind==='visual'){window.JunfeiVisual?.unmount();clearTimeout(colourPollTimer)}element.replaceChildren()};
  }
 };
}

render=function(){
 if(!['listing','images'].includes(view)){
  window.JunfeiProductEditor?.unmount();productEditorHost=null;
  const result=renderOutsideProductEditor();
  const actions=view==='products'&&document.querySelector('#content .titlebar .actions');
  if(actions){
   const button=document.createElement('button');button.className='btn';button.textContent='批量生成 Listing';
   button.disabled=!serverReady;button.onclick=listingBatchDialog;actions.append(button);
  }
  return result;
 }
 const p=product();if(!p)return go('products');
 selected=p.id;
 if(listingWorkspaceProduct!==p.id){listingWorkspaceProduct=p.id;listingWorkspaceStep='product'}
 if(view==='images')listingWorkspaceStep='visual';
 else if(listingWorkspaceStep==='visual')listingWorkspaceStep='copy';
 const step=listingWorkspaceStep;
 market=p.sourceImport?.market||p.market||'US';
 renderNavigation();
 document.getElementById('crumb').textContent='产品档案 / Listing 工作台 / '+editorSteps[step];
 rememberListingLocation(p,step);
 if(!productEditorHost?.isConnected){
  productEditorHost=document.createElement('div');
  productEditorHost.className='product-editor-root';
  productEditorHost.textContent='正在加载 Listing 工作台…';
  document.getElementById('content').replaceChildren(productEditorHost);
 }
 const host=productEditorHost;
 loadVisualEditor().then(()=>{
  if(host!==productEditorHost||!host.isConnected||selected!==p.id||listingWorkspaceStep!==step)return;
  window.JunfeiProductEditor.mount(host,editorContext(p,step));
 }).catch(error=>{if(host.isConnected)host.textContent=error.message});
};
