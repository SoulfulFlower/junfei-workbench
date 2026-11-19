// Included in a per-run entry point with JSON params, by supplier_capture.py.
const fs = await import('node:fs/promises');
let route = params.browser;
const reconnectRequested = route?.reconnectMissing === true;
const existingCreationRunId = route?.reconnectExistingCreationRunId;
const nativeBlank = url => ['about:blank', 'chrome://newtab/', 'chrome://new-tab-page/'].includes(url);
const previousRoute = route ? {...route} : null;
const originalMissingRoute = route?.reconnectOriginalMissingBrowser;
const boundCreationRoute = route?.reconnectBoundCreationBrowser;
if (route) {
  route = {...route};
  delete route.reconnectMissing;
  delete route.reconnectFromRunId;
  delete route.reconnectExistingCreationRunId;
  delete route.reconnectOriginalMissingBrowser;
  delete route.reconnectBoundCreationBrowser;
}
let reconnect;
let browserDiagnostics;
const diagnosticUrl = value => {if(nativeBlank(value))return value;try {const u = new URL(value);return `${u.protocol}//${u.host}${u.pathname}`;} catch {return String(value || '').slice(0, 200);}};
const persist = async value => fs.writeFile(params.output, JSON.stringify({...value, browser: route,
  ...(reconnect ? {reconnect} : {}), ...(browserDiagnostics ? {browserDiagnostics} : {})}), 'utf8');
try {
  let task;
  if (reconnectRequested) {
    if (!params.resume || !/^[a-f0-9]{32}$/.test(params.runId || '')
        || !/^[a-f0-9]{32}$/.test(previousRoute.reconnectFromRunId || '')
        || !Number.isInteger(route.spaceId) || route.spaceId <= 0) throw Error('invalid_missing_browser_reconnect');
    const spaces = await listTaskSpaces();
    if (!Array.isArray(spaces) || spaces.some(s => !Number.isInteger(s.id))) throw Error('invalid_task_space_inventory');
    const missingRoute = originalMissingRoute || route;
    if (!Number.isInteger(missingRoute.spaceId) || missingRoute.spaceId <= 0) throw Error('invalid_missing_browser_reconnect');
    if (spaces.some(s => s.id === missingRoute.spaceId)) throw Error('missing_browser_still_exists');
    if (existingCreationRunId && (!/^[a-f0-9]{32}$/.test(existingCreationRunId)
        || (!boundCreationRoute && existingCreationRunId !== previousRoute.reconnectFromRunId))) throw Error('invalid_existing_creation_reconciliation');
    if (boundCreationRoute && (!existingCreationRunId || JSON.stringify(boundCreationRoute) !== JSON.stringify(route))) throw Error('invalid_bound_creation_reconciliation');
    const name = `Junfei 1688 serial collection reconnect ${existingCreationRunId || params.runId}`;
    const entries = spaces.filter(s => s.name === name);
    reconnect = {previousBrowser: missingRoute, previousRunId: previousRoute.reconnectFromRunId,
      runId: params.runId, oldSpaceAbsent: true, stage: 'creating',
      ...(existingCreationRunId ? {existingCreationRunId, creationCalls: 0} : {creationCalls: 1}),
      ...(boundCreationRoute ? {previousStage:'bound', reconciledBoundBrowser:boundCreationRoute} : {})};
    if (existingCreationRunId) {
      if (entries.length !== 1 || entries[0].ownership !== 'agent') throw Error('existing_creation_not_uniquely_agent_owned');
      if (boundCreationRoute && (entries[0].id !== boundCreationRoute.spaceId || name !== boundCreationRoute.name)) throw Error('bound_creation_identity_changed');
      // Attach by the observed ID; never call taskSpace(name), which could create another space.
      await persist({status: 'paused', reason: 'existing_creation_reconciliation_unknown'});
      task = await taskSpace(entries[0].id);
      if (task.spaceId !== entries[0].id) throw Error('reconnect_binding_changed');
    } else {
      if (entries.length) throw Error('reconnect_creation_unknown');
      // Unknown creation is never replayed: record the intent before asking Ego.
      await persist({status: 'paused', reason: 'reconnect_creation_unknown'});
      task = await taskSpace(name);
    }
    if (task.name !== name || task.spaceId === missingRoute.spaceId) throw Error('reconnect_binding_changed');
    // Keep the acknowledged space identity even if binding its initial tab fails.
    reconnect.createdSpace = {spaceId: task.spaceId, name: task.name};
    await persist({status: 'paused', reason: 'reconnect_page_binding_unknown'});
  }
  // A setup/inspection task may deliberately finish while keeping the configured
  // supplier tab. New user-authorized collection may reuse only that exact tab.
  task ??= route?.keptByCollector ? await claimTaskSpace(route.spaceId) : params.resume
    ? (route ? await takeOverTaskSpace(route.spaceId) : await taskSpace('Junfei 1688 serial collection'))
    : (route ? await taskSpace(route.spaceId) : await taskSpace('Junfei 1688 serial collection'));
  if (!reconnectRequested && route && (task.spaceId !== route.spaceId || task.name !== route.name)) throw Error('browser_binding_changed');
  if (task.ownership !== 'agent') throw Error('browser_control_required');
  const tabs = await task.tabs();
  if (reconnectRequested) browserDiagnostics = {tabs: tabs.map(t => ({label:t.label,url:diagnosticUrl(t.url),openedBy:t.openedBy})), observations:[]};
  let tab;
  if(reconnectRequested) {
    const candidates = tabs.filter(t => t.label === 'p1' && nativeBlank(t.url) && t.openedBy === 'agent');
    if (candidates.length !== 1 || tabs.length !== 1) throw Error('reconnect_blank_page_required');
    tab = candidates[0];
  }else if(route?.keptByCollector){
    const candidates=tabs.filter(t=>t.url===route.keptUrl);
    if(candidates.length!==1)throw Error('kept_supplier_page_changed');
    tab=candidates[0];
    if(!tab.label){const adopted=await task.adopt(tab.page);tab={...tab,label:adopted.label};}
  }else tab = route ? tabs.find(t => t.label === route.label) : tabs.find(t => t.label === 'p1');
  if (!tab) throw Error('bound_page_missing');
  route = {spaceId: task.spaceId, name: task.name, label: tab.label};
  if (reconnect) reconnect = {...reconnect, stage: 'bound', browser: route};
  await persist({status: 'paused', reason: 'execution_unknown'}); // Save binding before navigation.
  const page = task.page(tab.label);
  const inspect = async () => {
    const pageUrl = reconnectRequested ? await page.url() : null;
    const view = await page.evaluate(() => {
    const visible = e => !!e?.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
    const title = document.title;
    const text = document.body?.innerText?.slice(0, 12000) || '';
    const challenge = /验证码|安全验证|访问受限|安全检查|punish|captcha|challenge/i.test(title + ' ' + location.href)
      || [...document.querySelectorAll('#nc_1_wrapper,.nc-container,#baxia-dialog-content,iframe[src*="punish"],iframe[src*="captcha"]')].some(visible)
      || /请完成验证|拖动滑块|请先登录/.test(text);
    return {url: location.href, documentURL: document.URL, blocked: challenge || /login\.1688|login\.taobao|passport\./i.test(location.hostname)};
    });
    if (reconnectRequested) browserDiagnostics.observations.push({pageUrl:diagnosticUrl(pageUrl),
      url:diagnosticUrl(view.url),documentURL:diagnosticUrl(view.documentURL || view.url),blocked:view.blocked,
      pageNativeBlank:nativeBlank(pageUrl),documentNativeBlank:nativeBlank(view.url) && nativeBlank(view.documentURL || view.url)});
    return view;
  };
  let view = await inspect();
  // Never navigate away from a visible CAPTCHA, including one left by an earlier task.
  if (view.blocked) {
    await persist({status: 'paused', reason: 'login_or_verification'});
    await task.handOff();
  } else {
    const canonical = value => {try {const u = new URL(value);return u.origin + u.pathname;} catch {return '';}};
    if (params.resume && !reconnectRequested && canonical(view.url) !== params.url) throw Error('verify_original_product_page');
    if (reconnectRequested && (!nativeBlank(view.url) || !nativeBlank(view.documentURL || view.url)
        || !browserDiagnostics.observations.at(-1).pageNativeBlank)) throw Error('reconnect_blank_page_required');
    if ((!params.resume || reconnectRequested) && canonical(view.url) !== params.url) await page.goto(params.url, {timeout: 45000});
    view = await inspect();
    if (view.blocked) {
      await persist({status: 'paused', reason: 'login_or_verification'});
      await task.handOff();
    } else {
      if (canonical(view.url) !== params.url) throw Error('unexpected_product_page');
      const collector = await fs.readFile(params.collector, 'utf8');
      const supplier = await page.evaluate(collector);
      if (!supplier || canonical(supplier.url) !== params.url || !supplier.title
          || /登录|验证|访问受限|安全检查/.test(supplier.title)
          || (!Object.keys(supplier.attributes || {}).length && !(supplier.images || []).length)) {
        await persist({status: 'paused', reason: 'incomplete_product_page'});
        await task.handOff();
      } else {
        await persist({status: 'collected', supplier: {...supplier, url: params.url,
          captureMethod: 'ego-serial-browser', retrievedAt: supplier.capturedAt}});
      }
    }
  }
} catch (error) {
  await persist({status: 'paused', reason: String(error.message || error).slice(0, 200)});
}
