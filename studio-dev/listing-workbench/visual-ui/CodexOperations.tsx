import {useEffect, useState} from 'react';

type Authority={stopAfter:string; costBasis:string; writesErp:boolean; authorizesPublication:boolean};
type Evidence={path:string; digest:string; decision:string};
type Action = {type:string; label:string; authority:Authority; target:Record<string,string|number>};
type Proposal = {
  handoffStage?:string; resolution?:{reference:string};
  request:{requestId:string; revision:number; type:string; target:Action['target']; parameters:Record<string,string|number>};
  status:string; label:string; expiresAt:number; jobId?:string; message?:string; authority?:Authority; assignment?:{inputs:Record<string,unknown>}; review?:{note:string; evidence:(Evidence|string)[]};
};
type Status = {amounts:{estimatedMarketProfitCny:string|null; textBudgets:{taskId:string;budgetCny:number}[]; productImageCosts:{reservationId:string;quoteCurrency:string;quoteMaximum:string|null;reservedFen:number;settledFen:number|null}[];externalBillCny:number|null};revision:number; stage:string; blockers:string[]; actions:Action[]; proposals:Proposal[]};
type Props = {
  productId:string; market:string; accountId:number; online:boolean;
  beforeApproval:()=>Promise<void>; openTasks:()=>void;
};
const proposalLabels:Record<string,string> = {
  pending:'待确认', dispatching:'已记录执行意图，核对原任务', needs_review:'需核对', dispatched:'已交给后端任务',
  expired:'已过期', declined:'已拒绝', not_submitted:'已核实未提交',
  assigned:'等待 Agent 核对', blocked:'Agent 报告资料有缺口',
  stale:'资料已更新，需重新派单', requires_assignment:'旧申请，请由工作台重新派单',
};

function scopeText(scope:Authority) {
  return [scope.stopAfter,scope.costBasis,scope.writesErp?'可写 ERP 草稿':'',scope.authorizesPublication?'授权发布':'无发布授权'].filter(Boolean).join(' · ');
}
function observedValue(inputs:unknown,path:string) {
  let value=inputs;
  for(const key of path.slice(1).split('/')){
    if(typeof value!=='object'||value===null)return '';
    value=(value as Record<string,unknown>)[key.replace(/~1/g,'/').replace(/~0/g,'~')];
  }
  return JSON.stringify(value);
}

export default function CodexOperations({productId,market,accountId,online,beforeApproval,openTasks}:Props) {
  const [expanded,setExpanded]=useState(false);
  const [status,setStatus]=useState<Status>();
  const [token,setToken]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [refresh,refreshStatus]=useState(0);
  const [budget,setBudget]=useState('');
  const [asins,setAsins]=useState('');
  async function api(path:string, options:RequestInit={}) {
    const response=await fetch('/api/codex/'+path,{
      ...options,
      headers:{'Content-Type':'application/json','X-Workspace-Account':String(accountId)},
    });
    const result=await response.json();
    if(!response.ok)throw Error(result.error||'工作台操作读取失败');
    return result;
  }
  useEffect(()=>{
    if(!online||!expanded)return;
    const controller=new AbortController();
    void api('status?'+new URLSearchParams({productId,market}),{signal:controller.signal}).then(result=>{
      if(!controller.signal.aborted){setStatus(result);setError('');}
    }).catch(error=>{if(!controller.signal.aborted)setError(error.message);});
    return ()=>controller.abort();
  },[online,expanded,productId,market,accountId,refresh]);

  const [references,setReferences]=useState<Record<string,string>>({});

  async function handle(path:string,extra:Record<string,unknown>={}) {
    setBusy(true);
    setError('');
    try {
      if(path!=='decline')await beforeApproval();
      const result=await api(path,{method:'POST',body:JSON.stringify({productId,market,...extra})});
      if(path==='pair')setToken(result.token);
      refreshStatus(value=>value+1);
    } catch(error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if(!online)return null;
  return <details className="pe-card pe-operations" onToggle={event=>{
    const open=event.currentTarget.open;
    setExpanded(open);
    if(!open)setToken('');
  }}>
    <summary>运营状态与 Codex</summary>
    <div className="pe-operations-body">
      <p><strong>{status?.stage||'读取当前阶段'}</strong> · {market}{status&&' · 资料版本 '+status.revision}</p>
      <div className="pe-actions">
        <button className="pe-primary" disabled={busy} onClick={()=>void handle('pair')}>生成本款配对码</button>
        <button disabled={busy} onClick={()=>refreshStatus(value=>value+1)}>刷新状态</button>
        <button onClick={openTasks}>查看任务中心</button>
      </div>
      {token&&<label>30 分钟有效的单款配对码<input readOnly value={token}
        onFocus={event=>event.currentTarget.select()} autoComplete="off"/></label>}
      {error&&<p role="alert">{error}</p>}
      {status?.blockers.length?<ul>{status.blockers.map(blocker=><li key={blocker}>{blocker}</li>)}</ul>:null}
      {status?.amounts&&<details><summary>金额与计量</summary>
        <p>本站情景预估利润（元） {status.amounts.estimatedMarketProfitCny??'暂无报价'} · 外部账单（元） {status.amounts.externalBillCny??'待核实'}</p>
        {status.amounts.textBudgets.map(t=><p key={t.taskId}>文本授权预算 ¥{t.budgetCny} · {t.taskId}</p>)}
        {status.amounts.productImageCosts.map(c=><p key={c.reservationId}>本款图像 {c.reservationId} · 报价 {c.quoteMaximum??'未知'} {c.quoteCurrency} · 预留 ¥{(c.reservedFen/100).toFixed(2)} · 结算 {c.settledFen===null?'待核实':'¥'+(c.settledFen/100).toFixed(2)}</p>)}
      </details>}
      {status?.actions.length?<details><summary>派给 Agent 核对</summary>
        <div className="pe-operations-body">{status.actions.map(action=><div key={JSON.stringify(action)}>
          <p>{scopeText(action.authority)}</p>
          {action.type==='research_and_copy'&&<>
            <label>预算记录（人民币）<input type="number" min="0.01" step="0.01" value={budget} onChange={e=>setBudget(e.target.value)}/></label>
            <label>已核验竞品 ASIN（可空）<input value={asins} onChange={e=>setAsins(e.target.value)}/></label></>}
          <button disabled={busy||(action.type==='research_and_copy'&&!(Number(budget)>0))}
            onClick={()=>void handle('assign',{action:{type:action.type,target:action.target,revision:status.revision,
              parameters:action.type==='research_and_copy'?{budgetCny:Number(budget),researchAsins:asins}:{}}})}>
            派单 · {action.label}{action.target.label||action.target.store?' · '+(action.target.label||action.target.store):''}
          </button>
        </div>)}</div></details>:null}
      {status?.proposals.map(proposal=>{
        const {target,parameters,requestId,revision}=proposal.request;
        return <article className="pe-operations-request" key={requestId}>
          <div><strong>{proposal.label}</strong><p>{proposalLabels[proposal.status]||proposal.status}
            {proposal.jobId&&' · 原任务 '+proposal.jobId}</p>
          <p>请求编号 <code>{requestId}</code></p>
          <p>{[target.store,target.label,target.provider,target.model,target.taskId,target.jobId].filter(Boolean).join(' · ')}</p>
          {parameters.budgetCny&&<p>预算记录 ¥{parameters.budgetCny}，费用以服务账单为准。{parameters.researchAsins&&' 竞品 '+parameters.researchAsins}</p>}
          {proposal.authority&&<p>{scopeText(proposal.authority)}</p>}
          {proposal.message&&<p role="status">{proposal.message}</p>}</div>
          {proposal.review&&<details><summary>Agent 核对意见 · {proposal.review.note}</summary><ul>{proposal.review.evidence.map((e,i)=><li key={i}>{typeof e==='string'?e:<><code>{e.path}</code> · {e.decision==='ready'?'通过':'阻塞'} · {observedValue(proposal.assignment?.inputs,e.path)}</>}</li>)}</ul></details>}
          {proposal.resolution&&<p>核查依据 · {proposal.resolution.reference}</p>}
          {proposal.handoffStage==='prepared'&&<button onClick={openTasks}>前往原任务核对启动状态</button>}
          {['dispatching','needs_review'].includes(proposal.status)&&!proposal.handoffStage&&<details>
            <summary>核对原请求</summary>
            <label>核查依据（账单、服务工单或 ERP 流水）<input maxLength={500} value={references[requestId]||''}
              onChange={e=>setReferences({...references,[requestId]:e.target.value})}/></label>
            <button disabled={busy||!references[requestId]?.trim()} onClick={()=>{
              if(window.confirm('已从服务方记录确认该请求未提交？结案后可重新派单。'))
                void handle('resolve-unsubmitted',{requestId,reference:references[requestId]});
            }}>确认未提交并结案</button>
          </details>}
          {proposal.status==='assigned'&&<button disabled={busy} onClick={()=>void handle('decline',{requestId})}>撤回派单</button>}
          {proposal.status==='pending'&&<div className="pe-actions"><button disabled={busy}
            onClick={()=>void handle('decline',{requestId})}>拒绝</button><button className="pe-primary" disabled={busy||status.revision!==revision} onClick={()=>{
            if(window.confirm('确认 '+proposal.label+'？'+(proposal.authority?scopeText(proposal.authority):'')))
              void handle('approve',{requestId});
          }}>确认执行</button></div>}
        </article>;
      })}
    </div>
  </details>;
}
