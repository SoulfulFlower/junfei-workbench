"""Listing locks survive workspace saves and are checked before provider calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import listing_locks
import server
import test_agent_api as api_fixtures


class ListingLockTests(unittest.TestCase):
    call = api_fixtures.AgentAPITests.call

    @classmethod
    def setUpClass(cls):
        api_fixtures.AgentAPITests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        api_fixtures.AgentAPITests.tearDownClass.__func__(cls)

    def setUp(self):
        data = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='listing-lock-')))
        self.enterContext(patch.object(server, 'DB', data / 'studio.sqlite3'))
        self.key = 'product-1-US'
        self.state = {'products': [{'id': 'product-1', 'name': 'Fixture', 'cat': 'Fixtures',
                                    'owner': 'test', 'status': '制作中', 'color': '#fff', 'colors': 1, 'sizes': 1}],
                      'copy': {self.key: {'title': 'Original title', 'description': 'Before',
                                          'lockedFields': ['title'], 'translations': {'title': '原文'}}}, 'reviews': {}}
        with server.database() as db:
            db.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)')
            db.execute('INSERT INTO workspace VALUES (1, 1, ?)', (json.dumps(self.state),))

    def test_lock_survives_translation_or_combined_unlock_and_edit(self):
        for patch_values in ({'translations': {'title': '更改'}},
                             {'lockedFields': [], 'title': 'Changed'}):
            proposed = copy.deepcopy(self.state)
            proposed['copy'][self.key].update(patch_values)
            self.assertEqual(self.call('/api/state', {'revision': 1, 'state': proposed})[0], 400)
        proposed = copy.deepcopy(self.state)
        proposed['copy'][self.key]['description'] = 'After'
        self.assertEqual(self.call('/api/state', {'revision': 1, 'state': proposed})[0], 200)
        proposed['copy'][self.key]['lockedFields'] = []
        self.assertEqual(self.call('/api/state', {'revision': 2, 'state': proposed})[0], 200)
        proposed['copy'][self.key]['title'] = 'Changed after unlock'
        self.assertEqual(self.call('/api/state', {'revision': 3, 'state': proposed})[0], 200)

    def test_rewrite_rejects_a_locked_field_before_the_provider(self):
        with patch.object(server.provider, 'rewrite_field', return_value={'text': 'generated'}) as provider:
            request = {'field': 'title', 'text': 'Original title', 'productId': 'product-1', 'market': 'US'}
            self.assertEqual(self.call('/api/listing/rewrite', request)[0], 400)
            provider.assert_not_called()
            self.assertEqual(self.call('/api/listing/rewrite', dict(request, field='description'))[0], 200)
            provider.assert_called_once()

    def test_candidate_adoption_preserves_current_lock_not_snapshot_lock(self):
        candidate = {'title': 'Candidate title', 'description': 'After', 'lockedFields': ['description'],
                     'translations': {'title': '候选'}, 'contentAudit': {'someRule': True}}
        merged = listing_locks.merge(self.state['copy'][self.key], candidate)
        self.assertEqual((merged['title'], merged['description']), ('Original title', 'After'))
        self.assertEqual(merged['translations']['title'], '原文')
        self.assertEqual(merged['lockedFields'], ['title'])
        self.assertNotIn('contentAudit', merged)
