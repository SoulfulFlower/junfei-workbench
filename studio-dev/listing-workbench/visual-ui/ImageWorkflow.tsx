import {useState} from 'react';
import ImageEngine from './ImageEngine';
import LegacyVisualStep from './LegacyVisualStep';
import type {ListingState} from './bridge';

export default function ImageWorkflow({state}:{state:ListingState}){
 const [aplusOpen,setAplusOpen]=useState(false);
 const history=state.creativeSets.gallery?.images||[];
 const running=[...Object.values(state.jobs),...Object.values(state.renderJobs)].some(job=>job?.status==='running');
 return <section className="image-workflow">
  <div className="image-workflow-heading"><h2>商品作图</h2><p>先完成首色七图，再按真实色样制作颜色变体，逐张检查并保存。需要局部调整时使用智能修图。</p>
   <ol className="image-workflow-steps"><li><strong>1 · 首色套图</strong><span>白底1 · 细节2 · 种草3 · 尺码1</span></li><li><strong>2 · 颜色变体</strong><span>已过检母版 + 同款真实颜色照片</span></li><li><strong>3 · 检查保存</strong><span>核对结构、颜色、文字与整套差异</span></li></ol>
   <p>细节与种草分别使用原模板。三张种草图的场景、模特及展示方式不同；所有颜色共用有真实依据的尺码图。</p>
  </div>
  <ImageEngine productId={state.project.id}/>
  <details className="image-workflow-compat"><summary>历史分镜与成图 · {history.length}个图位</summary><p>历史商品分镜只在此查看。新套图统一从上方入口制作。</p>
   {running&&<p role="status">原分镜任务仍在后台运行，任务及回执继续保留。</p>}
   {history.length?<div className="ie-results">{history.map((image,index)=><figure key={index}>{image.final_url?<a href={image.final_url} target="_blank" rel="noreferrer"><img src={image.final_url} alt={`历史图位 ${index+1}`} loading="lazy"/></a>:<p>图位{index+1} · 暂无成图</p>}<figcaption>{index+1} · {image.role||image.shot_type||'历史图位'}{image.final_url&&<a href={image.final_url} download>保存原成图</a>}</figcaption><small>{image.render_qa?.ready?'原检查通过':'保留原检查状态'}</small></figure>)}</div>:<p>暂无历史商品分镜。</p>}
  </details>
  <details className="image-workflow-compat" onToggle={event=>setAplusOpen(event.currentTarget.open)}><summary>A+ 内容制作</summary>{aplusOpen&&<LegacyVisualStep state={state}/>}</details>
 </section>;
}
