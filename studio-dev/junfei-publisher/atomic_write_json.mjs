// Durable local checkpoint. Transient Windows sharing violations retry only
// replacement of the already-written local file, never an external action.
import * as realFs from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {setTimeout as realSleep} from 'node:timers/promises';

export async function writeJsonAtomic(filename,value,{fs=realFs,sleep=realSleep,attempts=10,delayMs=50}={}){
 if(typeof filename!=='string'||!filename||!Number.isInteger(attempts)||attempts<1||attempts>20||!Number.isInteger(delayMs)||delayMs<0||delayMs>1000)throw Error('Invalid local checkpoint options');
 const data=JSON.stringify(value,null,2);if(data===undefined)throw Error('Checkpoint must be JSON serializable');
 const temporary=filename+'.'+randomUUID()+'.tmp';
 const file=await fs.open(temporary,'wx');
 try{await file.writeFile(data,'utf8');await file.sync();}finally{await file.close();}
 for(let attempt=0;attempt<attempts;attempt++){
  try{await fs.rename(temporary,filename);return;}
  catch(error){
   if(!['EPERM','EBUSY','EACCES'].includes(error.code)||attempt+1>=attempts){error.checkpointTemporaryPath=temporary;throw error;}
   await sleep(delayMs);
  }
 }
}
