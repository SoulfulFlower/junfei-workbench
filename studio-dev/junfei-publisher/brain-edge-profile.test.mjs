import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {resolveEdgeProfile} from './brain-edge-profile.mjs';

test('worker defaults to its private profile', () => {
  assert.equal(resolveEdgeProfile('C:/agent/brain-state'), path.join('C:/agent/brain-state', 'edge-profile'));
});

test('worker can reuse an explicitly configured dedicated profile', () => {
  assert.equal(resolveEdgeProfile('C:/agent/brain-state', 'D:/agent-profile'), path.resolve('D:/agent-profile'));
});

test('worker rejects a relative shared profile path', () => {
  assert.throws(() => resolveEdgeProfile('C:/agent/brain-state', 'profile'), /必须是绝对路径/);
});
