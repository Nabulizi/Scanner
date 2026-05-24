"""
watchlist.py — Edit this file to match your positions and tickers.
==================================================================
Types:
  'tsll_tslz' — Leveraged Tesla ETFs (max $6K per position, 1 add only)
  'crypto'    — BTC, ETH, DOGE, IBIT, BITI, etc. (max $6K per position)
  'stock'     — Large cap stocks, regular ETFs (max $10K per position)
"""

# ── Your watchlist ────────────────────────────────────────────────────────────
# Add or remove tickers freely. Scanner will pull 1H data for each.

WATCHLIST = [
    # ── Tesla Leveraged ETFs (your #1 strategy by volume) ──
    {"ticker": "TSLL", "type": "tsll_tslz"},
    {"ticker": "TSLZ", "type": "tsll_tslz"},

    # ── Crypto / Bitcoin ETFs ──
    {"ticker": "IBIT", "type": "crypto"},
    {"ticker": "BITI", "type": "crypto"},
    {"ticker": "BTC-USD",  "type": "crypto"},
    {"ticker": "ETH-USD",  "type": "crypto"},
    {"ticker": "DOGE-USD", "type": "crypto"},

    # ── Large Cap Stocks (your NFLX/BABA high-avg-win plays) ──
    {"ticker": "NFLX", "type": "stock"},
    {"ticker": "BABA", "type": "stock"},
    {"ticker": "AAPL", "type": "stock"},
    {"ticker": "NVDA", "type": "stock"},
    {"ticker": "TSLA", "type": "stock"},   # underlying, not leveraged ETF

    # ── Add more tickers here ──
    # {"ticker": "AMZN", "type": "stock"},
    # {"ticker": "META", "type": "stock"},
    # {"ticker": "UNI-USD", "type": "crypto"},
]


# ── Your current portfolio state ──────────────────────────────────────────────
# Update before each scan session. Scanner uses this for Step 3 scoring.

PORTFOLIO_STATE = {
    # Total capital currently deployed across ALL open positions ($)
    "total_deployed":   0,

    # Number of currently open positions
    "open_positions":   0,

    # Are any of these active conditions true today?
    "fed_day":          False,   # Fed announcement / FOMC today
    "tesla_catalyst":   False,   # Elon tweet / delivery data / Tesla news day

    # Default new position size (scanner uses $3,000 per your rules)
    "position_size":    3000,

    # ── Manual pre-session confirmations ───────────────────────────────────
    # Review and update these before each scan session.
    # Keeping them True means the check always passes; set to False to block trades.
    "daily_chart_checked":     True,   # Have you reviewed the daily chart?
    "no_strong_downtrend":     True,   # No strong downtrend visible on daily
    "no_strong_uptrend":       True,   # No strong uptrend visible on daily
    "initial_size_confirmed":  True,   # Position sized at $3K initial entry
    "max_avgdown_defined":     True,   # Max avg-down level written down
    "profit_target_confirmed": True,   # 2–3% profit target set before entry
    "hard_stop_confirmed":     True,   # Hard stop level defined before entry
}
