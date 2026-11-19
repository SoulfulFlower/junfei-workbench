type ColourItem={slot:number;image?:string;status?:string;qc?:{pass?:boolean;issues?:unknown[]}};
type ColourSet={colorKey?:string;status?:string;validated?:boolean;items?:ColourItem[];skuBinding?:{status?:string};skuBindingError?:string};
type ColourGroup={key:string;color:string;ready?:boolean;listingEligible?:boolean;issues?:string[]};
export type DeliveryColours={sets:ColourSet[];colors:ColourGroup[];masterColorKey:string;masterReferenceMatches?:boolean;galleryCount?:number;errors?:{error:string}[]};
type GallerySelection={version?:number;sourceStudioProjectId?:string|null;items?:{jobId?:string;imageIndex?:number;sha256?:string}[]};
export type SelectedGalleryReadiness={productId:string;selection:GallerySelection;imageCount:number;ready:boolean;reason?:string;reviewScope?:string};
type MasterGallery={_projectId?:string;images?:{final_url?:string;render_qa?:{ready?:boolean}|null}[];set_qa?:{ready?:boolean}|null};
const completeStatuses=new Set(['done','awaiting_manual','approved']);
const checked=(item:ColourItem)=>!!item.image&&completeStatuses.has(item.status||'')&&item.qc?.pass===true&&!item.qc.issues?.length;

// Presentation gate only; the ERP snapshot remains the authority at submission.
export function colourDeliveryProgress(data?:DeliveryColours){
  if(!data)return {ready:false,totalColors:0,totalImages:0,images:0,checked:0,linked:0,rows:[],reason:'正在读取当前母版的变体套图检查…'};
  const count=data.galleryCount||7;
  const groups=data.colors.filter(group=>group.listingEligible!==false);
  const rows=groups.filter(group=>group.key!==data.masterColorKey).map(group=>{
    const sets=data.sets.filter(set=>set.colorKey===group.key),set=sets.length===1?sets[0]:undefined;
    const items=set?.items||[],images=items.filter(item=>item.image).length,passed=items.filter(checked).length;
    const complete=items.length===count&&[...items].sort((a,b)=>a.slot-b.slot).every((item,index)=>item.slot===index);
    const ready=!!group.ready&&!!set&&set.validated===true&&completeStatuses.has(set.status||'')&&complete&&passed===count&&set.skuBinding?.status==='linked';
    const state=ready?'检查通过，已关联 SKU':!group.ready?'颜色资料待补齐':sets.length>1?'同色多套冲突':!set?'尚未制作':set.status==='reviewing'?'检查中':set.status==='needs_attention'?'检查未通过':set.skuBindingError||({queued:'排队中',validating:'核对同款与颜色',generating:'制作中',local_preparing:'本地准备中',local_rendering:'本地换色中',local_paused:'本地处理已暂停'}[set.status||'']||'等待完整检查与 SKU 关联');
    return {key:group.key,color:group.color,ready,images,checked:passed,total:count,state};
  });
  const master=groups.find(group=>group.key===data.masterColorKey);
  const reason=data.errors?.length?'变体记录读取异常：'+data.errors.map(error=>error.error).join('；'):!master?.ready?'母版颜色资料未核实':data.masterReferenceMatches!==true?'母版颜色参考未匹配':rows.some(row=>!row.ready)?'变体套图尚未完整通过检查与 SKU 关联，暂不能新建 ERP 采集。':'';
  return {ready:!reason,totalColors:rows.length,totalImages:rows.length*count,images:rows.reduce((sum,row)=>sum+row.images,0),checked:rows.reduce((sum,row)=>sum+row.checked,0),linked:rows.filter(row=>row.ready).length,rows,reason};
}

export function newCollectionBlocked(ready:boolean,job?:{id:string}){return !ready&&!job?.id;}

const selectionKey=(selection:GallerySelection)=>JSON.stringify([selection?.version,selection?.sourceStudioProjectId??null,Array.isArray(selection?.items)?selection.items.map(item=>[item?.jobId,item?.imageIndex??0,item?.sha256]):null]);
export function masterDeliveryProgress(product:{id:string;generatedGallerySelection?:GallerySelection|null},gallery?:MasterGallery,selected?:SelectedGalleryReadiness){
  const selection=product.generatedGallerySelection;
  if(selection!=null){
    const items=selection.items;
    const complete=selection.version===1&&Array.isArray(items)&&items.length===7&&items.every(item=>!!item&&typeof item.jobId==='string'&&!!item.jobId&&Number.isInteger(item.imageIndex??0)&&(item.imageIndex??0)>=0&&/^[a-f0-9]{64}$/.test(item.sha256||''))&&new Set(items.map(item=>item.jobId+':'+(item.imageIndex??0))).size===7;
    const matches=!!selected&&selected.productId===product.id&&selectionKey(selected.selection)===selectionKey(selection)&&(selection.sourceStudioProjectId??null)===(gallery?._projectId??null);
    const ready=complete&&matches&&selected.ready===true&&selected.imageCount===7&&selected.reviewScope==='draft_only';
    return {imagesReady:ready,setReady:ready,ready,imageLabel:'已选母版逐图草稿审核（7 张）',setLabel:'已选母版整套草稿审核',reason:ready?'':!complete?'已选母版须保留完整 7 张已绑定哈希的图片。':matches?selected.reason||'已选母版草稿审核尚未通过。':'正在核对当前已选母版的草稿审核记录…'};
  }
  const imagesReady=gallery?.images?.length===7&&gallery.images.every(item=>!!item.final_url&&item.render_qa?.ready===true);
  const setReady=gallery?.set_qa?.ready===true;
  return {imagesReady,setReady,ready:imagesReady&&setReady,imageLabel:'母版逐图自动检查（7 张）',setLabel:'母版整套自动检查',reason:imagesReady&&setReady?'':'母版 7 张成图及整套检查尚未全部通过。'};
}
