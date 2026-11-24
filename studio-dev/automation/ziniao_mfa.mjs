// Run with the supported Computer Use runtime's sky client.
// The code remains inside Ziniao's field. Reports contain state only.
export function inspectMfaTree(tree, origin) {
  const lines = String(tree).split('\n');
  const page = lines.find(line => line.includes(' ID: RootWebArea') && line.includes('Value: ' + origin + '/'));
  if (!page) throw Error('Expected Seller Central document is missing');
  const url = page.split('Value: ')[1]?.split(' ID: ')[0];
  const parsed = new URL(url);
  if (parsed.origin !== origin) throw Error('Seller Central origin changed');
  if (parsed.pathname !== '/ap/mfa') return { state: 'left_mfa' };
  const pick = pattern => {
    const matches = lines.filter(line => pattern.test(line));
    if (matches.length > 1) throw Error('Ambiguous verification control');
    return matches[0];
  };
  const field = pick(/text field .*ID: auth-mfa-otpcode$/);
  const login = pick(/button .*ID: auth-signin-button$/);
  if (!field || !login) throw Error('Verification form changed');
  const refresh = pick(/hyperlink .*重新获取验证码/);
  const index = line => Number(line.trim().match(/^\d+/)?.[0]);
  return { state: 'mfa', ready: /Value: \d{6} ID:/.test(field) && !login.includes('(disabled)'),
    login: index(login), refresh: refresh ? index(refresh) : null,
    servicePresent: lines.some(line => line.includes('紫鸟验证码服务')) };
}

export async function completeZiniaoMfa(sky, { storeName, market = 'US', timeoutMs = 45000 }) {
  const origin = { US: 'https://sellercentral.amazon.com', UK: 'https://sellercentral.amazon.co.uk' }[market];
  if (!origin || !storeName) throw Error('Expected store and market are required');
  const windows = (await sky.list_windows()).filter(window => window.title === storeName &&
    /ziniaobrowser\.exe/i.test(window.app));
  if (windows.length !== 1) throw Error('Expected exactly one Ziniao store window');
  let window = await sky.get_window({ id: windows[0].id, app: windows[0].app });
  await sky.activate_window({ window });
  const deadline = Date.now() + timeoutMs;
  let refreshed = 0, submitted = 0, refreshAtSubmit = -1;
  while (Date.now() < deadline) {
    const observation = await sky.get_window_state({ window, include_text: true, include_screenshot: false });
    window = observation.window;
    const state = inspectMfaTree(observation.accessibility?.tree, origin);
    if (state.state === 'left_mfa') return { status: 'left_mfa', refreshed, submitted, otpRecorded: false };
    // The observed refresh link appears when Ziniao's code has expired.
    if (state.refresh !== null && state.servicePresent) {
      if (refreshed >= 2) throw Error('Verification refresh limit reached');
      await sky.click({ window, element_index: state.refresh });
      refreshed++;
      continue;
    }
    if (state.ready && (submitted === 0 || refreshed > refreshAtSubmit)) {
      if (submitted >= 2) throw Error('Verification submission limit reached');
      await sky.click({ window, element_index: state.login });
      submitted++;
      refreshAtSubmit = refreshed;
    }
    await new Promise(resolve => setTimeout(resolve, 400));
  }
  throw Error('Verification result unconfirmed; inspect the same page before retrying');
}
