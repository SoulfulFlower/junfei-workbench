import {strict as assert} from 'node:assert';

const SEARCH_HINT = /search|搜索|搜款|关键词|keyword/i;
const SEARCH_HOSTS = new Set(['s.1688.com','search.1688.com','www.1688.com']);

function assertImageSearchPage(url) {
  const parsed = new URL(url);
  const allowedAirRoute = parsed.hostname === 'air.1688.com' && parsed.pathname.startsWith('/kapp/1688-search/pc-image-search/');
  if (parsed.protocol !== 'https:' || (!SEARCH_HOSTS.has(parsed.hostname) && !allowedAirRoute)) {
    throw new Error('图片粘贴只允许在1688图片搜索/搜索页面执行');
  }
}

export async function pasteImageToSearch({page, locator, imageBase64}) {
  assertImageSearchPage(page.url());
  const info = await locator.evaluate(element => ({
    tag: element.tagName.toLowerCase(),
    type: (element.getAttribute('type') || 'text').toLowerCase(),
    readOnly: !!element.readOnly,
    disabled: !!element.disabled,
    visible: !!(element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden'),
    hint: [element.getAttribute('placeholder'), element.getAttribute('aria-label'), element.getAttribute('name'), element.id, element.className, element.parentElement?.className].join(' ')
  }));
  assert.equal(info.tag, 'input', '粘贴目标必须是搜索输入框');
  assert.ok(['text','search'].includes(info.type), '不允许向文件/密码/隐藏输入框粘贴');
  assert.equal(info.readOnly, false, '搜索输入框不可写');
  assert.equal(info.disabled, false, '搜索输入框已禁用');
  assert.equal(info.visible, true, '搜索输入框不可见');
  assert.match(info.hint, SEARCH_HINT, '目标没有明确的搜索框标识');
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(imageBase64) || imageBase64.length < 100) throw new Error('图片剪贴板数据无效');

  await locator.click();
  await page.evaluate(async base64 => {
    const binary = atob(base64);
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
    const image = new Blob([bytes], {type:'image/png'});
    await navigator.clipboard.write([new ClipboardItem({'image/png':image})]);
  }, imageBase64);
  await locator.press('Control+V');
  return {method:'clipboard-paste', target:'visible-1688-search-input'};
}
