import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ego_browser


class EgoBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        cli = self.root / 'ego.exe'
        cli.touch()
        self.browser = {'engine': 'ego-lite', 'cli': str(cli), 'task_space_id': 4,
                        'task_space_name': 'publishing', 'script_directory': str(self.root/'pub'),
                        'task_bindings': {'selection': {'task_space_id': 7, 'task_space_name': 'selection',
                                                       'script_directory': str(self.root/'sel')}}}
        self.root_patch = patch.object(ego_browser, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def write_config(self):
        (self.root/'config.json').write_text(json.dumps({'browser': self.browser}), encoding='utf-8')

    def test_selection_identity_does_not_change_publishing_default(self):
        self.write_config()
        selected, _, _ = ego_browser.settings('selection')
        default, _, _ = ego_browser.settings()
        self.assertEqual((selected['task_space_id'], selected['task_space_name']), (7, 'selection'))
        self.assertEqual((default['task_space_id'], default['task_space_name']), (4, 'publishing'))
        self.assertNotEqual(selected['script_directory'], default['script_directory'])

    def test_unknown_binding_does_not_fall_back_to_publishing(self):
        self.write_config()
        with self.assertRaisesRegex(ValueError, '不回退'):
            ego_browser.settings('missing')

    def test_incomplete_binding_does_not_inherit_publishing_id(self):
        del self.browser['task_bindings']['selection']['task_space_id']
        self.write_config()
        with self.assertRaisesRegex(ValueError, '不继承'):
            ego_browser.settings('selection')

    def test_binding_invalid_id_is_rejected(self):
        self.browser['task_bindings']['selection']['task_space_id'] = True
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'TaskSpace ID'):
            ego_browser.settings('selection')
