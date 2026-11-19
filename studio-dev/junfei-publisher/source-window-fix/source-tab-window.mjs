/** Open a supplier search beside its source, without using the current window. */
export async function open1688SourceTab(url, source, api = globalThis.chrome) {
  if (!source || !Number.isInteger(source.id) || source.id < 0 ||
      !Number.isInteger(source.windowId) || source.windowId < 0) {
    throw new Error('Cannot identify the source tab and window');
  }
  const target = new URL(url);
  if (target.protocol !== 'https:' || target.hostname !== 's.1688.com') {
    throw new Error('Unexpected supplier search destination');
  }
  const current = await api.tabs.get(source.id);
  if (!current || current.id !== source.id || current.windowId !== source.windowId) {
    throw new Error('The source tab was closed or moved; supplier search was not opened');
  }
  return api.tabs.create({
    url: target.href,
    windowId: current.windowId,
    openerTabId: current.id,
    index: current.index + 1,
    active: false,
  });
}
