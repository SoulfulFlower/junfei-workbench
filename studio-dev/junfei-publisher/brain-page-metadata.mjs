import {assertAllowedPageUrl} from './brain-url-policy.mjs';

export function pageMetadata(url) {
  const parsed = new URL(url);
  let allowed = true;
  try { assertAllowedPageUrl(url); } catch { allowed = false; }
  return {origin:parsed.origin, pathname:parsed.pathname, allowed};
}
