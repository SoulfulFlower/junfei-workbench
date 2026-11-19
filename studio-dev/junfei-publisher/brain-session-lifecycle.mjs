// A dedicated Edge context may close independently of its worker process.
export function stopWhenBrowserCloses(browser, stop) {
  let stopped = false;
  const stopOnce = () => {
    if (stopped) return;
    stopped = true;
    stop();
  };
  browser.on('close', stopOnce);
}
