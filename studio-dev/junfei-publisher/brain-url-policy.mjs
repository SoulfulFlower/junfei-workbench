// Exact origins for the local ERP executor. Alibaba checkout/account pages stay blocked.
const ERP_ORIGIN = 'https://www.junfeikuajing.com';
const LOCAL_ORIGINS = new Set(['http://127.0.0.1:18765', 'http://localhost:18765']);
const PUBLIC_1688_ORIGINS = new Set([
  'https://s.1688.com',
  'https://www.1688.com',
  'https://detail.1688.com',
]);
const PUBLIC_1688_IMAGE_SEARCH = new Set([
  '/kapp/1688-search/pc-image-search',
  '/kapp/1688-search/pc-image-search/',
]);

export function assertAllowedPageUrl(rawUrl) {
  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    throw new Error(`执行器拒绝无效 URL：${String(rawUrl)}`);
  }
  const allowed = url.origin === ERP_ORIGIN
    || LOCAL_ORIGINS.has(url.origin)
    || PUBLIC_1688_ORIGINS.has(url.origin)
    || (url.origin === 'https://air.1688.com' && PUBLIC_1688_IMAGE_SEARCH.has(url.pathname));
  if (!allowed) throw new Error(`执行器拒绝访问 ${url.host}（仅允许钧飞 ERP、本机工作台及 1688 公共搜索/商品详情页）`);
  return url;
}
