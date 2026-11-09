"""Offline regression tests; no credentials, store requests or browser needed."""
import ast
import os
from html.parser import HTMLParser
from pathlib import Path
import re
import time
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / 'Collect_Rewards.py'
FUNCTIONS = {'confirmation_matches', 'success_modal_matches', 'confirm_claim'}


def collector_functions():
    tree = ast.parse(SOURCE.read_text())
    namespace = dict(re=re, time=time, save_debug=Mock(), save_html=Mock())
    exec(compile(ast.Module(body=[n for n in tree.body
         if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS],
         type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


class ReceiptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tag = None
        self.data = {'h3': '', 'p': ''}

    def handle_starttag(self, tag, attrs):
        if tag in self.data:
            self.tag = tag

    def handle_endtag(self, tag):
        if tag == self.tag:
            self.tag = None

    def handle_data(self, data):
        if self.tag:
            self.data[self.tag] += data


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.ns = collector_functions()
        self.matches = self.ns['confirmation_matches']
        self.title = 'DAILY FREE MARKET POINTS'

    def test_captured_store_receipt(self):
        # Receipt markup from run 338, stripped of images/account/page content.
        parser = ReceiptParser()
        parser.feed('<h3 class="L">Success</h3><p class="S">'
                    'Successfully Claimed:<br>DAILY FREE MARKET POINTS</p>')
        self.assertTrue(self.matches(parser.data['h3'], parser.data['p'], self.title))

    def test_rendered_uppercase_heading(self):
        self.assertTrue(self.matches('SUCCESS', 'Successfully Claimed:\n' + self.title, self.title))

    def test_whitespace_and_case(self):
        self.assertTrue(self.matches(' success ', 'SUCCESSFULLY CLAIMED :\n daily free  market points ', self.title))

    def test_wrong_reward_rejected(self):
        self.assertFalse(self.matches('Success', 'Successfully Claimed: ELDER DAILY CRYSTAL', self.title))

    def test_error_heading_rejected(self):
        self.assertFalse(self.matches('Error', 'Successfully Claimed:' + self.title, self.title))

    def test_missing_title_rejected(self):
        self.assertFalse(self.matches('Success', 'Successfully Claimed:', ''))

    def test_incomplete_receipt_waits(self):
        page = Mock()
        page.evaluate.side_effect = [None, {'heading': '', 'message': ''},
            {'heading': 'SUCCESS', 'message': 'Successfully Claimed:' + self.title}]
        self.assertTrue(self.ns['success_modal_matches'](page, self.title))
        self.assertEqual(page.wait_for_timeout.call_count, 2)

    def test_no_receipt_preserves_evidence(self):
        page = Mock()
        page.evaluate.return_value = None
        self.assertFalse(self.ns['success_modal_matches'](page, self.title, timeout_ms=0))
        self.ns['save_html'].assert_called_once()

    def test_disappearing_card_needs_matching_receipt(self):
        self.ns['reload_store'] = Mock(return_value=True)
        self.ns['scan_items'] = Mock(return_value=[{'key': 'crystal', 'soldOut': True}])
        self.assertTrue(self.ns['confirm_claim'](None, 'points', {}, True))
        with self.assertRaises(RuntimeError):
            self.ns['confirm_claim'](None, 'points', {}, False)

    def test_receipt_does_not_override_claimable_card(self):
        self.ns['reload_store'] = Mock(return_value=True)
        self.ns['scan_items'] = Mock(return_value=[{'key': 'points', 'soldOut': False}])
        self.assertFalse(self.ns['confirm_claim'](None, 'points', {}, True))

    def test_reload_failure_cannot_pass(self):
        self.ns['reload_store'] = Mock(return_value=False)
        with self.assertRaises(RuntimeError):
            self.ns['confirm_claim'](None, 'points', {}, True)

    def test_scan_failure_cannot_pass(self):
        self.ns['reload_store'] = Mock(return_value=True)
        self.ns['scan_items'] = Mock(side_effect=RuntimeError('scan failed'))
        with self.assertRaises(RuntimeError):
            self.ns['confirm_claim'](None, 'points', {}, True)


@unittest.skipUnless(os.getenv('MCOC_BROWSER_TESTS') == '1', 'Browser tests enabled in CI')
class BrowserConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_rendered_and_delayed_receipts(self):
        ns = collector_functions()
        page = self.browser.new_page()
        try:
            # Same receipt structure as the captured store HTML. Exercise CSS
            # capitalization and asynchronous insertion in an actual browser.
            page.set_content('<style>h3,p{text-transform:uppercase}</style><main></main>')
            page.evaluate('''() => setTimeout(() => {
                document.querySelector('main').innerHTML =
                  '<div class="purchase-handler-modal"><h3>Success</h3>' +
                  '<p>Successfully Claimed:<br>DAILY FREE MARKET POINTS</p>' +
                  '<button class="button-continue">CONTINUE SHOPPING</button></div>';
            }, 500)''')
            self.assertTrue(ns['success_modal_matches'](page, 'DAILY FREE MARKET POINTS'))
            self.assertEqual(page.locator('h3').inner_text(), 'SUCCESS')
            self.assertFalse(ns['success_modal_matches'](page, 'ELDER DAILY CRYSTAL', timeout_ms=0))
        finally:
            page.close()


if __name__ == '__main__':
    unittest.main()
