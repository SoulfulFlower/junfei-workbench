"""Offline, fail-closed regression for metadata-only image preparation.

All account data is temporary before application imports; no network or workers.
"""
import atexit
import hashlib
import json
import os
import socket
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

_IMPORT_DATA = tempfile.TemporaryDirectory(prefix='image-preparation-import-')
atexit.register(_IMPORT_DATA.cleanup)
os.environ['JUNFEI_ACCOUNT_DATA'] = _IMPORT_DATA.name
os.environ['JUNFEI_WORKER_USER'] = '0'
with patch.object(socket.socket, 'connect', side_effect=AssertionError('Import network forbidden')), \
        patch.object(socket, 'create_connection', side_effect=AssertionError('Import network forbidden')):
    import test_agent_handoff as fixtures
    import agent_center as agent
    import agent_handoff
    import agent_research
    import agent_image_preparation as preparation


# Reuse only helpers, not a TestCase subclass (which would repeat handoff tests).
class FixtureMixin:
    pass


for _name, _method in fixtures.AgentHandoffTests.__dict__.items():
    if not _name.startswith('test_') and not _name.startswith('__'):
        setattr(FixtureMixin, _name, _method)


class ImagePreparationTests(FixtureMixin, unittest.TestCase):
    def setUp(self):
        FixtureMixin.setUp(self)
        self.children = [
            {'asin': 'B000000001', 'sku': 'black-s', 'color_name': 'Black', 'size_name': 'S'},
            {'asin': 'B000000002', 'sku': 'black-m', 'color_name': 'Black', 'size_name': 'M'},
            {'asin': 'B000000003', 'sku': 'blue-s', 'color_name': 'Blue', 'size_name': 'S'},
        ]
        self.product.update(
            colorNames='Black,Blue', sizeNames='S,M', masterColor='Black',
            sourceImport={'amazon': {'variants': self.children}},
            supplierColorReferences=[{'url': 'https://example.invalid/black.png', 'color': 'Black'},
                                     {'url': '/uploads/blue.png', 'color': 'Blue'}],
            supplierVariantCoverage={
                'productId': self.pid, 'sourceUrl': self.product['sourceUrl'],
                'checkedAt': '2026-11-06T00:00:00+00:00', 'evidence': 'Synthetic offline observation',
                'supplierObservedColors': ['Black', 'Blue'], 'supplierObservedSizes': ['S', 'M'],
                'supplierObservedVariants': [{'color': c['color_name'], 'size': c['size_name']}
                                             for c in self.children]})
        self.save_workspace()
        self.prepare()
        self.workspace['copy'][self.pid + '-US'] = self.listing
        self.workspace['reviews'][self.pid] = {'copy': True}
        self.save_workspace()
        self.mutate_task(status='blocked', cursor=4,
                         results={key: {'ok': True} for key in ('facts', 'research', 'listing')},
                         listingAttempt={'state': 'saved'}, researchAttempt={'state': 'saved'})
        self.refresh_snapshot()
        self.original = self.stored()
        self.image_policy = {'gallery_count': 7, 'minimum_short_side': 1600}
        p = patch.object(preparation, 'image_policy', side_effect=lambda: self.clone(self.image_policy))
        p.start()
        self.addCleanup(p.stop)
        for target in ('agent_center.start', 'agent_center.run', 'provider.research_json',
                       'provider.text_completion', 'urllib.request.urlopen',
                       'socket.socket.connect_ex', 'socket.socket.sendto'):
            p = patch(target, side_effect=AssertionError('Forbidden side effect: ' + target))
            p.start()
            self.addCleanup(p.stop)

    def refresh_snapshot(self):
        self.save_workspace()
        self.mutate_task(snapshot=agent_research.snapshot(self.workspace, self.stored()), workspaceRevision=7)

    def hashes(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def preview(self, user=1, revision=7):
        before = self.hashes()
        with patch.object(threading.Thread, 'start', side_effect=AssertionError('Worker forbidden')):
            try:
                return preparation.preview(user, self.tid, revision)
            finally:
                self.assertEqual(self.hashes(), before)

    def rejected(self, **kwargs):
        with self.assertRaises(ValueError):
            self.preview(**kwargs)

    def assert_blocked(self):
        result = self.preview()
        self.assertFalse(result['readyForManualPreparation'])
        self.assertTrue(result['blockers'])
        self.assertFalse(result['executionAllowed'])
        return result

    def test_valid_two_colors_three_children_plan_fourteen_without_cartesian_product(self):
        result = self.preview()
        self.assertEqual(result['blockers'], [])
        self.assertTrue(result['readyForManualPreparation'])
        self.assertEqual(result['plannedImageCount'], 14)
        self.assertEqual(result['galleryCountPerColor'], 7)
        self.assertEqual(result['masterColor'], 'Black')
        self.assertEqual([len(s['children']) for s in result['sets']], [2, 1])
        self.assertEqual({c['sku'] for s in result['sets'] for c in s['children']},
                         {'black-s', 'black-m', 'blue-s'})
        self.assertEqual([s['role'] for s in result['sets']],
                         ['master', 'full_colour_set_after_master_review'])
        for item in result['sets']:
            self.assertEqual(len(item['slots']), 7)
            self.assertTrue(all(not s['approved'] for s in item['slots']))
        for key in ('executionAllowed', 'paidCallsAllowed', 'productionReady', 'imagesReady',
                    'humanReviewed', 'stockVerified'):
            self.assertFalse(result[key])
        self.assertFalse(result['history']['providerStatusChecked'])
        self.assertFalse(result['history']['imageBytesChecked'])
        self.assertEqual(result['budget']['newReservations'], 0)

    def test_two_children_still_mean_fourteen_images(self):
        self.children.pop(1)
        self.refresh_snapshot()
        result = self.preview()
        self.assertEqual(result['blockers'], [])
        self.assertEqual(result['plannedImageCount'], 14)
        self.assertEqual(sum(len(s['children']) for s in result['sets']), 2)

    def test_missing_sku_is_not_synthesized(self):
        self.children[0].pop('sku')
        self.refresh_snapshot()
        result = self.assert_blocked()
        self.assertIsNone(result['sets'][0]['children'][0]['sku'])

    def test_no_children_is_not_reconstructed_from_color_and_size_names(self):
        self.children.clear()
        self.refresh_snapshot()
        result = self.assert_blocked()
        self.assertEqual(result['sets'], [])

    def test_duplicate_sku_asin_and_normalized_pair_are_blockers(self):
        original = self.clone(self.children)
        for key, value in (('sku', 'black-s'), ('asin', 'B000000001'), ('size_name', 'small')):
            with self.subTest(key=key):
                self.children[:] = self.clone(original)
                self.children[1][key] = value
                self.refresh_snapshot()
                self.assert_blocked()

    def test_missing_reference_master_and_declared_color_are_blockers(self):
        original = self.clone(self.product)
        for key, value in (('supplierColorReferences', []), ('masterColor', 'Red'),
                           ('colorNames', 'Black,Blue,Red')):
            with self.subTest(key=key):
                self.product.clear()
                self.product.update(self.clone(original))
                self.product[key] = value
                self.refresh_snapshot()
                self.assert_blocked()

    def test_missing_supplier_combination_is_a_blocker(self):
        self.product['supplierVariantCoverage']['supplierObservedVariants'].pop()
        self.refresh_snapshot()
        self.assert_blocked()

    def test_asset_bindings_override_reference_color(self):
        self.product['supplierColorReferences'][1]['color'] = 'Incorrect'
        self.product['assetColorBindings'] = {'/uploads/blue.png': 'Blue'}
        self.refresh_snapshot()
        self.assertEqual(self.preview()['blockers'], [])

    def test_remote_locators_are_hash_only_and_never_opened(self):
        result = self.preview()
        serialized = json.dumps(result)
        self.assertNotIn('https://example.invalid', serialized)
        ref = result['sets'][0]['references'][0]
        self.assertEqual(ref['kind'], 'remote_not_fetched')
        self.assertFalse(ref['pixelsVerified'])
        self.assertEqual(len(ref['locatorSha256']), 64)
        for value in ('file:///secret', '/uploads/../secret', 'http://example.invalid/a',
                      'https://user:secret@example.invalid/a'):
            self.assertIsNone(preparation.reference_kind(value))

    def test_unknown_attempts_and_unapproved_copy_remain_blocked(self):
        for key in ('planningAttempt', 'sourcingAttempt', 'researchAttempt', 'listingAttempt'):
            for value in (None, {}, {'state': 'started'}, {'state': 'unknown'}):
                with self.subTest(key=key, value=value):
                    self.restore_original()
                    self.mutate_task(**{key: value})
                    self.assert_blocked()
        self.restore_original()
        self.mutate_task(results={'facts': {'ok': True}, 'research': {'ok': True},
                                  'listing': {'ok': False}}, listingDraftAvailable=True)
        self.assert_blocked()

    def test_invalid_image_configuration_blocks(self):
        for key, values in (('gallery_count', [None, True, 0, 6, 10, '7']),
                            ('minimum_short_side', [None, True, 1599, '1600'])):
            for value in values:
                with self.subTest(key=key, value=value):
                    self.image_policy = {'gallery_count': 7, 'minimum_short_side': 1600}
                    self.image_policy[key] = value
                    self.assert_blocked()

    def test_account_isolation_and_missing_task(self):
        self.rejected(user=2)
        self.tid = 'nonexistent-task'
        self.rejected()

    def test_state_scope_profile_and_active_tasks_are_rejected(self):
        for key, values in (('status', ['queued', 'running', 'paused', 'done', 'needs_review']),
                            ('executionScope', ['', 'unknown']), ('taskMode', ['inspection'])):
            for value in values:
                with self.subTest(key=key, value=value):
                    self.restore_original()
                    self.mutate_task(**{key: value})
                    self.rejected()
        self.restore_original()
        profile = dict(self.original['profile'], mode='publish')
        self.mutate_task(profile=profile)
        self.rejected()
        self.restore_original()
        agent.ACTIVE.add(self.tid)
        self.rejected()

    def test_erp_and_downstream_records_are_rejected(self):
        for key in ('images', 'export', 'junfeiPreflight', 'publish', 'verify'):
            self.restore_original()
            self.mutate_task(results=dict(self.original['results'], **{key: {}}))
            self.rejected()
        for update in ({'erpObservation': {}}, {'exportAvailable': True}, {'junfeiPlanAvailable': True}):
            self.restore_original()
            self.mutate_task(**update)
            self.rejected()

    def test_snapshot_and_revision_must_match_exactly(self):
        for revision in (None, True, '7', 6, 8):
            self.rejected(revision=revision)
        self.product['material'] = 'Changed'
        self.save_workspace()
        self.rejected()
        self.refresh_snapshot()
        self.save_workspace(8)
        self.rejected(revision=8)

    def test_candidate_identity_and_handoff_identity_must_match(self):
        for key, value in (('asin', 'B999999999'), ('market', 'UK')):
            self.product['selectionResearch']['reference'][key] = value
            self.refresh_snapshot()
            self.rejected()
            self.product['selectionResearch']['reference'] = {'asin': 'B012345678', 'market': 'US'}
        self.refresh_snapshot()
        for key in ('productId', 'profileId', 'store', 'marketplace', 'scope'):
            self.restore_original()
            self.mutate_task(copyHandoff=dict(self.original['copyHandoff'], **{key: 'wrong'}))
            self.rejected()

    def test_corrupt_and_missing_history_tables_are_not_empty_success(self):
        for filename in ('visual_studio.sqlite3', 'colour_sets.sqlite3', 'image_jobs.sqlite3'):
            for corrupt in (False, True):
                with self.subTest(filename=filename, corrupt=corrupt):
                    path = self.root / filename
                    if corrupt:
                        path.write_bytes(b'not a sqlite database')
                    else:
                        with closing(sqlite3.connect(path)) as c:
                            c.execute('CREATE TABLE unrelated(id INTEGER)')
                    result = self.assert_blocked()
                    self.assertTrue(result['history']['issues'])
                    path.unlink()

    def test_unknown_job_is_not_retried_and_other_product_is_ignored(self):
        path = self.root / 'image_jobs.sqlite3'
        with closing(sqlite3.connect(path)) as c, c:
            c.execute('CREATE TABLE jobs(body TEXT)')
            c.execute('CREATE TABLE submission_attempts(product_id TEXT, body TEXT)')
            c.execute('INSERT INTO jobs VALUES(?)', (json.dumps({'id': 'old-job',
                      'productId': self.pid, 'status': 'unknown'}),))
        first = self.assert_blocked()
        self.assertEqual(first, self.preview())
        with closing(sqlite3.connect(path)) as c, c:
            c.execute('UPDATE jobs SET body=?', (json.dumps({'id': 'other-job',
                      'productId': 'other-product', 'status': 'unknown'}),))
        self.assertEqual(self.preview()['blockers'], [])

    def test_recorded_submission_requires_same_product_terminal_job(self):
        path = self.root / 'image_jobs.sqlite3'
        with closing(sqlite3.connect(path)) as c, c:
            c.execute('CREATE TABLE jobs(body TEXT)')
            c.execute('CREATE TABLE submission_attempts(product_id TEXT, body TEXT)')
        cases = [
            ('completed', self.pid, 'job-1', True),
            ('failed', self.pid, 'job-1', True),
            ('cancelled', self.pid, 'job-1', True),
            ('pending', self.pid, 'job-1', False),
            ('unknown', self.pid, 'job-1', False),
            ('completed', 'another-product', 'job-1', False),
            ('completed', self.pid, 'missing-job', False),
            ('completed', self.pid, '', False),
            (None, self.pid, 'job-1', False),
        ]
        for status, product_id, external_id, allowed in cases:
            with self.subTest(status=status, product=product_id, link=external_id):
                with closing(sqlite3.connect(path)) as c, c:
                    c.execute('DELETE FROM jobs')
                    c.execute('DELETE FROM submission_attempts')
                    if status is not None:
                        c.execute('INSERT INTO jobs VALUES(?)', (json.dumps({
                            'id': 'job-1', 'productId': product_id, 'status': status}),))
                    c.execute('INSERT INTO submission_attempts VALUES(?,?)', (self.pid, json.dumps({
                        'id': 'attempt-1', 'status': 'recorded', 'externalId': external_id})))
                result = self.preview()
                self.assertEqual(result['readyForManualPreparation'], allowed)
                self.assertEqual(bool(result['history']['issues']), not allowed)
                self.assertFalse(result['executionAllowed'])
                self.assertEqual(result, self.preview())

    def test_malformed_history_json_blocks(self):
        with closing(sqlite3.connect(self.root / 'colour_sets.sqlite3')) as c, c:
            c.execute('CREATE TABLE sets(product_id TEXT, body TEXT)')
            c.execute('INSERT INTO sets VALUES(?,?)', (self.pid, '{bad json'))
        self.assert_blocked()

    def test_double_read_detects_task_workspace_policy_and_history_changes(self):
        values = {
            'read_workspace': [(7, self.clone(self.workspace)), (8, self.clone(self.workspace))],
            'read_task': [self.stored(), dict(self.stored(), updated=-1)],
            'image_policy': [self.clone(self.image_policy), dict(self.image_policy, gallery_count=6)],
            'inventory': [preparation.inventory(self.pid),
                          dict(preparation.inventory(self.pid), issues=['changed'])],
        }
        for target, sequence in values.items():
            with self.subTest(target=target), patch.object(preparation, target, side_effect=sequence):
                self.rejected()

    def test_repeated_and_concurrent_previews_do_not_mutate_any_file(self):
        before = self.hashes()
        expected = self.preview()
        self.assertEqual(self.preview(), expected)
        # Test harness threads are pre-started before forbidding application threads.
        ready = threading.Barrier(5)
        go = threading.Event()
        def worker():
            ready.wait(timeout=10)
            go.wait(timeout=10)
            return preparation.preview(1, self.tid, 7)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker) for _ in range(4)]
            ready.wait(timeout=10)
            with patch.object(threading.Thread, 'start', side_effect=AssertionError('Worker forbidden')):
                go.set()
                results = [f.result(timeout=20) for f in futures]
        self.assertEqual(results, [expected] * 4)
        self.assertEqual(self.hashes(), before)


if __name__ == '__main__':
    unittest.main()
