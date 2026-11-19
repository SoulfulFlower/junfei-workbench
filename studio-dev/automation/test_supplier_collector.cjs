const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../listing-workbench/extension/collector.js'),'utf8');

async function collect(photos,originals){
 const requests=[];
 const images=photos.map(p=>({...p,currentSrc:p.url,src:p.url,naturalWidth:p.width,naturalHeight:p.height,getClientRects:()=>[{}]}));
 const document={title:'女士丝绒堆堆领长袖不对称上衣商品 - 阿里巴巴',querySelectorAll:selector=>selector==='img'?images:[]};
 class FakeImage{
  set src(url){requests.push(url);queueMicrotask(()=>{
   if(originals[url]){this.naturalWidth=originals[url][0];this.naturalHeight=originals[url][1];this.onload?.();}
   else this.onerror?.();
  });}
 }
 const data=await vm.runInNewContext(source,{document,location:{href:'https://detail.1688.com/offer/123456789.html'},
  getComputedStyle:()=>({visibility:'visible'}),URL,Image:FakeImage,setTimeout,clearTimeout});
 return {data:JSON.parse(JSON.stringify(data)),requests};
}
const original='https://cbu01.alicdn.com/img/ibank/shirt.jpg';
const thumbnail=original+'_sum.jpg';

test('collects loaded original, preserving thumbnail provenance and actual dimensions',async()=>{
 const {data,requests}=await collect([{url:thumbnail,width:80,height:80}],{[original]:[1200,1200]});
 assert.deepEqual(requests,[original]);assert.deepEqual(data.images,[original]);
 const row=data.imageObservations[0];assert.equal(row.observedUrl,thumbnail);
 assert.equal(row.width,1200);assert.equal(row.height,1200);assert.equal(row.observedWidth,80);
 assert.equal(row.originalStatus,'browser_loaded_larger_original');assert.equal(row.visuallyReviewed,false);
});
test('failed original and a still-small response both preserve the observed source',async()=>{
 for(const response of [{},{[original]:[80,80]}]){
  const {data}=await collect([{url:thumbnail,width:80,height:80}],response);
  assert.deepEqual(data.images,[thumbnail]);assert.equal(data.imageObservations[0].originalStatus,'thumbnail_retained_original_unavailable');
 }
});
test('retains all observed colors and does not request full-size or untrusted images',async()=>{
 const second='https://cbu02.alicdn.com/img/ibank/blue.jpg';
 const {data,requests}=await collect([
  {url:thumbnail,width:80,height:80},{url:second,width:900,height:1200},
  {url:'https://cbu01.alicdn.com.evil.example/img/ibank/private.jpg_sum.jpg',width:80,height:80},
  {url:'https://user:password@cbu01.alicdn.com/img/ibank/private.jpg_sum.jpg',width:80,height:80},
 ],{[original]:[1200,1200]});
 assert.deepEqual(data.images,[original,second]);assert.deepEqual(requests,[original]);
});
