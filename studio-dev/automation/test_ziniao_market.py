import json
import subprocess
import unittest
from unittest.mock import Mock, patch
import ziniao_market as market


def execution(stage, **fields):
    return {'ok': True, 'data': {'ok': True, 'data': {'exceptionDetails': None,
            'result': json.dumps({'ok': True, 'stage': stage, **fields})}}}


GEOMETRY = {'ok': False, 'error': {'message': 'coordinate input geometry is unavailable'}}
ROW = '.dropdown-account-switcher.account-switcher-root .dropdown-account-switcher-list-item[title="英国"]'


class MarketTests(unittest.TestCase):
    def select(self, run, allow_dom_click=False):
        with patch.object(market.time, 'monotonic', return_value=1):
            return market.select_observed_market(run, 'cli', store_id='123', market='UK', seller='Example Store', deadline=20,
                                                 allow_dom_click=allow_dom_click)

    def test_already_open_menu_never_clicks_header_and_uses_trusted_row_input_first(self):
        run = Mock(side_effect=[execution('ready', selector=ROW), {'ok': True}])
        result = self.select(run)
        self.assertTrue(result['attempted']);self.assertFalse(result['confirmed'])
        self.assertEqual(result['method'], 'ziniao_cli_trusted_click')
        self.assertEqual(run.call_count, 2)
        self.assertIn(ROW, run.call_args.args)

    def test_only_known_geometry_failure_allows_fresh_guarded_dom_fallback(self):
        run = Mock(side_effect=[execution('ready', selector=ROW), GEOMETRY,
                               execution('ready', selector=ROW), execution('market_click_requested', clicked=True)])
        result = self.select(run, allow_dom_click=True)
        self.assertEqual(result['method'], 'user_authorized_DOM_click')
        self.assertTrue(result['nativeInputUnavailable']);self.assertFalse(result['confirmed'])
        self.assertEqual(sum(call.args[1:3] == ('page', 'click') for call in run.call_args_list), 1)
        self.assertIn('"action": "click"', run.call_args.args[-1])

    def test_default_native_only_market_switch_never_uses_dom_after_geometry_failure(self):
        run = Mock(side_effect=[execution('ready', selector=ROW), GEOMETRY, execution('ready', selector=ROW)])
        result = self.select(run)
        self.assertTrue(result['nativeInputUnavailable']);self.assertTrue(result['resultUnknown'])
        self.assertEqual(result['method'], 'ziniao_cli_trusted_click');self.assertEqual(run.call_count, 3)
        self.assertNotIn('"action": "click"', run.call_args.args[-1])

    def test_unknown_native_result_is_not_replayed_with_dom(self):
        for response in [subprocess.TimeoutExpired('cli', 1), {'ok': False, 'error': {'message': 'unknown result'}},
                         {'ok': True, 'data': {'ok': False, 'error': {'message': 'unknown nested result'}}}]:
            run = Mock(side_effect=[execution('ready', selector=ROW), response])
            result = self.select(run)
            self.assertTrue(result['resultUnknown']);self.assertFalse(result['confirmed'])
            self.assertEqual(run.call_count, 2)

    def test_page_already_changed_after_geometry_error_prevents_second_click(self):
        run = Mock(side_effect=[execution('ready', selector=ROW), GEOMETRY, execution('already_selected', clicked=False)])
        result = self.select(run)
        self.assertEqual(run.call_count, 3);self.assertNotIn('nativeInputUnavailable', result)

    def test_already_selected_and_guard_failures_do_not_send_any_click(self):
        run = Mock(return_value=execution('already_selected', clicked=False))
        self.assertFalse(self.select(run)['attempted']);run.assert_called_once()
        for reason in ['seller_mismatch', 'ambiguous_market', 'obscured']:
            response = {'ok': True, 'data': {'result': json.dumps({'ok': False, 'stage': 'guard', 'reason': reason})}}
            run = Mock(return_value=response)
            with self.assertRaises(market.MarketSelectionError) as error:self.select(run)
            self.assertEqual(error.exception.error_type, 'market_selection_' + reason);run.assert_called_once()

    def test_exec_exception_details_and_unknown_reason_never_leak_raw_message(self):
        for data in [{'exceptionDetails': {'text': 'PRIVATE'}, 'result': ''},
                     {'result': '{"ok":false,"stage":"guard","reason":"PRIVATE"}'}]:
            with self.assertRaises(market.MarketSelectionError) as error:self.select(Mock(return_value={'ok': True, 'data': data}))
            self.assertNotIn('PRIVATE', str(error.exception));self.assertNotIn('PRIVATE', error.exception.error_type)


if __name__ == '__main__':unittest.main()
