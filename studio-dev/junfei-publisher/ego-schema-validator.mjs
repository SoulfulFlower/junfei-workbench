// Runs beside the native ERP automation, never in page.evaluate(). It validates
// standard JSON Schema only; the proof is not an Amazon approval or publish.
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';

const helper=fileURLToPath(new URL('./validate_attributes.py',import.meta.url));
const failure=message=>new Error('原始类目 schema 检查未通过：'+message);

export function validateSchemaAttributes(meta,records,input){
 const executable=input?.runtime?.pythonExecutable;
 if(typeof executable!=='string'||!isAbsolute(executable)||/[\r\n\0]/.test(executable))throw failure('缺少服务端冻结的 Python 运行路径');
 if(typeof meta?.hash!=='string'||!meta.hash.trim())throw failure('缺少实际类目 schema 标识');
 let schema;try{schema=typeof meta.schema_content==='string'?JSON.parse(meta.schema_content):meta.schema_content;}catch{throw failure('类目 schema 不是有效 JSON');}
 if((typeof schema!=='object'||schema===null||Array.isArray(schema))&&typeof schema!=='boolean')throw failure('缺少实际类目 schema');
 const processResult=spawnSync(executable,['-X','utf8',helper],{input:JSON.stringify({schema,records}),encoding:'utf8',shell:false,windowsHide:true,timeout:20000,maxBuffer:2*1024*1024});
 if(processResult.error){if(processResult.error.code==='ETIMEDOUT')throw failure('本地检查超时，未继续保存或发布');throw failure('无法启动指定的本地验证运行环境');}
 let result;try{result=JSON.parse(processResult.stdout);}catch{throw failure('本地验证没有返回有效检查回执');}
 const proof={passed:result.passed===true,checkedCount:result.checkedCount,schemaHash:meta.hash,
  schemaSha256:createHash('sha256').update(JSON.stringify(schema)).digest('hex'),validator:'python-jsonschema-draft202012',
  scope:'standard_json_schema',amazonApproval:false,errors:Array.isArray(result.errors)?result.errors.slice(0,10):[]};
 if(result.truncated)proof.truncated=true;
 if(processResult.status!==0||!proof.passed||proof.checkedCount!==records?.length||proof.errors.length){
  const summary=proof.errors.slice(0,10).map(error=>`${String(error.id??'schema').slice(0,120)} /${(error.path||[]).join('/').slice(0,120)}: ${String(error.message||'invalid').slice(0,240)}`).join('; ');
  const error=failure(summary||'验证未完成');error.schemaValidation=proof;throw error;
 }
 return proof;
}
