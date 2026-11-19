import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {trackPages} from './brain-page-tracker.mjs';

class MockPage extends EventEmitter {
  closed = false;
  isClosed() { return this.closed; }
  close() { this.closed = true; this.emit('close'); }
}

class MockContext extends EventEmitter {
  openPages = [];
  pages() { return this.openPages; }
  addPage(page) { this.openPages.push(page); this.emit('page', page); }
  closePage(page) { this.openPages = this.openPages.filter(item => item !== page); page.close(); }
}

test('new Edge tabs become the worker target', () => {
  const context = new MockContext();
  const first = new MockPage();
  const second = new MockPage();
  context.openPages = [first];
  let current;
  trackPages(context, {select:page => { current = page; }, onEmpty:() => assert.fail('unexpected empty context')});

  context.addPage(second);

  assert.equal(current, second);
});

test('closing the selected tab falls back to another live tab', () => {
  const context = new MockContext();
  const first = new MockPage();
  const second = new MockPage();
  context.openPages = [first, second];
  let current;
  let empty = 0;
  trackPages(context, {select:page => { current = page; }, onEmpty:() => empty++});

  context.closePage(second);

  assert.equal(current, first);
  assert.equal(empty, 0);
});

test('closing the final tab signals worker shutdown', () => {
  const context = new MockContext();
  const only = new MockPage();
  context.openPages = [only];
  let empty = 0;
  trackPages(context, {select:() => {}, onEmpty:() => empty++});

  context.closePage(only);

  assert.equal(empty, 1);
});
