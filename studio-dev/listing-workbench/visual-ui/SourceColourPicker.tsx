import {useEffect,useRef,useState} from 'react';
export type SourceColourAssociation={receiptId:string;colorKey:string;color:string;reference:string;sourceUpload:string;children:{sku:string;size:string;asin:string}[]};
type Reference={url:string;referenceType:string;sourceAsin?:string};
type Colour={key:string;color:string;listingEligible:boolean;children:unknown[];references:Reference[];issues:string[]};
async function request(path:string,data?:unknown){const response=await fetch('/api/image-engine/'+path,data===undefined?undefined:{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)});const body=await response.json();if(!response.ok)throw Error(body.error||'颜色参考图读取失败');return body;}
export default function SourceColourPicker({productId,value,disabled,onBusyChange,onSelect}:{productId:string;value:SourceColourAssociation|null;disabled:boolean;onBusyChange:(busy:boolean)=>void;onSelect:(value:SourceColourAssociation|null)=>void}){
 const [colors,setColors]=useState<Colour[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true),[attempt,setAttempt]=useState(0),[preparing,setPreparing]=useState(false);
 const serial=useRef(0),onSelectRef=useRef(onSelect);onSelectRef.current=onSelect;
 useEffect(()=>{const token=++serial.current;setColors([]);setLoading(true);setError('');setPreparing(false);onBusyChange(false);
  void request('variants?productId='+encodeURIComponent(productId)).then(body=>{if(token===serial.current)setColors(body.colors)}).catch(e=>{if(token===serial.current)setError(e.message)}).finally(()=>{if(token===serial.current)setLoading(false)});
  return()=>{serial.current++;onBusyChange(false)};
 },[productId,attempt,onBusyChange]);
 async function choose(colorKey:string,reference?:string){
  if(!colorKey){onSelectRef.current(null);return;}
  const group=colors.find(row=>row.key===colorKey);if(!group?.listingEligible||!group.references.length)return;
  const url=reference||(group.references.find(ref=>ref.referenceType==='amazon_variant_main')||group.references[0]).url;
  const token=++serial.current;setPreparing(true);onBusyChange(true);setError('');
  try{const body=await request('prepare-variant-source',{productId,colorKey,reference:url});if(token===serial.current)onSelectRef.current(body.association)}
  catch(e){if(token===serial.current)setError((e as Error).message)}
  finally{if(token===serial.current){setPreparing(false);onBusyChange(false)}}
 }
 const selected=colors.find(row=>row.key===value?.colorKey);
 return <div className="ie-source-colour">
  <label>关联颜色变体<select aria-label="关联颜色变体" value={value?.colorKey||''} disabled={disabled||loading||preparing} onChange={e=>void choose(e.target.value)}>
   <option value="">{loading?'正在读取商品颜色…':'直接选择颜色，或上传自有图片'}</option>
   {colors.map(row=><option key={row.key} value={row.key} disabled={!row.listingEligible||!row.references.length}>{row.color} · {row.children.length}个子SKU{!row.listingEligible?' · 已排除':!row.references.length?' · 缺少参考图':''}</option>)}
  </select></label>
  {selected&&selected.references.length>1&&<label>该颜色的参考图<select aria-label="该颜色的参考图" disabled={disabled||preparing} value={value?.reference||''} onChange={e=>void choose(selected.key,e.target.value)}>{selected.references.map((ref,index)=><option key={ref.url} value={ref.url}>{index+1} · {ref.referenceType==='amazon_variant_main'?'同款变体主图':'已关联商品图'}{ref.sourceAsin?' · '+ref.sourceAsin:''}</option>)}</select></label>}
  {value&&<p>已关联：{value.color} · {value.children.length}个实际子SKU。用于本次作图，正式SKU配图按整套检查结果关联。</p>}
  {preparing&&<p role="status">正在载入该颜色的原图…</p>}
  {!loading&&!colors.length&&!error&&<p>本商品尚未保存颜色变体，可先上传图片。</p>}
  {error&&<p role="alert" className="ie-error">{error} <button disabled={disabled||preparing} onClick={()=>setAttempt(v=>v+1)}>重新读取颜色</button></p>}
 </div>;
}
