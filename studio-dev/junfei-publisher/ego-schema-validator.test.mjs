import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
import {validateSchemaAttributes} from './ego-schema-validator.mjs';

const pythonResult=spawnSync('python',['-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true,shell:false,timeout:10000});
assert.equal(pythonResult.status,0,'Tests require the existing local Python runtime');
const input={runtime:{pythonExecutable:pythonResult.stdout.trim()}};
function fixture(){return{
 meta:{hash:'native-real-schema-hash',schema_content:{type:'object',required:['size'],additionalProperties:false,
  $defs:{values:{type:'string',enum:['s','m']}},properties:{size:{$ref:'#/$defs/values'}}}},
 records:[{id:'original-sku-s',attributes:{size:'s'}},{id:'original-sku-m',attributes:{size:'m'}}]
};}

test('standard local schema validation returns bounded proof, not an Amazon approval',()=>{
 const {meta,records}=fixture(),proof=validateSchemaAttributes(meta,records,input);
 assert.equal(proof.passed,true);assert.equal(proof.checkedCount,2);assert.equal(proof.schemaHash,meta.hash);
 assert.match(proof.schemaSha256,/^[a-f0-9]{64}$/);assert.equal(proof.scope,'standard_json_schema');assert.equal(proof.amazonApproval,false);
 assert.deepEqual(proof.errors,[]);assert(!Object.hasOwn(proof,'records'));assert(!Object.hasOwn(proof,'schema'));
 meta.schema_content=JSON.stringify(meta.schema_content);
 assert.equal(validateSchemaAttributes(meta,records,input).schemaSha256,proof.schemaSha256);
});

test('invalid attributes throw exact record/path diagnostics without an instance or enum dump',()=>{
 const {meta,records}=fixture();records[0].attributes.size='private-value';
 assert.throws(()=>validateSchemaAttributes(meta,records,input),error=>{
  assert.equal(error.schemaValidation.passed,false);assert.equal(error.schemaValidation.checkedCount,2);
  assert.deepEqual(error.schemaValidation.errors[0].path,['size']);assert.equal(error.schemaValidation.errors[0].id,'original-sku-s');
  assert(!error.message.includes('private-value'));return true;
 });
});

test('server-frozen absolute runtime and native schema identity are required',()=>{
 const {meta,records}=fixture();
 for(const bad of [{},{runtime:{}},{runtime:{pythonExecutable:'python'}},{runtime:{pythonExecutable:input.runtime.pythonExecutable+'\n'}}])assert.throws(()=>validateSchemaAttributes(meta,records,bad),/服务端冻结/);
 assert.throws(()=>validateSchemaAttributes({...meta,hash:''},records,input),/schema 标识/);
 assert.throws(()=>validateSchemaAttributes({...meta,schema_content:'{broken'},records,input),/有效 JSON/);
});

test('remote references and invalid schema fail before any draft can be saved',()=>{
 const {meta,records}=fixture();meta.schema_content.properties.size={$ref:'https://example.invalid/forbidden'};
 assert.throws(()=>validateSchemaAttributes(meta,records,input),error=>{assert.equal(error.schemaValidation.passed,false);assert.match(error.message,/local # references/);return true;});
 meta.schema_content={type:'invalid'};
 assert.throws(()=>validateSchemaAttributes(meta,records,input),error=>{assert.match(error.message,/invalid/);assert.equal(error.schemaValidation.checkedCount,0);return true;});
});

test('record errors are limited while the returned count covers the complete batch',()=>{
 const {meta}=fixture(),records=Array.from({length:31},(_,i)=>({id:'sku-'+i,attributes:{}}));
 assert.throws(()=>validateSchemaAttributes(meta,records,input),error=>{
  const p=error.schemaValidation;assert.equal(p.checkedCount,31);assert.equal(p.errors.length,10);assert.equal(p.truncated,true);return true;
 });
});

test('missing local runtime fails closed without logging subprocess stderr',()=>{
 const {meta,records}=fixture();
 assert.throws(()=>validateSchemaAttributes(meta,records,{runtime:{pythonExecutable:resolve('does-not-exist-python.exe')}}),/无法启动/);
});
