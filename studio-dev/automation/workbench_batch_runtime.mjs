// Current-page workbench API batching. The supplier service owns navigation,
// FIFO, 90-second throttling, CAPTCHA pauses and result reuse.
const fs=await import('node:fs/promises');
const path=await import('node:path');
const crypto=await import('node:crypto');
const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
async function persist(file,value){const temporary=file+'.'+crypto.randomUUID()+'.tmp';await fs.writeFile(temporary,JSON.stringify(value,null,2),'utf8');await fs.rename(temporary,file);}

export function assertIdentity(plan,space,url){
 if(!space||space.id!==plan.workbench.id||space.name!==plan.workbench.name||space.ownership!=='agent')throw Error('原专属工作台已丢失或控制权变化；停止，不接管或重建');
 if(new URL(url).origin!=='http://127.0.0.1:18775')throw Error('当前页面不是已确认的本地工作台');
}

export function requests(plan){
 if(!['status','supplier-add','observe'].includes(plan.action)||!Number.isSafeInteger(plan.accountId)||plan.accountId<1)throw Error('批处理动作无效');
 for(const url of plan.suppliers)if(!/^https:\/\/detail\.1688\.com\/offer\/[1-9]\d*\.html$/.test(url))throw Error('货源URL无效');
 for(const id of plan.jobs)if(!/^[a-f0-9]{32}$/.test(id))throw Error('原任务ID无效');
 return [{key:'queue',url:'/api/supplier-capture/status'},
  ...plan.suppliers.map(url=>({key:'supplier:'+url,url:'/api/supplier-capture/result',body:{url}})),
  ...plan.jobs.map(id=>({key:'job:'+id,url:'/api/publication/status?id='+id}))];
}

export function assertObserveScope(job,id,accountId){
 if(!job||job.id!==id||(job.accountId!==undefined&&job.accountId!==accountId)||!job.usPublishId||!job.ukPublishId||job.canObserveLatestReceipts!==true||['queued','running'].includes(job.status))throw Error('原任务双站编号、账号或只读刷新条件不符；不继续、不发布');
}

export async function run(plan){
 const report={runId:plan.runId,at:new Date().toISOString(),action:plan.action,accountId:plan.accountId,reads:{},actions:[]};
 let lock;
 const lockPath=path.join(plan.outputDirectory,'account-'+plan.accountId+'.lock');
 try{
  const reads=requests(plan);
  lock=await fs.open(lockPath,'wx');await lock.writeFile(JSON.stringify({runId:plan.runId,at:report.at}));
  const space=(await listTaskSpaces()).find(s=>s.id===plan.workbench.id);
  const task=space?await taskSpace(space.id):null;
  if(!task)throw Error('原工作台空间不存在，不自动新建');
  if(!(await task.pages()).some(p=>p.label===plan.workbench.page))throw Error('原工作台页面不在，不自动采用其他页面');
  const page=task.page(plan.workbench.page);assertIdentity(plan,space,await page.url());
  const call=async(spec)=>{
   const response=await page.fetch(spec.url,{headers:{'Content-Type':'application/json','X-Workspace-Account':String(plan.accountId)},...(spec.body?{method:'POST',body:JSON.stringify(spec.body)}:{}),timeout:45000});
   let body;try{body=JSON.parse(response.body);}catch{throw Error('工作台响应不是JSON：'+spec.url);}
   return {ok:response.ok,status:response.status,body};
  };
  const auth=await call({url:'/api/auth/status'});
  if(!auth.ok||auth.body?.user?.id!==plan.accountId)throw Error('当前真实登录账号不符，停止批处理');
  report.auth={accountId:auth.body.user.id,username:auth.body.user.username};
  // Four concurrent reads at most; each result is retained, including failures.
  for(let start=0;start<reads.length;start+=4){const batch=reads.slice(start,start+4),settled=await Promise.allSettled(batch.map(call));for(let i=0;i<batch.length;i++)report.reads[batch[i].key]=settled[i].status==='fulfilled'?settled[i].value:{ok:false,error:String(settled[i].reason)};}
  await persist(plan.resultFile,report);
  if(plan.action==='supplier-add'){
   for(const url of plan.suppliers){
    const cached=report.reads['supplier:'+url];
    if(cached?.ok&&cached.body?.id){report.actions.push({url,reused:true,captureId:cached.body.id,status:cached.body.status});continue;}
    const journal=path.join(plan.outputDirectory,'supplier-'+digest([plan.accountId,url])+'.json');let old;
    try{old=JSON.parse(await fs.readFile(journal,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
    if(old){report.actions.push({url,reconciliationOnly:true,originalIntent:old});continue;}
    const intent={accountId:plan.accountId,url,runId:plan.runId,state:'request_unknown',intendedAt:new Date().toISOString()};
    // Exclusive durable intent before the queue request; no automatic replay.
    const file=await fs.open(journal,'wx');try{await file.writeFile(JSON.stringify(intent,null,2));await file.sync();}finally{await file.close();}
    const result=await call({url:'/api/supplier-capture/request',body:{url}});report.actions.push({url,result});
    if(!result.ok)throw Error('货源队列请求未确认；保留原意图，先对账');
    await persist(journal,{...intent,state:'request_returned',result});await persist(plan.resultFile,report);
   }
  }else if(plan.action==='observe'){
   const id=plan.jobs[0];if(plan.jobs.length!==1)throw Error('一次只刷新一个原双站刊登');
   const original=report.reads['job:'+id];if(!original?.ok)throw Error('未取得原任务状态');assertObserveScope(original.body.job,id,plan.accountId);
   const intent={id,confirmed:true,observeOnly:true};report.observeIntent=intent;await persist(plan.resultFile,report);
   const result=await call({url:'/api/publication/continue',body:intent});report.actions.push({id,result});if(!result.ok)throw Error('原任务观察未确认；查看回执，不自动再次调度');
  }
 }catch(error){report.error=String(error.message||error);}
 finally{await persist(plan.resultFile,report);if(lock){await lock.close();await fs.unlink(lockPath);}}
 console.log(JSON.stringify({runId:report.runId,action:report.action,resultFile:plan.resultFile,reads:Object.fromEntries(Object.entries(report.reads).map(([key,value])=>[key,{ok:value.ok,status:value.status,state:value.body?.status||value.body?.job?.status,phase:value.body?.job?.phase,captureId:value.body?.id,paused:value.body?.paused,usFailure:value.body?.job?.usFailure,ukObservation:value.body?.job?.ukPublicationObservation,error:value.error||value.body?.error||value.body?.job?.error}])),actions:report.actions,error:report.error},null,2));
 return report;
}
