import {useEffect,useRef,useState} from 'react';
import type {CreativeSets,Job,Plan} from './types';
type Notify=(tone:'success'|'warn'|'error'|'info',message:string)=>void;
export interface BridgeContext {productId:string;name:string;market:string;prepare:()=>Promise<void>;listing:Record<string,string>}
declare global {interface Window {junfeiStudioContext?:BridgeContext;JunfeiVisual?:{mount:(element:HTMLElement,context:BridgeContext)=>void;unmount:()=>void};}}
async function request(action:string,data?:unknown){const response=await fetch('/api/studio/'+action,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});const result=await response.json();if(!response.ok)throw Error(result.error||'工作台请求失败');return result;}
export function useBridge(context:BridgeContext,notify:Notify){
 const [creativeSets,setCreativeSets]=useState<CreativeSets>({}),[jobs,setJobs]=useState<Record<string,Job>>({}),[renderJobs,setRenderJobs]=useState<Record<string,Job>>({});
 const [insightVersion,setInsightVersion]=useState('');
 const [automaticProductSource,setAutomaticProductSource]=useState<boolean>();
 const [loading,setLoading]=useState(true),[loadError,setLoadError]=useState('');
 const [readAttempt,setReadAttempt]=useState(0);
 const retryView=()=>{setLoading(true);setReadAttempt(value=>value+1);};
 const [model,setModel]=useState('gpt-image-2'),[resolution,setResolution]=useState('2K'),[autoRepair,setAutoRepair]=useState(true);
 const [models,setModels]=useState<string[]>([]);const dirty=useRef(false),saving=useRef<Promise<boolean>|null>(null);const setsRef=useRef(creativeSets);setsRef.current=creativeSets;
 const refresh=async()=>{const d=await request('view?productId='+encodeURIComponent(context.productId));setCreativeSets(d.sets);setJobs(d.jobs);setRenderJobs(d.renderJobs);setInsightVersion(d.materialInsightVersion||'');setAutomaticProductSource(d.automaticProductSource===true);return d;};
 useEffect(()=>{let alive=true;const tick=async()=>{try{const d=await request('view?productId='+encodeURIComponent(context.productId));if(!d.sets||!d.jobs||!d.renderJobs)throw Error('视觉记录格式不完整，请重新读取');if(alive){setCreativeSets(old=>{if(dirty.current || saving.current)return old;return d.sets});setJobs(d.jobs);setRenderJobs(d.renderJobs);setInsightVersion(d.materialInsightVersion||'');setAutomaticProductSource(d.automaticProductSource===true);setLoadError('')}}catch(error){if(alive)setLoadError((error as Error).message)}finally{if(alive)setLoading(false)}};void tick();const timer=setInterval(tick,5000);fetch('/api/image/settings').then(r=>r.json()).then(d=>{if(alive&&Array.isArray(d.models)){setModels(d.models);if(d.models.length)setModel(d.models.includes('gpt-image-2')?'gpt-image-2':d.models[0])}}).catch(()=>{});return()=>{alive=false;clearInterval(timer)};},[context.productId,readAttempt]);
 async function action(name:string,data:Record<string,unknown>){try{if(loading||loadError)throw Error('请先成功读取已有视觉记录，再执行制作操作');const result=await request(name,{productId:context.productId,...data});await refresh();return result;}catch(error){notify('error',(error as Error).message);throw error;}}
 const runPlan=async(params:{target_count:number;deliverable:string;visual_tone:string;language:string;brief:string})=>{
  if(automaticProductSource===false){notify('warn','请重启工作台服务以启用自动取图');return;}
  if(!confirm('工作台优先使用商品白底图，缺少时使用已核对的本款 ASIN 主图。AI 将识别商品并策划整套分镜。策划使用模型额度，图片生成需另行确认。重新策划会创建新版本并保留历史，是否继续？'))return;
  try{await context.prepare()}catch(error){notify('error',(error as Error).message);return;}
  try{await action('plan',params);notify('info','策划已在后台开始，可以离开页面');}catch{}
 };
 async function render(deliverable:string,indices:number[],reviewCompleteSet=false){if(!indices.length)return;if(saving.current && !await saving.current)return;if(dirty.current){notify('warn','请先完成当前输入并保存，再生成图片');return;}const max=indices.length*(autoRepair?2:1);if(!confirm(`请先核对分镜事实、图上文案及主体图。确认后生成${indices.length}张，每张调用当前图片服务并用视觉模型质检。${autoRepair?'每张失败最多自动重画1次，最多'+max+'次图片生成。':'不自动重画。'}${reviewCompleteSet?'整套单图通过后将自动复核整套。':''}按服务商价格计费，是否继续？`))return;try{await action('render',{deliverable,projectId:setsRef.current[deliverable as 'gallery'|'aplus']?._projectId,indices,confirmed:true,autoRepair,reviewCompleteSet,config:{model,size:deliverable==='aplus'?'16:9':'1:1',resolution}});notify('info','已提交后台制作，任务与质检会持续更新');}catch{}}
 const runRenderImage=async(deliverable:string,index:number)=>render(deliverable,[index]);
 const runRenderSet=async(deliverable:string,onlyMissing=false)=>{const p=setsRef.current[deliverable as 'gallery'|'aplus'];if(!p)return;const images=p.images;const blocked=images.filter((i:any)=>['submitting','generating','reviewing','repairing','submit_unknown','interrupted'].includes(i._status));if(blocked.length){notify('warn','存在进行中或提交状态不明的图片，请先查看任务记录，避免重复计费');return;}const indices=images.map((_,i)=>i).filter(i=>!onlyMissing||!images[i].final_url);await render(deliverable,indices,true);};
 const runReviewSet=async(deliverable:string)=>{if(!confirm('将整套成图发送给视觉模型复核色系、外观和叙事一致性，产生模型调用费用，是否继续？'))return;try{await action('review-set',{deliverable});}catch{}};
 const applyPlan=(deliverable:string,p:Plan)=>{dirty.current=true;setCreativeSets(old=>({...old,[deliverable]:p}));};
 const persistPlan=async(deliverable:string,p:Plan)=>{const previous=saving.current;const pending=(async()=>{if(previous)await previous;try{const before=setsRef.current[deliverable as 'gallery'|'aplus'] as any;const d=await request('save',{productId:context.productId,projectId:before?._projectId,plan:p});dirty.current=false;await refresh();notify('success',d.message||'已保存');return true;}catch(error){notify('error',(error as Error).message);dirty.current=false;await refresh();return false;}})();saving.current=pending;try{await pending;}finally{if(saving.current===pending)saving.current=null;}};
 const project={id:context.productId,asin:context.productId,marketplace:context.market};
 return {project,creativeSets,jobs,renderJobs,automaticProductSource,loading,loadError,retryView,scrape:{summary:{title:context.name}},analysis:{text:insightVersion},copyResult:{titles:context.listing.title?[context.listing.title]:[]},runPlan,runRenderImage,runRenderSet,runReviewSet,persistPlan,applyPlan,model,setModel,models,resolution,setResolution,autoRepair,setAutoRepair};
}
export type ListingState=ReturnType<typeof useBridge>;
