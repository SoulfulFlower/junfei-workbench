import { renderOfficialColour, type ColourSettings, type ColourResources } from './OfficialColour';
export type ToolKind = 'selection' | 'reference_sample' | 'colour_check';
export type ToolTask = { id: string; status: string; phase?: string; error?: string; result: any; upgradeAllowed?: boolean };
async function api(url: string, body?: unknown, account?: string | number) {
  const headers: Record<string, string> = account === undefined ? {} : { 'X-Workspace-Account': String(account) };
  if (body !== undefined) headers['content-type'] = 'application/json';
  const r = await fetch(url, { headers, ...(body === undefined ? {} : { method: 'POST', body: JSON.stringify(body) }) });
  const value = await r.json(); if (!r.ok) throw new Error(value.error || `自动检查请求失败 ${r.status}`); return value;
}
export async function runImageTool(productId: string, kind: ToolKind, inputs: Record<string, unknown>, progress?: (value: string) => void, expectedAccount?: string | number): Promise<ToolTask> {
  const account = (await api('/api/auth/status')).user?.id;
  if (!account) throw new Error('请先登录当前工作空间');
  if (expectedAccount !== undefined && String(account) !== String(expectedAccount)) throw new Error('账号已切换，原自动任务保持保存');
  const request = (url: string, body?: unknown) => api(url, body, account);
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify({ productId, kind, inputs }))))].map(v => v.toString(16).padStart(2, '0')).join('');
  const key = `junfei-image-tool:${account}:${hash}`;
  const saved = sessionStorage.getItem(key); const intent = saved ? JSON.parse(saved) : { requestId: crypto.randomUUID() };
  sessionStorage.setItem(key, JSON.stringify(intent));
  let task: ToolTask;
  if (intent.taskId) task = (await request('/api/image-tools/task?id=' + encodeURIComponent(intent.taskId))).task;
  else {
    task = (await request('/api/image-tools/start', { ...inputs, productId, kind, requestId: intent.requestId })).task;
    intent.taskId = task.id; sessionStorage.setItem(key, JSON.stringify(intent));
  }
  if (task.status === 'failed' && task.upgradeAllowed) {
    const prior = task.id;
    task = (await request('/api/image-tools/retry', { productId, taskId: prior })).task;
    intent.priorTaskIds = [...(intent.priorTaskIds || []), prior]; intent.taskId = task.id;
    sessionStorage.setItem(key, JSON.stringify(intent));
  }
  const deadline = Date.now() + 1800000;
  while (!['completed', 'failed', 'interrupted'].includes(task.status)) {
    progress?.(kind === 'selection' ? '正在自动识别并检查选区…' : kind === 'reference_sample' ? '正在自动取色并检查衣料样本…' : '正在检查成图与保护区域…');
    if (Date.now() > deadline) throw new Error(`自动检查仍在后台，原任务 ${task.id} 已保存；再次操作会查询原任务`);
    await new Promise(resolve => setTimeout(resolve, 3000));
    task = (await request('/api/image-tools/task?id=' + encodeURIComponent(task.id))).task;
  }
  if (task.status !== 'completed') throw new Error((task.error || '自动检查未通过；原意图与诊断已保存') + `（自动任务 ${task.id}）`);
  return task;
}

export async function runAutomaticColour(args: { productId: string; source: string; mask: string; selectionTaskId?: string; target: string; reference?: string; autoMask: boolean; matchTarget: boolean; settings: ColourSettings; resources: ColourResources; progress: (value: string) => void }) {
  const account = (await api('/api/auth/status')).user?.id;
  if (!account) throw new Error('请先登录当前工作空间');
  const request = (url: string, body?: unknown) => api(url, body, account);
  let { mask, selectionTaskId } = args; let final: any; const attempts = [];
  const render = async (settings: ColourSettings) => {
    args.progress('正在生成换色并保留原像素…');
    const key = 'junfei-colour-render:' + JSON.stringify({ account, source: args.source, mask, target: args.target, settings });
    const saved = sessionStorage.getItem(key); if (saved) return JSON.parse(saved);
    const rendered = await renderOfficialColour(args.source, mask, args.target, args.resources, settings, { preserveOutsideSelection: true });
    const upload = await fetch('/api/upload', { method: 'POST', headers: { 'X-Workspace-Account': String(account) }, body: rendered.blob }); const uploaded = await upload.json(); if (!upload.ok) throw new Error(uploaded.error);
    const value = { renderedImage: uploaded.url as string, shaderReceipt: rendered.receipt };
    sessionStorage.setItem(key, JSON.stringify(value)); return value;
  };
  for (let attempt = 0; attempt < 2; attempt++) {
    let settings = args.settings; let calibration: any;
    if (args.matchTarget) {
      const recipe = await request('/api/image-templates/colour-recipe', { productId: args.productId, source: args.source, mask, target: args.target });
      settings = Object.fromEntries([...new Set([...Object.keys(recipe.settings), ...Object.keys(args.settings)])].map(k => [k, { ...recipe.settings[k], ...args.settings[k] }]));
      calibration = recipe.audit;
    }
    const initial = await render(settings); let rendered = initial; let feedback: any;
    if (args.matchTarget) {
      feedback = await request('/api/image-templates/colour-recipe', { productId: args.productId, source: args.source, mask, target: args.target, renderedImage: initial.renderedImage, settings });
      if (feedback.audit.applied) rendered = await render(feedback.settings);
    }
    const checked = await runImageTool(args.productId, 'colour_check', { source: args.source, mask, renderedImage: rendered.renderedImage, target: args.target,
      ...(selectionTaskId ? { selectionTaskId } : {}), ...(args.reference ? { reference: args.reference } : {}) }, args.progress, account);
    attempts.push({ number: attempt + 1, mask, selectionTaskId, initial, feedback, qualityCheckId: checked.id, quality: checked.result });
    final = { mask, renderedImage: rendered.renderedImage, selectionTaskId, qualityCheckId: checked.id,
      shaderReceipt: { ...rendered.shaderReceipt, skuCalibration: calibration, skuFeedback: feedback?.audit,
        automaticAttempts: attempts.map(a => ({ number: a.number, mask: a.mask, selectionTaskId: a.selectionTaskId, initialImage: a.initial.renderedImage, qualityCheckId: a.qualityCheckId, passed: a.quality.passed, issues: a.quality.issues })) } };
    if (checked.result.passed || attempt === 1 || !args.autoMask || checked.result.nextAction !== 'selection') break;
    args.progress('正在自动纠正选区…');
    const corrected = await runImageTool(args.productId, 'selection', { source: args.source, force: true, feedback: { qualityCheckId: checked.id, previousSelectionTask: selectionTaskId } }, args.progress, account);
    mask = corrected.result.mask.url; selectionTaskId = corrected.id;
  }
  return final;
}
