import json
import unittest

from publication_browser_result import MARKER, current_browser_error


class BrowserResultTests(unittest.TestCase):
    def marker(self, **changes):
        value = dict(version=1, kind='application_job_error', binding='dedicated',
                     scriptSha256='a'*64, message='专属采集浏览器连接已变化，请重新连接', stack='Error: current')
        value.update(changes)
        return MARKER+json.dumps(value)

    def test_current_complete_error_overrides_stale_receipt_message(self):
        error = current_browser_error(b'normal output', self.marker().encode(), 'dedicated', 'a'*64)
        self.assertEqual(error, '专属采集浏览器连接已变化，请重新连接')

    def test_other_invocations_and_incomplete_markers_are_ignored(self):
        for output in (self.marker(scriptSha256='b'*64), self.marker(binding='other'),
                       self.marker(version=True), self.marker(stack=None), MARKER+'{"message":'):
            self.assertIsNone(current_browser_error(output, '', 'dedicated', 'a'*64))

    def test_error_message_is_bounded_and_raw_output_not_exposed(self):
        self.assertEqual(current_browser_error('untrusted raw output', '', 'dedicated', 'a'*64), None)
        self.assertEqual(len(current_browser_error(self.marker(message='x'*2000), '', 'dedicated', 'a'*64)), 1500)
