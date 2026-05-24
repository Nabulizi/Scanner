import unittest
from unittest.mock import patch

import pandas as pd

import indicators


def good_frame():
    rows = []
    for i in range(35):
        rows.append({
            'Open': 10 + i,
            'High': 11 + i,
            'Low': 9 + i,
            'Close': 10 + i,
            'Volume': 1000,
        })
    return pd.DataFrame(rows)


class FakeTicker:
    calls = 0

    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, period, interval):
        FakeTicker.calls += 1
        if FakeTicker.calls == 1:
            raise RuntimeError("temporary yahoo failure")
        return good_frame()


class DataFetchTest(unittest.TestCase):
    def setUp(self):
        indicators.clear_ohlcv_cache()
        FakeTicker.calls = 0

    def test_fetch_ohlcv_retries_then_caches(self):
        with patch.object(indicators.yf, 'Ticker', FakeTicker):
            first = indicators.fetch_ohlcv("AAPL")
            second = indicators.fetch_ohlcv("AAPL")

        self.assertEqual(len(first), 35)
        self.assertEqual(len(second), 35)
        self.assertEqual(FakeTicker.calls, 2)

    def test_fetch_ohlcv_error_mentions_attempts(self):
        class AlwaysFails:
            def __init__(self, ticker):
                self.ticker = ticker

            def history(self, period, interval):
                raise RuntimeError("downstream unavailable")

        with patch.object(indicators.yf, 'Ticker', AlwaysFails):
            with self.assertRaisesRegex(ValueError, "Could not fetch 1H data for MSFT after 2 attempts"):
                indicators.fetch_ohlcv("MSFT")
