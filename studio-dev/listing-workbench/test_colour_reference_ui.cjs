const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'colour-pixel-tools.js'),'utf8'),context);
const plain=v=>JSON.parse(JSON.stringify(v));
test('reference selection handles reverse drags and clicks at image boundaries',()=>{
 assert.deepEqual(plain(context.colourSampleBox([.8,.9],[.2,.3])),[.2,.3,.8,.9]);
 const edge=plain(context.colourSampleBox([0,0],[0,0]));
 assert.equal(edge[0],0);assert.equal(edge[1],0);assert.ok(edge[2]>0&&edge[3]>0);
 assert.deepEqual(plain(context.colourSampleBox([-.2,.2],[1.2,.8])),[0,.2,1,.8]);
 assert.throws(()=>context.colourSampleBox([NaN,0],[1,1]),/取色坐标/);
});
test('restoring old recipes resets tuning instead of carrying a previous colours settings',()=>{
 const inputs=[{dataset:{tone:'saturation'},value:2},{dataset:{tone:'shadows'},value:20}];
 const outputs={saturation:{},shadows:{}};
 const root={querySelectorAll:s=>s==='[data-tone]'?inputs:[],querySelector:s=>s==='[data-curves]'?null:outputs[s.includes('saturation')?'saturation':'shadows']};
 context.loadColourTuning(root,{shadows:-8});
 assert.equal(inputs[0].value,1);assert.equal(inputs[1].value,-8);
 context.loadColourTuning(root,{});
 assert.deepEqual(plain(context.readColourTuning(root)),{saturation:1,shadows:0});
});
