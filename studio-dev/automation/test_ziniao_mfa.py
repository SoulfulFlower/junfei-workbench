import json
import unittest
from unittest.mock import Mock, patch
import ziniao_mfa as mfa


class MfaTests(unittest.TestCase):
    def test_autofilled_code_is_submitted_once_and_navigation_is_observed(self):
        run = Mock(return_value={'ok': True})
        with patch.object(mfa, 'inspect', side_effect=['ready', 'left_mfa']):
            result = mfa.submit_autofilled(run, 'cli', store_id='123',
                origin='https://sellercentral.amazon.com', deadline=mfa.time.monotonic()+1)
        self.assertEqual(result['status'], 'left_mfa')
        self.assertTrue(result['submitted'])
        self.assertFalse(result['otpRecorded'])
        run.assert_called_once()
        self.assertIn('#auth-signin-button', run.call_args.args)

    def test_rejected_code_requires_native_refresh_before_another_submission(self):
        run = Mock()
        with patch.object(mfa, 'inspect', return_value='code_rejected'):
            result = mfa.submit_autofilled(run, 'cli', store_id='123',
                origin='https://sellercentral.amazon.com', deadline=mfa.time.monotonic()+1)
        self.assertEqual(result['status'], 'refresh_required')
        run.assert_not_called()

    def test_inspection_only_returns_state(self):
        run = Mock(return_value={'ok': True, 'data': {'data': {'result': json.dumps({'state':'ready'})}}})
        self.assertEqual(mfa.inspect(run, 'cli', '123', 'https://sellercentral.amazon.com'), 'ready')
        script = run.call_args.args[-1]
        self.assertNotIn('value:fields', script)
        self.assertIn("location.origin", script)
