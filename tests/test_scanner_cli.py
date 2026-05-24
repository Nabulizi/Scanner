import io
import json
import unittest
from contextlib import redirect_stdout

import scanner


def fake_signals(ticker):
    return {
        'direction': 'long',
        'fvg': {'bullish': {'price_inside': True}, 'bearish': None},
        'near_lower_bb': True,
        'near_upper_bb': False,
        'bb_expanding': False,
        'stoch_oversold_cross': True,
        'stoch_overbought_cross': False,
        'stoch_mid_range': False,
        'earnings_soon': False,
        'data_quality': {'valid': True, 'bars_returned': 35, 'required_bars': 30, 'warnings': []},
        'price_data': {'close': 10, 'bb_lower': 9, 'bb_upper': 12, 'bb_mid': 10.5, 'stoch_k': 15, 'stoch_d': 12},
    }


class ScannerCliTest(unittest.TestCase):
    def test_run_scan_json_outputs_payload(self):
        original_watchlist = scanner.WATCHLIST
        original_fetch = scanner.fetch_and_analyze
        scanner.WATCHLIST = [{'ticker': 'AAPL', 'type': 'stock'}]
        scanner.fetch_and_analyze = fake_signals
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                payload = scanner.run_scan(output_json=True)
        finally:
            scanner.WATCHLIST = original_watchlist
            scanner.fetch_and_analyze = original_fetch

        printed = json.loads(out.getvalue())
        self.assertEqual(payload['results'][0]['ticker'], 'AAPL')
        self.assertEqual(printed['results'][0]['ticker'], 'AAPL')
        self.assertEqual(printed['errors'], [])

    def test_build_scan_entries_reports_skipped_symbols(self):
        entries, skipped = scanner.build_scan_entries(
            watchlist_entries=[{'ticker': 'TSLL', 'type': 'tsll_tslz', 'parent': 'TSLA'}, {'ticker': 'TSLA', 'type': 'stock'}],
            file_skipped=[{'symbol': 'BAD', 'reason': 'invalid'}],
        )

        self.assertEqual(entries, [{'ticker': 'TSLA', 'type': 'stock'}])
        self.assertEqual(skipped[0]['symbol'], 'BAD')
        self.assertEqual(skipped[1]['symbol'], 'TSLL')
        self.assertIn('parent TSLA', skipped[1]['reason'])
