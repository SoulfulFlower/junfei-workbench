const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/publication-tasks.js','utf8').split('/* Publication ledger')[0];
function fixture(){
 const ctx=vm.createContext({signedUser:{id:2},Date,Set,Map,JSON,setTimeout,clearTimeout});vm.runInContext(source,ctx);
 const product={id:'p1',sku:'PARENT',market:'US',status:'制作中',erpPublication:{recordId:'1234',status:'accepted',store:'US Store',allChildrenOnline:false,children:[{sku:'PARENT-S',status:'accepted'},{sku:'PARENT-M',status:'accepted'}]}};
 return{ctx,product};
}
test('ERP accepted publication completes the archive before retail visibility, without rewriting review or status',()=>{
 const {ctx,product}=fixture(),before=JSON.stringify(product);
 assert.equal(ctx.productDisplayStatus(product),'已完成');
 assert.equal(ctx.productCompletionRecord(product).verifiedLive,false);
 assert.equal(JSON.stringify(product),before);
});
test('draft-only, failed, uncertain, foreign account/product/SKU and missing receipts never complete',()=>{
 const f=fixture();
 for(const change of [p=>delete p.erpPublication,p=>p.erpPublication.recordId='',p=>p.erpPublication.status='draft',p=>p.erpPublication.status='failed',p=>p.erpPublication.status='uncertain',p=>p.erpPublication.accountId=3,p=>p.erpPublication.productId='foreign',p=>p.erpPublication.parentSku='foreign',p=>p.erpPublication.children[0].status='failed',p=>p.erpPublication.children[0].sku='Other-S']){
  const p=structuredClone(f.product);change(p);p.erpCollection={status:'verified',draftId:'123'};assert.equal(f.ctx.productDisplayStatus(p),'制作中');
 }
});
test('retired manual-review statuses become in progress, not fake completed',()=>{
 const {ctx}=fixture();for(const status of ['待审核','待质检','已通过','已完成'])assert.equal(ctx.productDisplayStatus({id:'p',status}),'制作中');
});
test('formal US/UK job completion is account and SKU scoped and requires both real task IDs',()=>{
 const {ctx}=fixture(),product={id:'p1',sku:'PARENT',status:'制作中'};
 vm.runInContext("productPublicationOwner=2;productPublicationJobs=[{productId:'p1',parentSku:'PARENT',status:'submitted',publishSubmitted:true,usPublishId:'100',ukPublishId:'200'}]",ctx);
 assert.equal(ctx.productDisplayStatus(product),'已完成');
 ctx.signedUser={id:3};assert.equal(ctx.productDisplayStatus(product),'制作中');
 ctx.signedUser={id:2};vm.runInContext("productPublicationJobs[0].status='needs_reconciliation'",ctx);assert.equal(ctx.productDisplayStatus(product),'需修改');
 vm.runInContext("productPublicationJobs[0].status='submitted';productPublicationJobs[0].ukPublishId=''",ctx);assert.equal(ctx.productDisplayStatus(product),'制作中');
});
test('current production failures mark needs changes without rewriting product or creating manual review work',()=>{
 const {ctx}=fixture(),product={id:'p1',sku:'PARENT',status:'制作中'},before=JSON.stringify(product);
 vm.runInContext("productPublicationOwner=2;productProductionProgress=[{productId:'p1',parentSku:'PARENT',needsAttention:true}]",ctx);
 assert.equal(ctx.productDisplayStatus(product),'需修改');assert.equal(JSON.stringify(product),before);
 ctx.signedUser={id:3};assert.equal(ctx.productDisplayStatus(product),'制作中');
 ctx.signedUser={id:2};assert.equal(ctx.productDisplayStatus({...product,sku:'OTHER'}),'制作中');
 vm.runInContext("productProductionProgress[0].needsAttention=false",ctx);
 assert.equal(ctx.productDisplayStatus(product),'制作中');
});
test('real publication receipt takes priority over older production failures',()=>{
 const {ctx,product}=fixture();
 vm.runInContext("productPublicationOwner=2;productProductionProgress=[{productId:'p1',parentSku:'PARENT',needsAttention:true}]",ctx);
 assert.equal(ctx.productDisplayStatus(product),'已完成');
});

test('later failure of an accepted formal task blocks stale single-market completion without changing its history',()=>{
 const {ctx,product}=fixture(),before=JSON.stringify(product);
 vm.runInContext(`productPublicationOwner=2;productPublicationJobs=[{
  productId:'p1',parentSku:'PARENT',status:'needs_reconciliation',publishSubmitted:false,
  usPublishId:'1234',ukPublishId:null,
  usPublicationObservation:{publishId:'1234',status:'failed',failed:true,verification:'failed',count:3}
 }]`,ctx);
 assert.equal(ctx.productCompletionRecord(product),null);
 assert.equal(ctx.productDisplayStatus(product),'需修改');
 assert.equal(JSON.stringify(product),before);
});

test('actual latest failure overrides a stale submitted job and both saved task numbers',()=>{
 const {ctx,product}=fixture();
 vm.runInContext(`productPublicationOwner=2;productPublicationJobs=[{
  productId:'p1',parentSku:'PARENT',status:'submitted',publishSubmitted:true,
  usPublishId:'1234',ukPublishId:'2000',
  usPublicationObservation:{publishId:'1234',status:'failed',failed:true,verification:'failed'}
 }]`,ctx);
 assert.equal(ctx.productCompletionRecord(product),null);
 assert.equal(ctx.productDisplayStatus(product),'需修改');
});

test('an accepted US receipt alone cannot finish its original formal US UK job while UK is unfinished',()=>{
 const {ctx,product}=fixture();
 vm.runInContext(`productPublicationOwner=2;productPublicationJobs=[{
  productId:'p1',parentSku:'PARENT',status:'running',publishSubmitted:false,
  usPublishId:'1234',ukPublishId:null,
  usPublicationObservation:{publishId:'1234',status:'publishing',failed:false,verification:'accepted'}
 }]`,ctx);
 assert.equal(ctx.productCompletionRecord(product),null);
 assert.equal(ctx.productDisplayStatus(product),'制作中');
});

test('task failures from another account product or SKU cannot suppress a legitimate historical receipt',()=>{
 for(const changes of [{owner:3},{productId:'foreign'},{parentSku:'OTHER'},{usPublishId:'9999'}]){
  const {ctx,product}=fixture(),job={productId:'p1',parentSku:'PARENT',status:'needs_reconciliation',usPublishId:'1234',...changes};
  ctx.failureFixture=job;
  vm.runInContext(`productPublicationOwner=failureFixture.owner||2;productPublicationJobs=[failureFixture]`,ctx);
  assert.equal(ctx.productDisplayStatus(product),'已完成');
 }
});

test('later accepted observations let the same original task complete after recovery',()=>{
 const {ctx,product}=fixture();
 vm.runInContext(`productPublicationOwner=2;productPublicationJobs=[{
  productId:'p1',parentSku:'PARENT',status:'submitted',publishSubmitted:true,
  usPublishId:'1234',ukPublishId:'2000',
  usPublicationObservation:{publishId:'1234',status:'accepted',failed:false,verification:'accepted'},
  ukPublicationObservation:{publishId:'2000',status:'publishing',failed:false,verification:'accepted'}
 }]`,ctx);
 assert.equal(ctx.productDisplayStatus(product),'已完成');
 assert.equal(ctx.productCompletionRecord(product).ukTaskId,'2000');
});

test('legacy publication observes latest failure but preserves a recovered latest accepted observation',()=>{
 const {ctx,product}=fixture(),p=product.erpPublication;
 p.failureObservation={publishId:'1234',status:'failed',failed:true,verification:'failed'};
 assert.equal(ctx.productCompletionRecord(product),null);
 p.latestObservation={publishId:'1234',status:'accepted',failed:false,verification:'accepted'};
 assert.equal(ctx.productDisplayStatus(product),'已完成');
 p.latestObservation={publishId:'1234',status:'queued',failed:false};
 assert.equal(ctx.productCompletionRecord(product),null);
 p.latestObservation={publishId:'1234',status:'accepted',failed:false,verification:'unknown'};
 assert.equal(ctx.productCompletionRecord(product),null);
});

test('legacy production receipt cannot bypass the later failure of its same formal task',()=>{
 const {ctx}=fixture(),product={id:'p1',sku:'PARENT',status:'已完成',
  erpProductionDraft:{published:true,verifiedLive:true,marketplace:'US',taskId:'1234'},
  erpPublishObservation:{marketplace:'US',allChildrenOnline:true}};
 assert.equal(ctx.productDisplayStatus(product),'已完成');
 vm.runInContext(`productPublicationOwner=2;productPublicationJobs=[{
  productId:'p1',parentSku:'PARENT',status:'needs_reconciliation',usPublishId:'1234',
  usPublicationObservation:{publishId:'1234',status:'failed',failed:true,verification:'failed'}
 }]`,ctx);
 assert.equal(ctx.productCompletionRecord(product),null);
 assert.equal(ctx.productDisplayStatus(product),'需修改');
});
