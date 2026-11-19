import test from 'node:test';
import assert from 'node:assert/strict';
import {publishNative,observePublishedNative,resolvePublicationSource,verifyPublication,publicationFailureObservation,readPublishReadiness} from './ego-publish-native.mjs';
import {copyNative,verifyCopiedDraft} from './ego-copy-native.mjs';

function fixture(){
 const urls={a:'https://media.example/a',b:'https://media.example/b'};
 const input={accountId:2,productId:'mock-product',sha256:'immutable-snapshot',store:'Exact US Store',urls,
  destination:{destinationId:'us-target',draftId:'101',marketId:'91',erpAccountId:'11',countryCode:'US',sizeValues:{S:'s',M:'m'}},
  goods:{parentSku:' Parent-Exact ',title:'Mock jacket',brand:'VerifiedBrand',manufacturer:'VerifiedBrand',description:'A\nB',bullets:['One'],terms:'mock terms'},
  assets:[{sha256:'a'},{sha256:'b'}],goodsItems:[{sku:'Exact-White-S',color:'White',size:'S',price:29,quantity:8,imageIndices:[0,1]},{sku:'Exact-White-M',color:'White',size:'M',price:29,quantity:8,imageIndices:[0,1]}],
  ukTarget:{storeName:'Exact UK Store',countryCode:'GB',currency:'GBP',languageTag:'en_GB',shippingTemplate:{name:'UK Verified'}},
  ukCommerce:{variantPrices:{'Exact-White-S':23,'Exact-White-M':23},quantities:{'Exact-White-S':8,'Exact-White-M':8},handlingDays:3,pricingBasis:'explicit'}};
 const body=(id,published=false)=>({code:0,data:{id,uid:11,market_id:91,country_code:'US',market:{alias:input.store},sku:input.goods.parentSku,title:input.goods.title,brand:'VerifiedBrand',manufacturer:'VerifiedBrand',status:published?'accepted':'unpublished',errors:[],
  extra:{images:Object.values(urls),product_description:'A<br/>B',bullet_point:['One'],keywords:'mock terms'},
  items:input.goodsItems.map((v,n)=>({id:Number(id)+n+1,pid:id,uid:11,sku:v.sku,price:29,quantity:8,status:'accepted',asin:null,
   variation:{'color.0.value':v.color,'apparel_size.0.size':input.destination.sizeValues[v.size]},main_image:urls.a,
   extra:{images:Object.values(urls),attributes:{color:[{value:v.color}],apparel_size:[{size:input.destination.sizeValues[v.size]}]}}}))}});
 const draft=body('101'),published=body('202',true),row={id:202,market_id:91,country_code:'US',market:{alias:input.store},sku:input.goods.parentSku};
 return{input,draft,published,row};
}
const sourceRows=input=>[{id:202,market_id:91,country_code:'US',market:{alias:input.store},sku:input.goods.parentSku}];
function onlineFixture(published,id='404'){
 const online=structuredClone(published);online.data.id=id;online.data.status='online';online.data.items.forEach((v,n)=>{v.pid=id;v.status='online';v.asin='REALMOCK'+n;});return online;
}

function materialAdvisoryFixture(){
 const f=fixture(),data=f.published.data;
 f.input.destination.countryCode=data.country_code='GB';
 f.input.store=data.market.alias='Exact UK Store';
 const child=data.items[1],advisory={code:'18448',severity:'WARNING',attributeNames:['material'],categories:['MISSING_ATTRIBUTE','PRODUCT'],
  message:'您提交的内容缺少一些关键属性：material。 缺少这些属性不会阻止您的商品在亚马逊上展示。 然而，这会影响您的商品信息的整体质量。'};
 data.errors.push({...advisory,sku:child.sku,solution:''});
 child.extra.message=[advisory];
 return{...f,child,advisory};
}

function familyFailureFixture(){
 const f=fixture(),sizes={S:'s',M:'m',L:'l',XL:'x_l',XXL:'xx_l','3XL':'3x_l'};
 f.input.assets=Array.from({length:7},(_,n)=>({sha256:String(n)}));f.input.urls=Object.fromEntries(f.input.assets.map((a,n)=>[a.sha256,'https://media.example/'+n+'.png']));
 f.input.destination.sizeValues=sizes;
 f.input.goodsItems=['White','Black','Brown','Gray','Red'].flatMap(color=>Object.keys(sizes).map(size=>({sku:'Exact-'+color+'-'+size,color,size,price:29,quantity:8,imageIndices:[0,1,2,3,4,5,6]})));
 const template=f.published.data.items[0],images=Object.values(f.input.urls);f.published.data.extra.images=[images[0]];
 f.published.data.items=f.input.goodsItems.map((v,n)=>({...structuredClone(template),id:203+n,sku:v.sku,main_image:images[0],
  variation:{'color.0.value':v.color,'apparel_size.0.size':sizes[v.size]},extra:{images:[...images],message:null,attributes:{color:[{value:v.color}],apparel_size:[{size:sizes[v.size]}]}}}));
 const failed=structuredClone(f.published);failed.data.status='failed';
 for(const row of failed.data.items){
  if(!['Exact-Brown-M','Exact-Brown-XXL','Exact-Gray-XXL'].includes(row.sku))continue;
  row.status='failed';const messages=row.sku.includes('Brown')?images.map(url=>({code:'300060',message:'Cannot access '+url,severity:'ERROR',sku:row.sku})):
   [{code:'18320',message:'Main image missing or incorrect',severity:'ERROR',enforcements:{actions:[{action:'SEARCH_SUPPRESSED'}]}}];
  row.extra.message=structuredClone(messages);
  failed.data.errors.push(...messages.map(message=>({...message,sku:row.sku,solution:'Native ERP guidance'})));
 }
 return{...f,failed};
}

test('failure observation joins parent errors and real child messages once while preserving all thirty identities',()=>{
 const {input,published,failed}=familyFailureFixture();assert.equal(publicationFailureObservation(published,input,'202'),null);
 assert(failed.data.items.every(row=>!Object.hasOwn(row,'errors')));
 const observation=publicationFailureObservation(failed,input,'202');
 assert.equal(observation.publishId,'202');assert.equal(observation.identityVerified,true);assert.equal(observation.status,'failed');assert.equal(observation.failed,true);
 assert.equal(observation.childCount,30);assert.equal(observation.count,3);assert.equal(observation.acceptedCount,27);assert.equal(observation.messageCount,15);
 assert.deepEqual(observation.skus,['Exact-Brown-M','Exact-Brown-XXL','Exact-Gray-XXL']);assert.equal(observation.failedChildIds.length,3);
 assert.equal(observation.acceptedChildIds.length,27);assert.equal(observation.unscopedMessageCount,0);assert.equal(observation.responseFingerprint.length,64);assert.ok(observation.observedAt);
 for(const message of observation.messages){assert.deepEqual(message.sources,['data.errors','child.extra.message']);assert.ok(message.childId);assert.ok(message.solution);}
 assert.equal(observation.messages.filter(v=>v.code==='300060').length,14);assert.equal(observation.messages.filter(v=>v.code==='18320').length,1);
 assert(observation.children.every(row=>row.asin===null&&row.images.length===7));
 const wrong=structuredClone(failed);wrong.data.uid=99;
 assert.throws(()=>publicationFailureObservation(wrong,input,'202'),error=>error.failureObservation===undefined);
 const mixed=structuredClone(failed);mixed.data.items[0].market_id=999;
 assert.throws(()=>publicationFailureObservation(mixed,input,'202'),error=>error.failureObservation===undefined);
});

test('child extra.message blocks an accepted parent even with empty parent errors and absent child.errors',()=>{
 const {input,published}=fixture(),row=published.data.items[0];row.extra.message=JSON.stringify([{code:'18320',message:'Image missing',severity:'ERROR'}]);
 assert.deepEqual(published.data.errors,[]);assert.equal(row.errors,undefined);
 assert.throws(()=>verifyPublication(published,input,'202'),error=>{
  assert.equal(error.code,'ERP_PUBLICATION_FAILED');assert.equal(error.failureObservation.status,'accepted');assert.equal(error.failureObservation.count,1);
  assert.deepEqual(error.failureObservation.skus,[row.sku]);assert.deepEqual(error.failureObservation.failedChildIds,[String(row.id)]);
  assert.deepEqual(error.failureObservation.messages[0].sources,['child.extra.message']);return true;
 });
 row.extra.message=JSON.stringify([{sku:'Foreign',code:'18320',message:'Wrong record'}]);
 assert.throws(()=>verifyPublication(published,input,'202'),error=>error.failureObservation===undefined);
});

test('the verified UK material advisory preserves the native acceptance and its durable evidence',async()=>{
 const {input,published,child}=materialAdvisoryFixture();
 published.data.status='publishing';
 const identity=verifyPublication(published,input,'202');
 assert.equal(identity.status,'publishing');assert.equal(identity.allChildrenOnline,false);
 assert.equal(publicationFailureObservation(published,input,'202'),null);
 assert.deepEqual(identity.errors,[]);assert.equal(identity.warnings.length,1);
 const [warning]=identity.warnings;
 assert.equal(warning.code,'18448');assert.equal(warning.severity,'WARNING');assert.equal(warning.sku,child.sku);
 assert.deepEqual(warning.attributeNames,['material']);assert.deepEqual(warning.sources,['data.errors','child.extra.message']);
 const record={publishId:'202',identity},saved=[];
 await observePublishedNative({},input,record,async()=>saved.push(structuredClone(record)),{
  read:async(_page,id)=>{assert.equal(id,'202');return published;},submit:async()=>assert.fail('must not submit')
 });
 assert.equal(saved.at(-1).latestObservation.failed,false);assert.deepEqual(saved.at(-1).latestObservation.warnings,identity.warnings);
 assert.deepEqual(saved.at(-1).sourceEvidence.errors,published.data.errors);
});

test('UK media errors still block while a different child with the material advisory remains accepted',()=>{
 const {input,published,child}=materialAdvisoryFixture(),failed=published.data.items[0];
 published.data.status='failed';failed.status='failed';
 published.data.errors.push(...['300060','300429'].map(code=>({sku:failed.sku,code,severity:'ERROR',message:'Image fetch failed'})));
 const result=publicationFailureObservation(published,input,'202');
 assert.equal(result.failed,true);assert.equal(result.count,1);assert.equal(result.acceptedCount,1);
 assert.deepEqual(result.failedChildIds,[String(failed.id)]);assert.deepEqual(result.acceptedChildIds,[String(child.id)]);
 assert.deepEqual(result.messages.map(message=>message.code),['18448','300060','300429']);
 assert.deepEqual(result.children[1].messages.map(message=>message.code),['18448']);
});

test('the UK material advisory cannot establish healthy child or parent status',()=>{
 const {input,published,child}=materialAdvisoryFixture();
 child.status='failed';
 const failure=publicationFailureObservation(published,input,'202');
 assert.equal(failure.count,1);assert.equal(failure.messages[0].code,'18448');
 child.status='accepted';published.data.status='failed';
 assert.equal(publicationFailureObservation(published,input,'202').failed,true);
 published.data.status='waiting';
 assert.throws(()=>verifyPublication(published,input,'202'),error=>error.code==='ERP_PUBLICATION_PENDING');
 published.data.status='accepted';
 for(const status of [undefined,'waiting','online']){
  child.status=status;assert.throws(()=>verifyPublication(published,input,'202'),/状态/);
 }
 child.asin='invalid';assert.throws(()=>verifyPublication(published,input,'202'),/状态/);
 child.asin='B000000001';assert.equal(verifyPublication(published,input,'202').status,'accepted');
});

test('unverified UK material notices and conflicting duplicate metadata remain blocking',()=>{
 for(const change of [
  ({input,published})=>{input.destination.countryCode=published.data.country_code='US';},
  ({advisory})=>{delete advisory.attributeNames;},
  ({advisory})=>{advisory.categories=['MISSING_ATTRIBUTE','INVALID_IMAGE'];},
  ({advisory})=>{advisory.code='99999';},
  ({advisory})=>{advisory.severity='ERROR';},
  ({advisory})=>{advisory.message+=' 该问题已触发展示限制。';},
  ({advisory})=>{advisory.enforcements={actions:[{action:'SEARCH_SUPPRESSED'}]};},
  ({published})=>{published.data.errors[0].enforcements=[];},
  ({advisory,published})=>{published.data.errors=[{...published.data.errors[0],enforcements:[]}];
   advisory.enforcements={actions:[{action:'SEARCH_SUPPRESSED'}]};}
 ]){
  const f=materialAdvisoryFixture();change(f);
  const result=publicationFailureObservation(f.published,f.input,'202');
  assert.equal(result.failed,true);assert.deepEqual(result.skus,[f.child.sku]);
 }
});

test('known failed publication persists its latest failure without rewriting historical acceptance or resubmitting',async()=>{
 const {input,published,failed}=familyFailureFixture(),identity=verifyPublication(published,input,'202');
 const record={publishId:'202',identity,status:'accepted',phase:'publishing_verified',sourceEvidence:structuredClone(published.data),sourceLink:{draftId:'101',publishId:'202'}},saved=[];
 const acceptedIdentity=JSON.stringify(record.identity),acceptedSource=JSON.stringify(record.sourceEvidence);
 await assert.rejects(()=>publishNative({},input,record,async()=>saved.push(structuredClone(record)),{
  read:async()=>failed,query:async()=>assert.fail('must not find a replacement'),submit:async()=>assert.fail('must not resubmit'),wait:async()=>assert.fail('terminal failure must not wait')
 }),error=>error.code==='ERP_PUBLICATION_FAILED');
 assert.equal(record.publishId,'202');assert.equal(record.phase,'publication_failed');assert.equal(record.status,'failed');assert.equal(record.currentStatus,'failed');
 assert.equal(record.latestObservation.failed,true);assert.equal(record.failureObservation.count,3);assert.equal(saved.at(-1).failureObservation.messageCount,15);
 assert.equal(JSON.stringify(record.identity),acceptedIdentity);assert.equal(JSON.stringify(record.sourceEvidence),acceptedSource);
 const originalFailure=structuredClone(record.failureObservation);
 await publishNative({},input,record,async()=>{}, {read:async()=>published,submit:async()=>assert.fail('must not resubmit')});
 assert.equal(record.phase,'publishing_verified');assert.equal(record.latestObservation.failed,false);assert.equal(record.latestObservation.verification,'accepted');
 assert.equal(record.currentStatus,'accepted');assert.deepEqual(record.failureObservation,originalFailure);
});

test('known task pending after a native family retry polls only its original ID before updating real acceptance',async()=>{
 const {input,published}=fixture(),record={publishId:'202',identity:verifyPublication(published,input,'202'),status:'accepted',phase:'publication_failed',
  sourceEvidence:structuredClone(published.data),sourceLink:{draftId:'101',publishId:'202'}};
 const pending=structuredClone(published);pending.data.status='waiting';let reads=0;const waits=[];
 await publishNative({},input,record,async()=>{}, {read:async(_page,id)=>{assert.equal(String(id),'202');return ++reads===1?pending:published;},
  query:async()=>assert.fail('must not search another task'),submit:async()=>assert.fail('must not submit'),wait:async ms=>waits.push(ms)});
 assert.equal(reads,2);assert.deepEqual(waits,[5000]);assert.equal(record.phase,'publishing_verified');assert.equal(record.latestObservation.verification,'accepted');
 reads=0;waits.length=0;
 await assert.rejects(()=>publishNative({},input,record,async()=>{}, {read:async()=>{reads++;return pending;},wait:async ms=>waits.push(ms),submit:async()=>assert.fail('must not submit')}),error=>error.code==='ERP_PUBLICATION_PENDING');
 assert.equal(reads,6);assert.equal(waits.length,5);assert.equal(record.publishId,'202');assert.equal(record.phase,'publish_pending');assert.equal(record.latestObservation.verification,'pending');
});

test('publication accepts genuine accepted task with exact identities and no online ASIN',()=>{
 const {input,published}=fixture(),proof=verifyPublication(published,input,'202');
 assert.equal(proof.publishId,'202');assert.equal(proof.status,'accepted');assert.equal(proof.allChildrenOnline,false);
 assert.equal(proof.parentSku,' Parent-Exact ');
 for(const mutate of [d=>d.data.uid=99,d=>d.data.market_id=99,d=>d.data.items[0].sku+='-UK',d=>d.data.items[0].extra.attributes.color[0].value='Blue',d=>d.data.errors=['error'],d=>d.data.status='waiting']){
  const d=structuredClone(published);mutate(d);assert.throws(()=>verifyPublication(d,input,'202'));
 }
});

test('publish persists intent before the sole write and links unique exact new task',async()=>{
 const {input,draft,published,row}=fixture(),record={},events=[];let submitted=false;
 const persist=async()=>events.push(structuredClone(record));
 const adapters={readDraft:async()=>draft,readiness:async()=>({verified:true}),query:async(_p,{section})=>submitted&&section!=='online'?[row]:[],read:async()=>published,
  submit:async()=>{assert.equal(events.at(-1).phase,'publish_unknown');assert.equal(events.at(-1).intent.draftId,'101');submitted=true;}};
 await publishNative({},input,record,persist,adapters);assert.equal(record.phase,'publishing_verified');assert.equal(record.sourceLink.draftId,'101');
 await publishNative({},input,record,persist,{...adapters,submit:async()=>assert.fail('resubmission')});
});

test('HTTP success without real task remains unknown and never submits again',async()=>{
 const {input,draft}=fixture(),record={};let writes=0;
 const api={readDraft:async()=>draft,readiness:async()=>({verified:true}),query:async()=>[],submit:async()=>{writes++;record.nativeRequests=[{response:{httpStatus:200,body:{code:0,data:null}}}];}};
 for(let n=0;n<2;n++)await assert.rejects(publishNative({},input,record,async()=>{},api),/不重复发布/);
 assert.equal(writes,1);assert.equal(record.phase,'publish_unknown');
});

test('existing same SKU task without this persisted intent blocks a new publication',async()=>{
 const {input,draft,row}=fixture();let writes=0;
 await assert.rejects(publishNative({},input,{},async()=>{},{readDraft:async()=>draft,readiness:async()=>({verified:true}),query:async()=>[row],submit:async()=>writes++}),/已有同SKU/);
 assert.equal(writes,0);
});

test('restart after lost response reconciles original unique task without another write',async()=>{
 const {input,published,row}=fixture(),record={intent:{draftId:'101',beforePublishIds:[]},phase:'publish_unknown'};
 await publishNative({},input,record,async()=>{},{query:async()=>[row],read:async()=>published,submit:async()=>assert.fail('second write')});
 assert.equal(record.publishId,'202');
});

test('only a fully verified nonterminal task produces a typed pending result',()=>{
 const {input,published}=fixture(),pending=structuredClone(published);pending.data.status='waiting';pending.data.items.forEach(v=>{v.status='waiting';v.errors=[];});
 assert.throws(()=>verifyPublication(pending,input,'202'),e=>e.code==='ERP_PUBLICATION_PENDING'&&e.publishId==='202'&&e.status==='waiting');
 for(const change of [d=>d.data.uid=99,d=>d.data.items[0].extra.attributes.apparel_size[0].size='wrong',d=>d.data.errors=['failure'],
  d=>d.data.items[0].errors=['child failure'],d=>d.data.items[0].errors='unknown error format',d=>d.data.status='failed',d=>d.data.items[0].status='rejected']){
  const altered=structuredClone(pending);change(altered);assert.throws(()=>verifyPublication(altered,input,'202'),e=>e.code!=='ERP_PUBLICATION_PENDING');
 }
});

test('one submit persists its unique candidate before waiting only on that ID until publishing',async()=>{
 const {input,draft,published,row}=fixture(),record={},events=[];let submits=0,reads=0;const waits=[];
 const waitResponse=structuredClone(published);waitResponse.data.status='waiting';waitResponse.data.items.forEach(v=>{v.status='waiting';v.errors=[];});
 const accepted=structuredClone(published);accepted.data.status='publishing';
 await publishNative({},input,record,async()=>events.push(structuredClone(record)),{
  readDraft:async()=>draft,readiness:async()=>({verified:true}),query:async(_page,{section})=>submits&&section!=='online'?[{...row,status:'waiting'}]:[],
  submit:async()=>submits++,wait:async ms=>waits.push(ms),
  read:async(_page,id)=>{assert.equal(String(id),'202');assert.equal(events.at(-1).observedCandidate.taskId,'202');assert.equal(events.at(-1).publishId,undefined);return ++reads===1?waitResponse:accepted;}
 });
 assert.equal(submits,1);assert.equal(reads,2);assert.deepEqual(waits,[5000]);assert.equal(record.publishId,'202');assert.equal(record.status,'publishing');
 assert.equal(record.observedCandidate.taskId,'202');assert.equal(record.observedCandidate.readCount,2);
});

test('candidate identity, attributes, errors and terminal failures stop immediately without retry or another submit',async()=>{
 for(const change of [d=>d.data.uid=99,d=>d.data.items[0].extra.attributes.color[0].value='Wrong',d=>d.data.errors=['failure'],
  d=>d.data.items[0].errors=['child failure'],d=>d.data.status='failed',d=>d.data.items[0].status='cancelled']){
  const {input,draft,published,row}=fixture(),record={};let submits=0,reads=0,waits=0;
  const response=structuredClone(published);response.data.status='waiting';change(response);
  await assert.rejects(()=>publishNative({},input,record,async()=>{}, {
   readDraft:async()=>draft,readiness:async()=>({verified:true}),query:async(_p,{section})=>submits&&section!=='online'?[row]:[],
   submit:async()=>submits++,read:async()=>{reads++;return response;},wait:async()=>waits++
  }),e=>e.code!=='ERP_PUBLICATION_PENDING');
  assert.equal(submits,1);assert.equal(reads,1);assert.equal(waits,0);assert.equal(record.publishId,undefined);assert.equal(record.observedCandidate.taskId,'202');
 }
});

test('bounded pending reads preserve candidate evidence and resume reads that same ID without querying a replacement',async()=>{
 const {input,draft,published,row}=fixture(),record={},saved=[];let submits=0,reads=0,queries=0;const waits=[];
 const pending=structuredClone(published);pending.data.status='waiting';pending.data.items.forEach(v=>{v.status='waiting';v.errors=[];});
 const api={readDraft:async()=>draft,readiness:async()=>({verified:true}),query:async(_p,{section})=>{queries++;return submits&&section!=='online'?[row]:[];},
  submit:async()=>submits++,read:async(_p,id)=>{reads++;assert.equal(String(id),'202');return pending;},wait:async ms=>waits.push(ms)};
 await assert.rejects(()=>publishNative({},input,record,async()=>saved.push(structuredClone(record)),api),e=>e.code==='ERP_PUBLICATION_PENDING');
 assert.equal(submits,1);assert.equal(reads,6);assert.deepEqual(waits,[5000,5000,5000,5000,5000]);assert.equal(record.publishId,undefined);
 assert.equal(record.phase,'publish_unknown');assert.equal(record.observedCandidate.taskId,'202');assert.equal(record.observedCandidate.status,'waiting');
 assert.equal(record.observedCandidate.readCount,6);assert.ok(record.observedCandidate.observedAt);assert.equal(saved.at(-1).observedCandidate.taskId,'202');
 const beforeQueries=queries;await publishNative({},input,record,async()=>{}, {...api,
  query:async()=>assert.fail('must not select a newly appearing candidate'),submit:async()=>assert.fail('must not resubmit'),
  read:async(_p,id)=>{reads++;assert.equal(String(id),'202');return published;}
 });
 assert.equal(queries,beforeQueries);assert.equal(submits,1);assert.equal(reads,7);assert.equal(record.publishId,'202');
});

test('an observed candidate cannot be replaced when its original detail is missing or returns another task',async()=>{
 const {input,published}=fixture();
 for(const read of [async()=>{throw Error('original detail unavailable');},async()=>{const other=structuredClone(published);other.data.id='404';return other;}]){
  const record={intent:{draftId:'101',beforePublishIds:[]},phase:'publish_unknown',observedCandidate:{taskId:'202',status:'waiting',observedAt:'original'}};let waits=0;
  await assert.rejects(()=>publishNative({},input,record,async()=>{}, {read,query:async()=>assert.fail('replacement search'),submit:async()=>assert.fail('resubmit'),wait:async()=>waits++}));
  assert.equal(record.observedCandidate.taskId,'202');assert.equal(record.publishId,undefined);assert.equal(waits,0);
 }
 const missingIntent={observedCandidate:{taskId:'202',status:'waiting'}};
 await assert.rejects(()=>publishNative({},input,missingIntent,async()=>{}, {readDraft:async()=>assert.fail('reopen'),submit:async()=>assert.fail('resubmit')}),/持久意图/);
});

test('copy preserves source association while exposing generated SKUs for UK correction',async()=>{
 const {input,draft,published}=fixture(),copied=structuredClone(draft);copied.data.id='303';copied.data.sku='Generated';
 copied.data.items.reverse();copied.data.items.forEach((v,n)=>{v.pid='303';v.id=304+n;v.sku='Generated-'+n;});
 const identity=verifyCopiedDraft(copied,input,published.data,'303');assert.equal(identity.mapping[0].sourceSku,'Exact-White-S');
 const record={},sourcePublication={publishId:'202',fingerprint:'US-fingerprint'};let writes=0;
 const api={readSource:async()=>published,querySourceRows:async()=>sourceRows(input),query:async()=>writes?[{id:303}]:[],read:async()=>copied,
  submit:async()=>{assert.equal(record.phase,'copy_unknown');assert.equal(record.intent.sourcePublishId,'202');writes++;}};
 await copyNative({},{source:input,target:input,sourcePublication},record,async()=>{},api);
 assert.equal(record.draftId,'303');assert.equal(record.sourceLink.sourcePublishId,'202');assert.equal(record.phase,'copy_verified');assert.equal(record.identity.copiedParentSku,'Generated');
 await copyNative({},{source:input,target:input,sourcePublication},record,async()=>{},api);assert.equal(writes,1);
 input.ukTarget.categoryHints={path:'Actual UK category selected after copy'};
 await copyNative({},{source:input,target:input,sourcePublication},record,async()=>{},api);assert.equal(writes,1);
 const changed=structuredClone(input);changed.ukTarget.storeName='Other UK store';
 await assert.rejects(copyNative({},{source:input,target:changed,sourcePublication},record,async()=>{},api),/英国目标/);
 changed.ukTarget=structuredClone(input.ukTarget);changed.ukCommerce.handlingDays=8;
 await assert.rejects(copyNative({},{source:input,target:changed,sourcePublication},record,async()=>{},api),/英国目标/);
});

test('unknown copy never repeats and will not accept unrelated images or ambiguous drafts',async()=>{
 const {input,published}=fixture(),record={};let writes=0;
 const api={readSource:async()=>published,querySourceRows:async()=>sourceRows(input),query:async()=>[],submit:async()=>writes++};
 for(let n=0;n<2;n++)await assert.rejects(copyNative({},{source:input,target:input,sourcePublication:{publishId:'202'}},record,async()=>{},api),/不重新复制/);
 assert.equal(writes,1);assert.equal(record.phase,'copy_unknown');
});

test('copied draft verification rejects wrong image order and duplicate color-size mappings',()=>{
 const {input,draft,published}=fixture();
 for(const mutate of [d=>d.data.items[0].extra.images.reverse(),d=>d.data.items[1].variation={'color.0.value':'White','apparel_size.0.size':'s'}]){
  const d=structuredClone(draft);d.data.id='303';d.data.items.forEach(v=>v.pid='303');mutate(d);
  assert.throws(()=>verifyCopiedDraft(d,input,published.data,'303'));
 }
});

test('ambiguous matching new copies remain unknown rather than selecting an arbitrary draft',async()=>{
 const {input,draft,published}=fixture(),record={intent:{sourcePublishId:'202',beforeDraftIds:[]},phase:'copy_unknown'};
 const read=async(_p,id)=>{const d=structuredClone(draft);d.data.id=id;d.data.items.forEach(v=>v.pid=id);return d;};
 await assert.rejects(copyNative({},{source:input,target:input,sourcePublication:{publishId:'202'}},record,async()=>{},{readSource:async()=>published,query:async()=>[{id:303},{id:404}],read,submit:async()=>assert.fail('write')}),/不重新复制/);
 assert.equal(record.draftId,undefined);assert.equal(record.phase,'copy_unknown');
});

test('copy source account mismatch blocks before any write or baseline query',async()=>{
 const {input,published}=fixture();published.data.uid=999;
 await assert.rejects(copyNative({},{source:input,target:input,sourcePublication:{publishId:'202'}},{},async()=>{},{readSource:async()=>published,query:async()=>assert.fail('query'),submit:async()=>assert.fail('write')}),/账号/);
});

test('already accepted publication moving online keeps original task and accepted evidence on resume',async()=>{
 const {input,published}=fixture(),identity=verifyPublication(published,input,'202'),record={publishId:'202',identity,status:'accepted',sourceEvidence:structuredClone(published.data),sourceLink:{draftId:'101',publishId:'202'}};
 const before=JSON.stringify(record.sourceEvidence),online=onlineFixture(published,'202');
 await publishNative({},input,record,async()=>{},{read:async()=>online,submit:async()=>assert.fail('resubmit')});
 assert.equal(record.publishId,'202');assert.equal(record.status,'accepted');assert.equal(record.currentStatus,'online');assert.equal(record.onlineObservation.identity.allChildrenOnline,true);
 assert.equal(JSON.stringify(record.sourceEvidence),before);assert.equal(record.identity.status,'accepted');
});

test('missing original accepted detail is reconciled to unique fully verified online row without replacing publishId',async()=>{
 const {input,published}=fixture(),identity=verifyPublication(published,input,'202'),record={publishId:'202',identity,status:'accepted',sourceEvidence:structuredClone(published.data),sourceLink:{draftId:'101',publishId:'202'}};
 const online=onlineFixture(published),row={...sourceRows(input)[0],id:404};
 await publishNative({},input,record,async()=>{},{read:async()=>{throw Error('not in publishing');},query:async()=>[row],readOnline:async()=>online,submit:async()=>assert.fail('resubmit')});
 assert.equal(record.publishId,'202');assert.equal(record.onlineObservation.recordId,'404');assert.equal(record.status,'accepted');
});

function partialOnlineFixture(){
 const {input,published,row}=fixture(),identity=verifyPublication(published,input,'202'),online=onlineFixture(published);
 const record={publishId:'202',phase:'publishing_verified',identity,status:'accepted',sourceEvidence:structuredClone(published.data),
  failureObservation:{publishId:'202',verification:'failed'},sourceLink:{draftId:'101',publishId:'202',method:'persisted_intent_unique_new_exact_identity',beforePublishIds:[]}};
 online.data.main_image='https://m.media-amazon.com/images/I/asset.jpg';
 delete online.data.errors;
 online.data.items.forEach((child,n)=>{child.asin='B00000000'+n;child.status='';});
 const api={read:async()=>{throw Error('not in publishing');},query:async(_p,query)=>{
  assert.deepEqual(query,{sku:input.goods.parentSku,section:'online'});return[{...row,id:404}];},
  readOnline:async(_p,id)=>{assert.equal(String(id),'404');return online;},submit:async()=>assert.fail('resubmission')};
 return{input,published,record,online,api,row};
}

test('explicit native observation records partial online evidence and preserves the original accepted receipt',async()=>{
 const {input,record,online,api}=partialOnlineFixture(),before=structuredClone(record),saved=[];
 assert.throws(()=>verifyPublication(online,input,'404',{allowOnline:true}),/持久父体封面不符/);
 await assert.rejects(resolvePublicationSource({},input,record,api),/持久父体封面不符/);
 await assert.rejects(publishNative({},input,structuredClone(record),async()=>{},api),/持久父体封面不符/);
 await observePublishedNative({},input,record,async()=>saved.push(structuredClone(record)),api);
 const evidence=record.onlineReadback;
 assert.deepEqual(saved[0].latestObservation,evidence);
 assert.equal(evidence.verification,'partial_online_readback');assert.equal(evidence.status,'online');assert.equal(evidence.failed,undefined);
 assert.equal(evidence.publishId,'202');assert.equal(evidence.recordId,'404');assert.equal(evidence.identityVerified,true);
 assert.equal(evidence.childCount,2);assert.equal(evidence.childrenWithAsin,2);assert.equal(evidence.childrenWithStatus,0);
 assert.equal(evidence.parentErrorsAvailable,false);assert.equal(evidence.childrenWithErrorFields,0);assert.equal(evidence.allChildrenOnline,false);
 assert.equal(evidence.originalGalleryFirstVerified,true);assert.equal(evidence.exactCoverUrl,false);assert.equal(evidence.coverContentCompared,false);
 for(const key of Object.keys(before))assert.deepEqual(record[key],before[key]);
 online.data.main_image=input.urls.a;online.data.errors=[];online.data.items[0].status='online';online.data.items[0].errors=[];
 await observePublishedNative({},input,record,async()=>{},api);
 assert.equal(record.onlineReadback.exactCoverUrl,true);assert.equal(record.onlineReadback.parentErrorsAvailable,true);
 assert.equal(record.onlineReadback.childrenWithStatus,1);assert.equal(record.onlineReadback.childrenWithErrorFields,1);
});

test('partial online readback rejects uncertain linkage, identity, gallery, or reported failures',async()=>{
 for(const change of [
  ({record})=>{record.sourceLink.publishId='999';},({record})=>{record.identity.erpAccountId='99';},
  ({record})=>{record.sourceLink.beforePublishIds=['202'];},({record})=>{record.identity.children.pop();},
  ({api,row})=>{api.query=async()=>[{...row,id:404},{...row,id:405}];},({online})=>{online.data.uid=99;},
  ({online})=>{online.data.items[0].uid=99;},({online})=>{online.data.market_id=99;},({online})=>{online.data.market.alias='Foreign';},
  ({online})=>{online.data.items[0].pid='wrong';},({online})=>{online.data.items[0].id=online.data.items[1].id;},
  ({online})=>{online.data.items[0].sku='wrong';},({online})=>{online.data.extra.images.reverse();},
  ({online})=>{online.data.main_image='https://foreign.example/images/I/asset.jpg';},({online})=>{online.data.items[0].status='failed';},
  ({online})=>{online.data.items[0].extra.message='Amazon rejected it';},({online})=>{online.data.errors=[{code:'BAD'}];},
  ({api,published})=>{published.data.uid=99;api.read=async()=>published;api.query=async()=>assert.fail('readable original cannot fall back');}
 ]){
  const f=partialOnlineFixture();change(f);
  await assert.rejects(observePublishedNative({},f.input,f.record,async()=>assert.fail('partial persisted'),f.api));
  assert.equal(f.record.onlineReadback,undefined);
 }
 const {input,api}=partialOnlineFixture();
 await assert.rejects(observePublishedNative({},input,{},async()=>assert.fail('unknown task'),api),/缺少原真实发布任务编号/);
});

test('incomplete online status cannot obscure a current failure on the original task',async()=>{
 for(const current of [{phase:'publication_failed'},{latestObservation:{verification:'failed'}},{latestObservation:{failed:true}}]){
  const {record,input,api}=partialOnlineFixture();Object.assign(record,current);
  await assert.rejects(observePublishedNative({},input,record,async()=>assert.fail('current failure must remain visible'),api),/持久父体封面不符/);
  assert.equal(record.onlineReadback,undefined);assert.equal(record.latestObservation,current.latestObservation);
  assert.deepEqual(record.failureObservation,{publishId:'202',verification:'failed'});
 }
});

test('copy after source moved online records online source separately and preserves original receipts',async()=>{
 const {input,draft,published}=fixture(),sourcePublication={publishId:'202',identity:verifyPublication(published,input,'202'),sourceLink:{draftId:'101',publishId:'202'},fingerprint:'same-source'};
 const original=JSON.stringify(sourcePublication),online=onlineFixture(published),copied=structuredClone(draft),record={};let writes=0;
 copied.data.id='303';copied.data.sku='New Generated';copied.data.items.forEach(v=>v.pid='303');
 const api={readSource:async()=>published,querySourceRows:async(_p,{section})=>section==='online'?[{...sourceRows(input)[0],id:404}]:[],readOnline:async()=>online,
  query:async()=>writes?[{id:303}]:[],read:async()=>copied,submit:async(_p,i)=>{assert.deepEqual(i.copySource,{recordId:'404',section:'online'});writes++;}};
 await copyNative({},{source:input,target:input,sourcePublication},record,async()=>{},api);
 assert.equal(record.intent.sourcePublishId,'202');assert.equal(record.intent.sourceRecordId,'404');assert.equal(record.sourcePublishId,'202');
 const sourceEvidence=JSON.stringify(record.sourceEvidence);published.data.status='publishing';
 await copyNative({},{source:input,target:input,sourcePublication},record,async()=>{},api);
 assert.equal(JSON.stringify(record.sourceEvidence),sourceEvidence);assert.equal(JSON.stringify(sourcePublication),original);assert.equal(writes,1);
});

test('readable wrong publication account never falls back to another online record',async()=>{
 const {input,published}=fixture(),record={publishId:'202',identity:verifyPublication(published,input,'202'),sourceLink:{draftId:'101'}};published.data.uid=99;
 await assert.rejects(publishNative({},input,record,async()=>{},{read:async()=>published,query:async()=>assert.fail('fallback'),submit:async()=>assert.fail('write')}),/账号/);
});

test('current UI readiness requires real allowed exemption, shipping and same handling before publication',async()=>{
 const {input,draft}=fixture();input.handlingDays=3;draft.data.extra.attributes={merchant_shipping_group:[{value:'real-template'}],supplier_declared_has_product_identifier_exemption:[{value:true}],fulfillment_availability:[{lead_time_to_ship_max_days:'3'}]};
 const ui={url:'https://www.junfeikuajing.com/#/amazon/product/101?type=draft',store:input.store,parentSku:input.goods.parentSku,brand:input.goods.brand,brandStatus:'UPC豁免：允许销售',shippingTemplate:'Real US Template',handlingDays:'3'};
 const result=await readPublishReadiness({waitForFunction:async()=>{},evaluate:async()=>ui},input,draft);assert.equal(result.shippingTemplate.id,'real-template');
 for(const override of [{brandStatus:'未申请'},{shippingTemplate:''},{handlingDays:'4'},{store:'Other'}])await assert.rejects(readPublishReadiness({waitForFunction:async()=>{},evaluate:async()=>({...ui,...override})},input,draft));
});
