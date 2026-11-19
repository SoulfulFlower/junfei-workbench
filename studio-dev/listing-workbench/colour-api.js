// HTTP and workspace synchronization boundary for the colour module.
const ColourApi={
 async json(url,options,fallback){
  const response=await fetch(url,options),data=await response.json();
  if(!response.ok){const error=Error(data.error||fallback);error.status=response.status;throw error}
  return data;
 },
 post(action,data,fallback){return this.json('/api/colours/'+action,
  {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)},fallback)},
 sets(productId){return this.json('/api/colours/sets?productId='+encodeURIComponent(productId))},
 masterView(productId){return this.json('/api/studio/view?productId='+encodeURIComponent(productId),undefined,'母版读取失败')},
 upload(file){return this.json('/api/upload',{method:'POST',body:file})},
 async bytes(url){const response=await fetch(url);if(!response.ok)throw Error('下载失败');return new Uint8Array(await response.arrayBuffer())}
};

// Existing callers retain this name; business validation remains server-side.
async function saveColourAssociation(p,action,key){
 await flushWorkspace();
 const account=signedUser?.id,before=JSON.stringify(state);
 let data;
 try{data=await ColourApi.post(action,{productId:p.id,colorKey:key,confirmed:true,revision:serverRevision},'颜色关联保存失败')}
 catch(error){if(error.status===409){syncConflict=true;showConflict()}throw error}
 if(signedUser?.id!==account)throw Error('登录账号已变化，请刷新后查看保存结果');
 if(JSON.stringify(state)!==before){syncConflict=true;syncPending=true;showConflict();throw Error('颜色关联已保存，但本页同时有其他修改，请备份后刷新核对')}
 Object.assign(p,data.product);serverRevision=data.revision;
 if(data.review){state.reviews=state.reviews||{};state.reviews[p.id]=data.review}
 basePersist();syncLabel('已保存到数据库');return data;
}
