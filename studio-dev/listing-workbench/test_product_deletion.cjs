const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/import.js','utf8');
const code=source.slice(source.indexOf('async function permanentlyDeleteProduct('),source.indexOf('const navigationBeforeEmptyProducts='));
function fixture(options={}){
 const entry={product:{id:'P1',name:'fixture'}};
 const other={product:{id:'P1-US',name:'other'}};
 const messages=[],nodes={};let saves=0;
 function node(){return {style:{},children:[],append(...items){this.children.push(...items)},setAttribute(k,v){this[k]=v},close(){this.closed=true},showModal(){this.open=true}}}
 const context={state:{products:[],deletedProducts:[entry,other],copy:{'P1-US':{title:'remove'},'P1-UK':{},'P1-image-0':'remove','P1-US-UK':{title:'keep'}},reviews:{P1:{copy:true},'P1-US':{copy:true}}},
  document:{getElementById:id=>(nodes[id]||=node()),createElement:node},
  confirm(text){context.confirmText=text;return options.confirm!==false},
  toast:message=>messages.push(message),persist(p){context.persistOptions=p},render(){},
  async flushWorkspace(){saves++;if(saves===options.failAt)throw Error('offline');if(saves===2)assert.equal(messages.length,0,'Must wait for persistence before success')},
 };
 vm.createContext(context);vm.runInContext(code,context);
 return {context,entry,other,messages,nodes,button:node()};
}

async function testBulkArchive(){
 const bulkCode=source.slice(source.indexOf('let productArchiveBusy ='),source.indexOf('const navigationBeforeEmptyProducts='));
 const published={id:'p1',name:'Cardigan',sku:'CARD-1',status:'已通过',
  erpProductionDraft:{published:true,verifiedLive:true,marketplace:'US',store:'US shop',taskId:'14948099'},
  erpPublishObservation:{marketplace:'US',allChildrenOnline:true,children:[{verifiedOnline:true}]}};
 const draft={id:'p2',name:'Draft',erpProductionDraft:{published:false,marketplace:'UK'}};
 const retained={id:'p3',name:'Retained',status:'已通过'};
 const nodes={},messages=[];
 let flushed=0,persisted=0;
 function node(){return {style:{},children:[],append(...items){this.children.push(...items)},showModal(){this.open=true},close(){this.open=false}};}
 const context={state:{products:[published,draft,retained],copy:{'p1-US':{title:'Cardigan'}},reviews:{p1:{copy:true},p3:{copy:true}}},
  signedUser:{id:1},selected:'p1',structuredClone,enhance(){},updateProductTableControls(){},render(){},
  document:{getElementById:id=>(nodes[id]||=node()),createElement:node},toast:message=>messages.push(message),
  async flushWorkspace(){flushed++;},persist(options){assert.equal(options.invalidateReview,false);persisted++;}};
 vm.createContext(context);vm.runInContext(bulkCode,context);
 assert.equal(context.publishedProductRecord(draft),null);
 assert.equal(context.publishedProductRecord({...published,erpPublishObservation:{...published.erpPublishObservation,marketplace:'UK'}}),null);
 assert.equal(context.publishedProductRecord(published).market,'US');
 context.showArchiveProducts(['p1','p2']);
 assert.equal(nodes.archiveProductList.children.length,2);
 assert.match(nodes.archiveProductList.children[0].textContent,/已发布 US/);
 nodes.cancelDelete.onclick();
 await nodes.confirmDelete.onclick();
 assert.equal(persisted,0,'Cancel must not archive anything');
 context.showArchiveProducts(['p1','p2']);
 context.signedUser={id:2};
 await nodes.confirmDelete.onclick();
 assert.equal(persisted,0,'A changed account must not archive the old selection');
 context.signedUser={id:1};
 await nodes.confirmDelete.onclick();
 assert.equal(persisted,1,'One save for the whole selection');
 assert.equal(flushed,2);
 assert.deepEqual(Array.from(context.state.products,p=>p.id),['p3']);
 assert.equal(context.selected,'p3');
 assert.equal(context.state.copy['p1-US'].title,'Cardigan');
 assert.equal(context.state.reviews.p3.copy,true);
 assert.equal(context.publishedProductRecord(context.state.deletedProducts[0].product).taskId,'14948099');
 assert.match(messages[0],/已删除 2 款/);
 console.log('PASS: bulk archive preview, cancel, account guard, one save and retained publication history');
}
async function run(){
 let f=fixture({confirm:false});const before=JSON.stringify(f.context.state);
 await f.context.permanentlyDeleteProduct(f.entry,f.button);
 assert.equal(JSON.stringify(f.context.state),before);assert.equal(f.messages.length,0);
 f=fixture();f.context.state.products.push({id:'P1',status:'已通过'});
 await f.context.permanentlyDeleteProduct(f.entry,f.button);
 assert.equal(f.context.state.deletedProducts.length,2);assert.match(f.messages[0],/仍在产品档案/);
 f=fixture({failAt:1});
 await f.context.permanentlyDeleteProduct(f.entry,f.button);
 assert.equal(f.context.state.deletedProducts.length,2);assert.match(f.messages[0],/未执行/);
 f=fixture();
 // Multiple archived copies must not leave another restore path for the same product.
 f.context.state.deletedProducts.push({product:{id:'P1',name:'older archive'}});
 f.context.state.products.push({id:'active',status:'已通过'});
 await f.context.permanentlyDeleteProduct(f.entry,f.button);
 assert.equal(f.context.state.deletedProducts.length,1);
 assert.equal(f.context.state.deletedProducts[0],f.other);
 assert.deepEqual(Object.keys(f.context.state.copy),['P1-US-UK']);
 assert.deepEqual(Object.keys(f.context.state.reviews),['P1-US']);
 assert.equal(f.context.state.products[0].status,'已通过');
 assert.equal(f.context.persistOptions.invalidateReview,false);
 assert.match(f.messages[0],/已彻底删除/);assert.match(f.context.confirmText,/无法恢复/);
 f=fixture({failAt:2});
 await f.context.permanentlyDeleteProduct(f.entry,f.button);
 assert.equal(f.context.state.deletedProducts.length,1);
 assert.match(f.messages[0],/尚未确认保存/);assert.equal(f.button.disabled,false);
 f=fixture();f.context.showDeletedProducts();
 const rows=f.nodes.deletedList.children;
 assert.equal(rows.length,2);
 const buttons=rows[0].children[1].children;
 assert.deepEqual(buttons.map(b=>b.textContent),['恢复','彻底删除']);
 assert.equal(buttons[1]['aria-label'],'彻底删除产品 P1');
 console.log('PASS: permanent delete UI, cancel, active-product protection, exact cleanup, duplicate archives, save failure and confirmed success');
 // The actual persistence wrapper must leave another product's review intact.
 const enhancements=fs.readFileSync(__dirname+'/enhancements.js','utf8');
 const persistLine=enhancements.split('\n').find(line=>line.startsWith('persist=function('));
 let invalidations=0,writes=0;
 const p={basePersist(){writes++},invalidateReview(){invalidations++},serverReady:true,syncConflict:false,syncPending:false,syncTimer:null,syncLabel(){},clearTimeout(){},setTimeout(){},pushState(){}};
 vm.createContext(p);vm.runInContext(persistLine,p);
 p.persist({invalidateReview:false});assert.equal(invalidations,0);assert.equal(p.syncPending,true);
 p.persist();assert.equal(invalidations,1);assert.equal(writes,2);
 console.log('PASS: permanent removal skips unrelated review invalidation; normal edits still invalidate');
 await testBulkArchive();
}
run().catch(error=>{console.error(error);process.exitCode=1});
