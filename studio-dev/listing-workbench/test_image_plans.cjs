// No network or paid image calls: verify the actual frontend plan compiler.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const context={renderSettings(){},enhance(){},state:{copy:{}},clearTimeout(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/images.js','utf8'),context);
const plans=context.buildProductImagePlans({id:'test',name:'Cotton shirt',cat:'服装',material:'cotton',visualBrief:'Soft daylight and blue-grey backgrounds'});
assert.equal(plans.length,7);
assert.equal(new Set(plans).size,7);
for(const p of plans){assert.match(p,/PRODUCT IDENTITY LOCK/);assert.match(p,/name: Cotton shirt/);assert.match(p,/material: cotton/);assert.match(p,/Soft daylight and blue-grey/);assert.match(p,/No text/)}
assert.match(plans[0],/pure white/);assert.match(plans[0],/overriding creative styling/);
assert.match(plans[3],/Never create measurement arrows/);
assert.match(plans[5],/Do not invent any accessories or packaging/);
const refs=['a','b','c'].map((url,i)=>({value:String(i),closest(){return {querySelector(){return {getAttribute(){return url}}}}}}));
let primary='2';context.document={querySelectorAll(){return refs},querySelector(){return primary===null?null:{value:primary}}};
assert.deepEqual(Array.from(context.selectedImageReferences()),['c','a','b']);
primary='0';assert.deepEqual(Array.from(context.selectedImageReferences()),['a','b','c']);
primary=null;assert.deepEqual(Array.from(context.selectedImageReferences()),[]);
const remaining=context.remainingImageSlots([{productId:'test',slot:'白底主图',status:'completed',images:['https://example.test/image.png']},{productId:'test',slot:'生活场景图',status:'processing'}],'test');
assert.equal(remaining.length,5);
console.log('Image plans: 7 distinct prompts, product facts/style, primary ordering and remaining slots passed.');
