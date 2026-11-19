import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {stopWhenBrowserCloses} from './brain-session-lifecycle.mjs';

test('closing the browser context stops the worker exactly once', () => {
  const browser = new EventEmitter();
  let stopped = 0;
  stopWhenBrowserCloses(browser, () => stopped++);

  browser.emit('close');
  browser.emit('close');

  assert.equal(stopped, 1);
});
