const fs=await import('node:fs/promises');
const {out,save}=await import('./cyclic_browser_helpers.mjs');
async function fullVariationCapture(asin){
 const file='full-variants-'+asin+'-parsed.json',capture=JSON.parse(await fs.readFile(out+'/'+file,'utf8')),f=capture.fields;
 const dimensions=f.dimensions[0],values=f.variationValues[0],mapping=f.dimensionValuesDisplayData[0];
 if(!values.color_name?.length||!values.size_name?.length||!Object.keys(mapping).length)throw Error('Complete observed variation capture required for '+asin);
 const variants=Object.entries(mapping).map(([child,vals])=>({asin:child,...Object.fromEntries(dimensions.map((key,i)=>[key,vals[i]])),url:'https://www.amazon.com/dp/'+child}));
 return {colors:values.color_name,sizes:values.size_name,variants,parentAsin:f.parentAsin[0],capture:{url:capture.url,checkedAt:capture.checkedAt,evidence:file,scope:'all_observed_amazon_child_asins'}};
}
export async function importReviewed(task,receipt){
 const reviewed=JSON.parse(await fs.readFile(out+'/qualified-products.json','utf8')),w=task.page('p2');
 const auth=JSON.parse((await w.fetch('/api/auth/status')).body);if(auth.user?.id!==1)throw Error('Wrong library account');
 const read=await w.fetch('/api/state',{headers:{'X-Workspace-Account':'1'}});if(!read.ok)throw Error('State read failed');const before=JSON.parse(read.body),state=before.state,additions=[];
 for(const q of reviewed){
  if(!q.qualified||!(Number(q.selected_quote.profit_at_market_price_rmb)>0))throw Error('Not qualified');
  const id='IMP-US-'+q.asin,present=state.products.find(p=>p.id===id);
  if(present){if(present.cyclicSelection?.style_key!==q.style_key)throw Error('Existing ID requires reconciliation');continue;}
  if(state.products.some(p=>p.cyclicSelection?.style_key===q.style_key||p.sourceImport?.asin===q.asin))throw Error('Duplicate style/ASIN');
  const amazon=JSON.parse(await fs.readFile(out+'/detail-'+q.asin+'.json','utf8'));
  const variations=await fullVariationCapture(q.asin);
  const imageCapture=JSON.parse(await fs.readFile(out+'/collected-images-'+q.asin+'.json','utf8'));
  if(!variations.colors.every(color=>imageCapture.colors.some(c=>c.color===color&&c.gallery?.length)))throw Error('Complete color image collection required for '+q.asin);
  const referenceImages=[...new Set(imageCapture.colors.flatMap(c=>c.gallery))];
  const supplierUrl='https://detail.1688.com/offer/'+q.supplier_id+'.html';
  additions.push({id,name:q.name,cat:q.category||'服装',owner:auth.user.name,colors:variations.colors.length,sizes:variations.sizes.length,status:'待审核',color:q.color_hex||'#295643',market:'US',brand:'Generic',manufacturer:'Generic',sourceUrl:supplierUrl,colorNames:variations.colors.join(', '),sizeNames:variations.sizes.join(', '),material:q.material,dimensions:'',packageDimensions:q.dimensions_cm.join(' × ')+' cm（供应商包装信息）',packageWeight:q.weight_g+' g（供应商包装信息）',productWeight:'',packageContents:'',features:'',variationCapturePolicy:'all_amazon_colors_and_sizes',supplierCapturePolicy:'one_verified_supplier_per_product',
   sourceImport:{asin:q.asin,market:'US',amazon:{title:amazon.title,url:amazon.url,referenceImages,colorImageGalleries:imageCapture.colors,parentAsin:variations.parentAsin,variationDimensions:{colors:variations.colors,sizes:variations.sizes},variants:variations.variants,variationCapture:variations.capture},supplier:{url:supplierUrl,title:q.name,shop:q.supplier_name,price:q.purchase_rmb,images:[q.supplier_image].filter(Boolean),source:'已核对的1688公开页面',attributes:{'目标规格':q.supplier_variant,'公开销量':q.sales_raw,'起订量':q.moq_raw,'包装尺寸':q.dimensions_cm.join('×')+'cm','包装重量':q.weight_g+'g'}},importedAt:new Date().toISOString()},
   cyclicSelection:{...q,imported:true,accountId:1},selectionStatus:'已入围',pricingEstimate:q.selected_quote,copyNotes:'报价仅为配置基础情景估算，发布前复核渠道适用性、附加费及国内实际运费；文案/图片尚未生产或审核。'+q.notes});
  state.reviews??={};state.reviews[id]={copy:false,images:false,note:'选品入围已核验，生产文案和图片尚未审核。'};
 }
 await save(receipt+'-intent.json',{accountId:1,revision:before.revision,ids:additions.map(p=>p.id),checkedAt:new Date().toISOString()});
 if(additions.length){state.products.unshift(...additions);const write=await w.fetch('/api/state',{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Account':'1'},body:JSON.stringify({revision:before.revision,state})});await save(receipt+'-response.json',write);if(!write.ok)throw Error('Import returned '+write.status+'; reconcile before retry');}
 const rr=await w.fetch('/api/state',{headers:{'X-Workspace-Account':'1'}});if(!rr.ok)throw Error('Readback failed');const after=JSON.parse(rr.body);await save(receipt+'-readback.json',after);
 for(const q of reviewed){const actual=after.state.products.find(p=>p.id==='IMP-US-'+q.asin);if(!actual||actual.cyclicSelection?.style_key!==q.style_key||actual.pricingEstimate?.profit_at_market_price_rmb!==q.selected_quote.profit_at_market_price_rmb)throw Error('Readback mismatch');Object.assign(q,{imported:true,library_product_id:actual.id,library_revision:after.revision});}
 await save('qualified-products.json',reviewed);const batch=JSON.parse(await fs.readFile(out+'/batch.json','utf8'));Object.assign(batch,{qualified_count:reviewed.length,imported_count:reviewed.filter(q=>q.imported).length,status:'researching'});await save('batch.json',batch);
 await w.reload({waitUntil:'domcontentloaded',timeout:20000});console.log('LIBRARY_IMPORTED',{account:auth.user.name,revision:after.revision,added:additions.map(p=>p.id),total:reviewed.length});
}
