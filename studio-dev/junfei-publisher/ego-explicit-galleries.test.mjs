import test from 'node:test';
import assert from 'node:assert/strict';
import {ensureExplicitDraftGalleries,patchDraftGalleryPayload,draftBusinessProjection} from './ego-explicit-galleries.mjs';
import {verifyPersistedDraft} from './ego-draft-readback.mjs';
import {publishNative} from './ego-publish-native.mjs';

function fixture(){
 const images=Array.from({length:7},(_,i)=>'https://junfeikuajing.oss-cn-shenzhen.aliyuncs.com/test/'+i+'.png');
 const assets=images.map((_,i)=>({sha256:'asset'+i})),urls=Object.fromEntries(assets.map((a,i)=>[a.sha256,images[i]]));
 const input={accountId:2,productId:'test',sha256:'snapshot',store:'Test US',mode:'draft',urls,assets,masterColor:'White',goods:{parentSku:'Parent',title:'Test coat',brand:'TestBrand',manufacturer:'TestBrand',description:'First\nSecond',bullets:['one'],terms:'test'},goodsItems:['S','M','L'].map(size=>({sku:'Parent-'+size,color:'White',size,price:29,quantity:88,imageIndices:[0,1,2,3,4,5,6]})),destination:{destinationId:'US',draftId:'100',marketId:'11',erpAccountId:'123',countryCode:'US',sizeValues:{S:'s',M:'m',L:'l'}}};
 const data={id:100,uid:123,market_id:11,country_code:'US',market:{alias:input.store},sku:'Parent',title:input.goods.title,brand:'TestBrand',manufacturer:'TestBrand',price:29,quantity:88,main_image:images[0],extra:{images:[...images],attributes:{care_instructions:[{value:'Machine Wash'}]},product_description:'First<br/>Second',bullet_point:['one'],keywords:'test'},items:input.goodsItems.map((v,i)=>({id:101+i,pid:100,uid:123,sku:v.sku,price:29,quantity:88,main_image:images[0],variation:{'color.0.value':'White','apparel_size.0.size':v.size.toLowerCase()},extra:{images:null,attributes:{color:[{value:'White'}],apparel_size:[{size:v.size.toLowerCase()}]}}}))};
 const body={id:100,market_id:'11',country_code:'US',parent_sku:'Parent',sku:'Parent',title:data.title,brand:data.brand,manufacturer:data.manufacturer,price:29,quantity:88,attributes:structuredClone(data.extra.attributes),product_description:'First\nSecond',bullet_point:['one'],keywords:'test',images:[...images],items:data.items.map(v=>({id:v.id,sku:v.sku,price:29,quantity:88,attributes:structuredClone(v.extra.attributes),images:[...images]}))};
 // Observed real ERP behaviour, reproduced here without external writes.
 const persisted=payload=>{const d=structuredClone(data);d.extra.images=payload.images;for(const row of d.items){const p=payload.items.find(v=>v.sku===row.sku);row.extra.images=JSON.stringify(p.images)===JSON.stringify(payload.images)?null:p.images;row.main_image=p.main_image||images[0];}return{code:0,data:d};};
 return{input,images,body,data,persisted};
}

test('parent cover prevents ERP compaction and every size retains seven ordered images',()=>{
 const f=fixture();assert.throws(()=>verifyPersistedDraft(f.persisted(f.body),f.input,f.input.urls),/独立七图/);
 const body=patchDraftGalleryPayload(f.body,{...f.input,galleryRepairSource:f.data},f.input.urls),saved=f.persisted(body);
 assert.deepEqual(body.images,[f.images[0]]);assert.ok(body.items.every(v=>v.images.length===7));
 assert.equal(verifyPersistedDraft(saved,f.input,f.input.urls).length,3);
 assert.equal(draftBusinessProjection(saved.data),draftBusinessProjection(f.data));
});

test('image-only migration refuses foreign draft, changed price, attributes, copy or child identity',()=>{
 const f=fixture();for(const mutate of [b=>b.id=999,b=>b.parent_sku='Other',b=>b.price=1,b=>b.items[0].quantity=1,b=>b.attributes.care_instructions[0].value='Guess',b=>b.items[0].attributes.color[0].value='Blue',b=>b.title='Changed',b=>b.product_description='Changed',b=>b.items[1].id=b.items[0].id,b=>b.publish=true]){const b=structuredClone(f.body);mutate(b);assert.throws(()=>patchDraftGalleryPayload(b,{...f.input,galleryRepairSource:f.data},f.input.urls));}
});

test('legacy migration saves once, rereads actual child fields, and a repeated call is read-only',async()=>{
 const f=fixture(),record={};let state={code:0,data:f.data},writes=0;
 const adapters={read:async()=>state,save:async(_page,input,urls,r,persist,patch)=>{r.saveIntendedAt='before-send';await persist();writes++;state=f.persisted(patch(f.body,input,urls));}};
 for(let n=0;n<2;n++)await ensureExplicitDraftGalleries({},f.input,f.input.urls,record,async()=>{},adapters);
 assert.equal(writes,1);assert.equal(record.explicitGallery.status,'verified');
});

test('lost save reply reconciles persisted child galleries without sending again',async()=>{
 const f=fixture(),record={};let state={code:0,data:f.data},writes=0;
 const adapters={read:async()=>state,save:async(_page,input,urls,r,_persist,patch)=>{r.saveIntendedAt='before-send';r.requestSent=true;writes++;state=f.persisted(patch(f.body,input,urls));throw Error('lost reply');}};
 await assert.rejects(ensureExplicitDraftGalleries({},f.input,f.input.urls,record,async()=>{},adapters),/lost reply/);
 await ensureExplicitDraftGalleries({},f.input,f.input.urls,record,async()=>{},adapters);assert.equal(writes,1);
 state={code:0,data:f.data};await assert.rejects(ensureExplicitDraftGalleries({},f.input,f.input.urls,record,async()=>{},adapters),/不重复提交/);assert.equal(writes,1);
});

test('publication cannot run before persisted explicit images pass the gate',async()=>{
 const f=fixture(),record={};let submits=0;
 await assert.rejects(publishNative({},f.input,record,async()=>{},{readDraft:async()=>({code:0,data:f.data}),ensureImages:async()=>{throw Error('image migration blocked');},submit:async()=>submits++}),/image migration blocked/);
 assert.equal(submits,0);assert.equal(record.intent,undefined);
});

test('a manually re-saved inherited draft is pinned again before the one native publish',async()=>{
 const f=fixture(),record={},events=[];let state={code:0,data:f.data},submitted=false,published;
 const read=async()=>state;
 const save=async(_page,input,urls,r,persist,patch)=>{r.saveIntendedAt='before-send';await persist();events.push('save-images');state=f.persisted(patch(f.body,input,urls));};
 const adapters={readDraft:read,ensureImages:(page,input,urls,r,persist)=>ensureExplicitDraftGalleries(page,input,urls,r,persist,{read,save}),
  readiness:async()=>{assert.ok(state.data.items.every(v=>v.extra.images?.length===7));events.push('ready');return{};},
  query:async()=>submitted?[{id:200,sku:'Parent',market_id:11,country_code:'US',market:{alias:'Test US'}}]:[],
  submit:async()=>{events.push('publish');submitted=true;published=structuredClone(state);published.data.id=200;published.data.status='accepted';published.data.errors=[];published.data.items.forEach(v=>{v.pid=200;v.status='accepted';});},read:async()=>published};
 await publishNative({},f.input,record,async()=>{},adapters);
 assert.deepEqual(events,['save-images','ready','publish']);assert.equal(record.identity.imagePersistenceVerified,true);
 await publishNative({},f.input,record,async()=>{},adapters);assert.deepEqual(events,['save-images','ready','publish']);
});
