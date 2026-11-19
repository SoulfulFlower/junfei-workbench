const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const test=require('node:test');
const code=fs.readFileSync(__dirname+'/product-editor.js','utf8').match(/function mergeCapturedAmazonCategory\([\s\S]*?\n\}/)[0];
const context={};vm.createContext(context);vm.runInContext(code,context);
const captured=()=>({asin:'B000000001',market:'US',category:'Women > T-Shirts',url:'https://www.amazon.com/dp/B000000001',capturedAt:'2026-11-15T00:00:00Z',categoryEvidence:{source:'amazon_wayfinding_breadcrumbs',breadcrumbs:[{name:'T-Shirts',url:'/tees?node=1044544',nodeId:'1044544'}]}});

test('same-source captured category reaches sourceImport.amazon without replacing variant or image facts',()=>{
 const variants=[{sku:'original'}],images=['original-image'],product={sourceImport:{asin:'B000000001',market:'US',amazon:{title:'Original title',variants,referenceImages:images}}};
 assert.equal(context.mergeCapturedAmazonCategory(product,captured()),true);
 assert.equal(product.sourceImport.amazon.category,'Women > T-Shirts');assert.strictEqual(product.sourceImport.amazon.variants,variants);
 assert.strictEqual(product.sourceImport.amazon.referenceImages,images);assert.equal(product.sourceImport.amazon.title,'Original title');
 assert.equal(product.sourceImport.amazon.categoryEvidence.sourceUrl,captured().url);
});

test('a different competitor, marketplace or absent breadcrumb proof cannot change the product category',()=>{
 for(const change of [value=>value.asin='B000000002',value=>value.market='UK',value=>value.category='',value=>delete value.categoryEvidence]){
  const product={sourceImport:{asin:'B000000001',market:'US',amazon:{category:'Preserved'}}},reference=captured();change(reference);
  assert.equal(context.mergeCapturedAmazonCategory(product,reference),false);assert.equal(product.sourceImport.amazon.category,'Preserved');
 }
});
