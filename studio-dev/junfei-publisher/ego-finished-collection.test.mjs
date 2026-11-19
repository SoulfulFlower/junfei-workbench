import test from 'node:test';
import assert from 'node:assert/strict';
import {patchDraftPayload} from './ego-finished-collection.mjs';
import {inboxPayload} from './ego-collection-inbox.mjs';
import {nativeJoinAllowed} from './ego-native-transfer.mjs';
import {verifyPersistedDraft} from './ego-draft-readback.mjs';
function fixture(){
 const urls={},assets=[];for(let n=0;n<42;n++){const sha=n.toString(16).padStart(64,'0');assets.push({sha256:sha});urls[sha]='https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/test/'+n+'.png';}
 const variants=['Beige','Black','Coffee','Gray','Pink','Red'].flatMap((color,c)=>['S','M','L','XL'].map(size=>({sku:'P-'+color+'-'+size,color,size,price:'25.64',quantity:'88',imageIndices:Array.from({length:7},(_,i)=>c*7+i)})));
 const input={mode:'draft',marketplace:'US',masterColor:'Red',handlingDays:'3',goods:{parentSku:'P',title:'Real cardigan',description:'Verified description',bullets:['one','two','three','four','five'],terms:'keywords',highlights:'Side tie',brand:'Generic',manufacturer:'Generic'},goodsItems:variants,assets,
  destination:{draftId:'123',marketId:'45',erpAssignedSku:'ALIAS',marketplaceId:'ATVPDKIKX0DER',sizeValues:{S:'s',M:'m',L:'l',XL:'x_l'}}};
 const body={id:123,market_id:'45',country_code:'US',parent_sku:'ALIAS',attributes:{material:[{value:'Unverified acrylic'}]},items:variants.map((v,i)=>({id:500+i,sku:v.sku,attributes:{pattern:[{value:'Unverified chevron'}]},images:[]}))};return{input,body,urls};
}
function withShirtMetadata(f){
 const d=f.input.destination;f.input.store='Target US';
 Object.assign(d,{countryCode:'US',schemaHash:'shirt-us-hash',variationFields:{color:'color.0.value',size:'shirt_size.0.size'},
  sizeAttributes:{size_class:'alpha',size_system:'as1'},
  sizeAttributeSchema:{field:'shirt_size',countryCode:'US',schemaHash:'shirt-us-hash',required:['size_class','size_system'],properties:{
   size:{type:'string',enum:['s','m','l','x_l']},marketplace_id:{type:'string'},
   size_class:{type:'string',enum:['alpha']},size_system:{type:'string',enum:['as1']}
  }}});
 return f;
}
function persistedPayload(p,input){return{code:0,data:{...p,sku:p.parent_sku,market:{alias:input.store},extra:{images:p.images,product_description:p.product_description,bullet_point:p.bullet_point,keywords:p.keywords},
 items:p.items.map(row=>({...row,pid:p.id,extra:{images:row.images,attributes:row.attributes}}))}};}

test('collection preserves 24 ERP item IDs, explicit sizes and seven ordered colour images without publishing',()=>{
 const{body,input,urls}=fixture();const p=patchDraftPayload(body,input,urls);
 assert.equal(p.with_publish,false);assert.equal(p.publish,false);assert.equal(p.parent_sku,'P');assert.equal(p.items.length,24);assert.equal(p.main_image,urls[input.assets[35].sha256]);
 assert.deepEqual(p.images,[p.main_image]);
 for(let i=0;i<24;i++){const v=input.goodsItems[i],item=p.items[i];assert.equal(item.id,500+i);assert.equal(item.variation['color.0.value'],v.color);assert.equal(item.variation['apparel_size.0.size'],input.destination.sizeValues[v.size]);assert.deepEqual(item.images,v.imageIndices.map(n=>urls[input.assets[n].sha256]));assert.equal(item.main_image,item.images[0]);assert.equal(item.attributes.pattern,undefined);}
 assert.equal(p.attributes.material,undefined);assert.deepEqual(body.items[0].images,[]);
});

test('schema-selected shirt_size survives draft save and persisted per-SKU readback',()=>{
 const{body,input,urls}=fixture();input.store='Target US';
 input.destination.variationFields={color:'color.0.value',size:'shirt_size.0.size'};input.destination.themeValue='COLOR/SIZE';
 const p=patchDraftPayload(body,input,urls);
 assert.equal(p.variation_theme,'COLOR/SIZE');
 for(let i=0;i<p.items.length;i++){
  const row=p.items[i],v=input.goodsItems[i];assert.equal(row.id,body.items[i].id);
  assert.equal(row.variation['shirt_size.0.size'],input.destination.sizeValues[v.size]);
  assert.equal(row.attributes.shirt_size[0].size,input.destination.sizeValues[v.size]);assert.equal(row.attributes.apparel_size,undefined);
 }
 const actual={code:0,data:{...p,sku:p.parent_sku,market:{alias:input.store},extra:{images:p.images,product_description:p.product_description,bullet_point:p.bullet_point,keywords:p.keywords},
  items:p.items.map(row=>({...row,pid:p.id,extra:{images:row.images,attributes:row.attributes}}))}};
 assert.equal(verifyPersistedDraft(actual,input,urls).length,24);
 actual.data.items[0].variation['shirt_size.0.size']='wrong';assert.throws(()=>verifyPersistedDraft(actual,input,urls));
});
test('serialized native Save keeps proven required shirt metadata for every child and removes stale template claims',()=>{
 const{body,input,urls}=withShirtMetadata(fixture());
 for(const row of body.items)row.attributes.shirt_size=[{size_class:'numeric',size_system:'foreign-system',body_type:'unverified'}];
 // Save hooks evaluate the function's source in the page, with no module scope.
 const patch=(0,eval)('('+patchDraftPayload.toString()+')'),p=patch(body,input,urls);
 for(const row of p.items){
  assert.deepEqual(row.attributes.shirt_size[0],{size:row.variation['shirt_size.0.size'],marketplace_id:input.destination.marketplaceId,size_class:'alpha',size_system:'as1'});
  assert.equal(row.attributes.pattern,undefined);assert.equal(row.attributes.shirt_size[0].body_type,undefined);
 }
 assert.equal(p.attributes.material,undefined);assert.equal(body.items[0].attributes.shirt_size[0].size_class,'numeric');
 const actual=persistedPayload(p,input);assert.equal(verifyPersistedDraft(actual,input,urls).length,24);
 for(const change of [
  a=>delete a.data.items[0].extra.attributes.shirt_size[0].size_class,
  a=>delete a.data.items[0].extra.attributes.shirt_size[0].size_system,
  a=>a.data.items[0].extra.attributes.shirt_size[0].size_class='numeric',
  a=>a.data.items[0].extra.attributes.shirt_size[0].size='m',
  a=>a.data.items[0].extra.attributes.shirt_size[0].marketplace_id='FOREIGN',
  a=>a.data.items[0].extra.attributes={}
 ]){const changed=structuredClone(actual);change(changed);assert.throws(()=>verifyPersistedDraft(changed,input,urls),/必填尺码属性/);}
});

test('size schema identity, required values and enums are checked independently before Save and during readback',()=>{
 const f=withShirtMetadata(fixture()),actual=persistedPayload(patchDraftPayload(f.body,f.input,f.urls),f.input);
 for(const change of [
  d=>d.sizeAttributeSchema.countryCode='GB',d=>d.sizeAttributeSchema.schemaHash='stale',d=>d.sizeAttributeSchema.field='apparel_size',
  d=>delete d.sizeAttributes,d=>delete d.sizeAttributes.size_class,d=>d.sizeAttributes.size_system='invented',
  d=>d.sizeAttributes.body_type='regular',d=>d.sizeAttributes.size='m',d=>d.sizeAttributes.marketplace_id='OTHER',
  d=>d.sizeAttributeSchema.required.push('body_type')
 ]){
  const input=structuredClone(f.input);change(input.destination);
  assert.throws(()=>patchDraftPayload(f.body,input,f.urls),/尺码/);
  assert.throws(()=>verifyPersistedDraft(actual,input,f.urls),/尺码/);
 }
});

test('foreign draft, store, country, publication flags, SKU changes and incomplete images stop before submission',()=>{
 for(const change of [x=>x.body.id=124,x=>x.body.market_id='other',x=>x.body.country_code='UK',x=>x.body.with_publish=true,x=>x.body.publish=true,x=>x.body.parent_sku='OTHER',x=>x.body.items.pop(),x=>x.body.items[1].sku=x.body.items[0].sku,x=>x.input.goodsItems[0].imageIndices.pop(),x=>delete x.input.destination.sizeValues.XL,x=>x.urls[x.input.assets[0].sha256]='https://untrusted.test/x.png']){const f=fixture();change(f);assert.throws(()=>patchDraftPayload(f.body,f.input,f.urls));}
});
test('real collection payload retains source, all 24 variants and colour gallery order with CNY purchase price',()=>{
 const {input,urls}=fixture();input.productId='P';input.destination.workbenchUrl='http://127.0.0.1:18775/?product=P&step=delivery';input.destination.purchaseCny='39';
 const p=inboxPayload(input,urls);assert.equal(p.source_url,input.destination.workbenchUrl);assert.equal(p.items.length,24);assert.equal(p.images.length,42);
 for(let i=0;i<24;i++){const v=input.goodsItems[i],item=p.items[i];assert.equal(item.sku,v.sku);assert.deepEqual(item.variation,{Color:v.color,Size:v.size});assert.equal(item.price,'39');assert.deepEqual(item.images,v.imageIndices.map(n=>urls[input.assets[n].sha256]));}
 assert.match(p.describe,/Search Terms\nkeywords/);delete input.destination.purchaseCny;assert.throws(()=>inboxPayload(input,urls),/人民币采购价/);
 input.destination.purchaseCny='39';input.destination.workbenchUrl='http://127.0.0.1:18775/?product=OTHER';assert.throws(()=>inboxPayload(input,urls),/来源页面身份/);
});
test('native transfer only joins once after approved replacement and never retries an uncertain result',()=>{
 const j={collectionId:'456',status:'join_intended',oldDraftRemoved:true,replacementApproved:true,zeroBeforeJoin:{rows:[]}};
 const row={id:456,join_platform:[]};assert.equal(nativeJoinAllowed(j,row),true);
 for(const status of ['join_unknown','native_join_verified'])assert.throws(()=>nativeJoinAllowed({...j,status},row),/不重发/);
 assert.equal(nativeJoinAllowed({...j,status:'join_unknown'},{...row,join_platform:['amazon']}),false);
 for(const change of [{oldDraftRemoved:false},{replacementApproved:false},{zeroBeforeJoin:{rows:['existing']}}])assert.throws(()=>nativeJoinAllowed({...j,...change},row));
 assert.throws(()=>nativeJoinAllowed(j,{id:457,join_platform:[]}));
});
test('ERP persisted readback rejects swapped gallery order, SKU mappings and wrong shop',()=>{
 const{input,urls}=fixture();input.store='Target US';
 const g=input.goods,d=input.destination;
 const actual={code:0,data:{id:123,market_id:'45',country_code:'US',market:{alias:'Target US'},sku:'P',title:g.title,brand:g.brand,manufacturer:g.manufacturer,
  extra:{product_description:g.description,bullet_point:g.bullets,keywords:g.terms,images:input.assets.map(a=>urls[a.sha256])},
  items:input.goodsItems.map((v,i)=>({id:1000+i,pid:123,sku:v.sku,variation:{'color.0.value':v.color,'apparel_size.0.size':d.sizeValues[v.size]},price:'25.64',quantity:88,main_image:urls[input.assets[v.imageIndices[0]].sha256],extra:{images:v.imageIndices.map(n=>urls[input.assets[n].sha256])}}))}};
 assert.equal(verifyPersistedDraft(actual,input,urls).length,24);
 input.goods.description='Verified first line\nVerified second line';actual.data.extra.product_description='Verified first line<br/>Verified second line';
 assert.equal(verifyPersistedDraft(actual,input,urls).length,24);
 for(const mutate of [a=>a.data.items[0].extra.images.reverse(),a=>a.data.items[0].variation['color.0.value']='Wrong',a=>a.data.items[0].variation['apparel_size.0.size']='x_l',a=>a.data.market.alias='Other shop',a=>a.data.items.pop(),a=>a.data.items[0].pid=999]){const changed=structuredClone(actual);mutate(changed);assert.throws(()=>verifyPersistedDraft(changed,input,urls));}
});
test('null child galleries block completion; exact legacy inheritance is only readable for migration',()=>{
 const{input,urls}=fixture();input.store='Target US';input.assets=input.assets.slice(0,7);input.goodsItems=input.goodsItems.slice(0,4);
 const g=input.goods,d=input.destination,images=input.assets.map(a=>urls[a.sha256]);
 const actual={code:0,data:{id:123,market_id:'45',country_code:'US',market:{alias:'Target US'},sku:'P',title:g.title,brand:g.brand,manufacturer:g.manufacturer,
  extra:{product_description:g.description,bullet_point:g.bullets,keywords:g.terms,images},
  items:input.goodsItems.map((v,i)=>({id:1000+i,pid:123,sku:v.sku,variation:{'color.0.value':v.color,'apparel_size.0.size':d.sizeValues[v.size]},price:'25.64',quantity:88,main_image:images[0],extra:{images:null}}))}};
 assert.throws(()=>verifyPersistedDraft(actual,input,urls),/独立七图/);
 const checks=verifyPersistedDraft(actual,input,urls,{allowInherited:true});assert.equal(checks.length,4);assert.ok(checks.every(c=>c.imagesSource==='parent_shared_gallery'&&c.images.length===7&&c.storedImages===null));
 for(const row of actual.data.items)row.extra.images=[...images];actual.data.extra.images=[images[0]];
 assert.ok(verifyPersistedDraft(actual,input,urls).every(c=>c.imagesSource==='child_gallery'));
 actual.data.extra.images=[...images,images[0]];assert.throws(()=>verifyPersistedDraft(actual,input,urls));
});
