// Keep the worker pointed at the newest live Edge tab (for example, a search
// site that opens image results in a separate tab) and fall back when a tab closes.
export function trackPages(context, {select, onEmpty}) {
  const attach = page => {
    select(page);
    page.on('close', () => {
      const open = context.pages().filter(candidate => !candidate.isClosed());
      if (open.length) select(open.at(-1));
      else onEmpty();
    });
  };
  for (const page of context.pages()) attach(page);
  context.on('page', attach);
}
