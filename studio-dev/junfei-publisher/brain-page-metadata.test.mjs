import test from 'node:test';
import assert from 'node:assert/strict';
import {pageMetadata} from './brain-page-metadata.mjs';

test('page diagnostics redact query and fragment data while classifying blocked origins', () => {
  assert.deepEqual(pageMetadata('https://air.1688.com/app/search/image?token=secret#private'), {
    origin:'https://air.1688.com', pathname:'/app/search/image', allowed:false
  });
});

test('page diagnostics mark approved public search pages', () => {
  assert.deepEqual(pageMetadata('https://s.1688.com/selloffer/offer_search.htm?keywords=door'), {
    origin:'https://s.1688.com', pathname:'/selloffer/offer_search.htm', allowed:true
  });
});
