import os
import tempfile
import unittest

from watchlist import load_watchlist_file, tradingview_to_yahoo


class WatchlistImportTest(unittest.TestCase):
    def test_tradingview_symbols_map_to_yahoo_tickers(self):
        self.assertEqual(tradingview_to_yahoo("NASDAQ:AAPL"), ("AAPL", None))
        self.assertEqual(tradingview_to_yahoo("CBOE:VIX"), ("^VIX", None))
        self.assertEqual(tradingview_to_yahoo("NYSE:BRK.B"), ("BRK-B", None))
        self.assertEqual(tradingview_to_yahoo("TSLA"), ("TSLA", None))

    def test_watchlist_file_returns_entries_and_skipped_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "swing.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# TradingView export symbols are allowed\n")
                f.write("NASDAQ:AAPL, NYSE:BABA, NASDAQ:AAPL\n")
                f.write("CRYPTOCAP:TOTAL3\n")
                f.write("BAD SYMBOL!\n")

            entries, skipped = load_watchlist_file(path)

        self.assertEqual(
            entries,
            [
                {"ticker": "AAPL", "type": "stock", "source": "NASDAQ:AAPL"},
                {"ticker": "BABA", "type": "stock", "source": "NYSE:BABA"},
            ],
        )
        self.assertEqual(skipped[0]["symbol"], "CRYPTOCAP:TOTAL3")
        self.assertIn("not available", skipped[0]["reason"])
        self.assertEqual(skipped[1]["symbol"], "BAD SYMBOL!")

    def test_watchlist_file_keeps_known_ticker_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tesla.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("NASDAQ:TSLA,NASDAQ:TSLL,CBOE:TSLZ")

            entries, skipped = load_watchlist_file(path)

        self.assertEqual(skipped, [])
        self.assertEqual(entries[1]["type"], "tsll_tslz")
        self.assertEqual(entries[1]["parent"], "TSLA")
        self.assertEqual(entries[2]["type"], "tsll_tslz")
        self.assertEqual(entries[2]["parent"], "TSLA")

    def test_missing_watchlist_file_has_clear_error(self):
        with self.assertRaisesRegex(FileNotFoundError, "Watchlist file not found"):
            load_watchlist_file("/tmp/does-not-exist-watchlist.txt")
