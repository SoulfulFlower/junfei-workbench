import json
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import portable_support as portable
import runtime_environment as runtime


class PortableSupportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / 'bundle'
        self.source = self.base / 'portable-runtime'
        (self.source / 'automation').mkdir(parents=True)
        (self.source / 'automation/config.json').write_text('{}', encoding='utf-8')
        (self.source / 'automation/ego_browser.py').write_text('# never executed in this fixture', encoding='utf-8')
        (self.base / portable.MARKER).write_text(json.dumps({'schemaVersion': 1, 'buildId': 'test-build', 'runtimeFiles': {'automation/ego_browser.py': hashlib.sha256((self.source/'automation/ego_browser.py').read_bytes()).hexdigest()}}), encoding='utf-8')
        self.data = Path(self.temp.name) / 'new profile'
        self.env = {'JUNFEI_ACCOUNT_DATA': str(self.data)}

    def test_clean_runtime_is_copied_to_writable_profile_without_pointer(self):
        self.assertTrue(portable.configure(self.base, self.env))
        root = Path(self.env['JUNFEI_PROJECT_ROOT'])
        self.assertEqual(root, self.data / 'portable-runtime')
        self.assertTrue((root / 'automation/config.json').is_file())
        self.assertFalse((root / 'project-root.txt').exists())
        self.assertEqual(self.env['JUNFEI_PORT'], '18768')

    def test_restart_preserves_configuration_and_execution_records(self):
        portable.configure(self.base, self.env)
        root = Path(self.env['JUNFEI_PROJECT_ROOT'])
        config = root / 'automation/config.json'
        config.write_text('{"operatorSetting": true}', encoding='utf-8')
        ledger = root / 'automation/data'
        ledger.mkdir()
        (ledger / 'receipt.json').write_text('{"status":"unknown"}', encoding='utf-8')
        env = {'JUNFEI_ACCOUNT_DATA': str(self.data)}
        portable.configure(self.base, env)
        self.assertEqual(config.read_text(), '{"operatorSetting": true}')
        self.assertEqual((ledger / 'receipt.json').read_text(), '{"status":"unknown"}')

    def test_different_release_never_overwrites_existing_state(self):
        portable.configure(self.base, self.env)
        (self.base / portable.MARKER).write_text(json.dumps({'schemaVersion': 1, 'buildId': 'new-build'}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'another build'):
            portable.configure(self.base, {'JUNFEI_ACCOUNT_DATA': str(self.data)})

    def test_existing_unmarked_directory_is_not_adopted(self):
        (self.data / 'portable-runtime').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'no install marker'):
            portable.configure(self.base, self.env)

    def test_source_mode_has_no_side_effect(self):
        self.assertFalse(portable.configure(Path(self.temp.name), self.env))
        self.assertFalse(self.data.exists())

    def test_help_dispatch_does_not_configure_data_or_import_server(self):
        before = set(Path(self.temp.name).rglob('*'))
        with patch.dict(os.environ, {'JUNFEI_ACCOUNT_DATA': str(self.data)}, clear=True), patch.object(portable.runpy, 'run_path') as run:
            self.assertTrue(portable.handle_cli(self.base, ['--workbench-tool', 'ego-browser', '--help']))
            run.assert_called_once_with(str(self.source / 'automation/ego_browser.py'), run_name='__main__')
        self.assertEqual(before, set(Path(self.temp.name).rglob('*')))
        self.assertFalse(self.data.exists())

    def test_cli_cannot_dispatch_arbitrary_python_files(self):
        with self.assertRaises(ValueError):
            portable.handle_cli(self.base, ['--workbench-tool', '../../other.py'])

    def test_self_check_writes_only_explicit_new_report(self):
        report = Path(self.temp.name) / 'report.json'
        with patch.dict(os.environ, {'JUNFEI_ACCOUNT_DATA': str(self.data)}, clear=True):
            portable.handle_cli(self.base, ['--self-check', str(report)])
            with self.assertRaises(FileExistsError):
                portable.handle_cli(self.base, ['--self-check', str(report)])
        self.assertTrue(json.loads(report.read_text(encoding='utf-8'))['readOnly'])
        self.assertFalse(self.data.exists())

    def test_frozen_ego_uses_fixed_bundled_dispatch_without_python_on_path(self):
        with patch.object(runtime.sys, 'frozen', True, create=True), patch.object(runtime.sys, 'executable', 'agent.exe'), patch.object(runtime.shutil, 'which', return_value=None):
            self.assertEqual(runtime.ego_command(self.source, {}), ['agent.exe', '--workbench-tool', 'ego-browser'])

    def test_changed_immutable_runtime_stops_without_overwrite(self):
        portable.configure(self.base, self.env)
        script = Path(self.env['JUNFEI_PROJECT_ROOT']) / 'automation/ego_browser.py'
        script.write_text('modified', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed or is missing'):
            portable.configure(self.base, {'JUNFEI_ACCOUNT_DATA': str(self.data)})
        self.assertEqual(script.read_text(), 'modified')

    def test_self_check_reads_existing_profile_without_writes(self):
        portable.configure(self.base, self.env)
        report = Path(self.temp.name) / 'profile-check.json'
        with patch.dict(os.environ, {'JUNFEI_ACCOUNT_DATA': str(self.data)}, clear=True):
            portable.handle_cli(self.base, ['--self-check', str(report)])
        self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['projectRoot'], str(self.data / 'portable-runtime'))

    def test_packaged_source_download_returns_corresponding_archive(self):
        import studio_bridge
        archive = self.base / 'corresponding-source.zip'
        archive.write_bytes(b'test source archive')
        with patch.object(studio_bridge, '__file__', str(self.base / 'studio_bridge.py')):
            self.assertEqual(studio_bridge.source_archive(), archive.read_bytes())

    def test_missing_ego_adapter_fails_before_launch(self):
        (self.source / 'automation/ego_browser.py').unlink()
        with self.assertRaises(FileNotFoundError):
            runtime.ego_command(self.source, {})


if __name__ == '__main__':
    unittest.main()
