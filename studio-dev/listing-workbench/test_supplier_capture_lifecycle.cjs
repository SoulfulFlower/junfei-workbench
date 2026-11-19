const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

test('cancelled capture stops product polling and preserves the product',async()=>{
 const messages=[],requests=[],product={id:'fixture-product',name:'Existing product'},original=JSON.stringify(product);
 const context={signedUser:{id:2},state:{products:[product]},flushWorkspace:async()=>{},
  toast:message=>messages.push(message),setInterval:()=>{},setTimeout:()=>{throw Error('cancelled capture must not keep polling')},
  fetch:async(url)=>{requests.push(url);return{ok:true,json:async()=>({status:'cancelled',message:'采集已取消，原记录已保留'})}}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync(require.resolve('./supplier-capture.js'),'utf8'),context);
 await context.captureSupplierForProduct(product,'https://detail.1688.com/offer/1001.html');
 assert.deepEqual(requests,['/api/supplier-capture/request']);
 assert.equal(messages.at(-1),'采集已取消，原记录已保留');
 assert.equal(JSON.stringify(product),original);
});
