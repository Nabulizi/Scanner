"""
watchlist.py — Edit this file to match your positions and tickers.
==================================================================
Types:
  'tsll_tslz' — Leveraged Tesla ETFs (max $6K per position, 1 add only)
  'stock'     — Large cap stocks, regular ETFs (max $10K per position)

This scanner is configured for stocks only. Crypto tickers are excluded.

parent field (optional):
  If a ticker has a 'parent' set and that parent stock is also in the watchlist,
  the derivative (ETF) is automatically skipped. Scan the underlying stock instead.
  Example: TSLL and TSLZ both have parent='TSLA'. If TSLA is in the list, they’re skipped.
"""

import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_DIR = os.path.join(SCRIPT_DIR, "watchlists")

UNSUPPORTED_PREFIXES = {"CRYPTOCAP"}
SYMBOL_RE = re.compile(r"^[A-Z0-9.\-\^=]{1,20}$")

EXPLICIT_SYMBOL_MAP = {
    "CBOE:VIX": "^VIX",
    "SP:SPX": "^GSPC",
}

EXCHANGE_PREFIXES = {"NASDAQ", "NYSE", "AMEX", "CBOE"}


def tradingview_to_yahoo(token: str):
    """Map a TradingView export token to a Yahoo-friendly ticker."""
    token = token.strip().upper()
    if not token:
        return None, "empty symbol"

    if token in EXPLICIT_SYMBOL_MAP:
        return EXPLICIT_SYMBOL_MAP[token], None

    if ":" not in token:
        if not SYMBOL_RE.match(token):
            return None, f"invalid characters in symbol: {token!r}"
        return token.replace(".", "-"), None

    prefix, symbol = token.split(":", 1)
    if prefix in UNSUPPORTED_PREFIXES:
        return None, f"{prefix} is not available from Yahoo-style feeds"
    if prefix in EXCHANGE_PREFIXES:
        if not SYMBOL_RE.match(symbol):
            return None, f"invalid characters in symbol: {symbol!r}"
        return symbol.replace(".", "-"), None

    return None, f"no mapper for {prefix}:{symbol}"


def _tokens_from_file(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise FileNotFoundError(f"Watchlist file not found: {path}")
    raw = ",".join(line.split("#", 1)[0] for line in lines)
    return [t.strip() for t in raw.split(",") if t.strip()]


def resolve_watchlist_path(name_or_path: str) -> str:
    if os.path.isabs(name_or_path) or os.path.exists(name_or_path):
        return name_or_path
    filename = name_or_path if name_or_path.endswith(".txt") else f"{name_or_path}.txt"
    return os.path.join(WATCHLIST_DIR, filename)


def load_watchlist_file(path: str):
    """Load a comma/newline separated watchlist file."""
    entries, skipped, seen = [], [], set()
    default_metadata = {
        entry['ticker']: {k: v for k, v in entry.items() if k != 'ticker'}
        for entry in WATCHLIST
    }
    for token in _tokens_from_file(path):
        ticker, reason = tradingview_to_yahoo(token)
        if not ticker:
            skipped.append({"symbol": token, "reason": reason})
            continue
        if ticker in seen:
            continue
        entry = {"ticker": ticker, "type": "stock", "source": token.strip().upper()}
        entry.update(default_metadata.get(ticker, {}))
        entries.append(entry)
        seen.add(ticker)
    return entries, skipped

# ── Your watchlist ────────────────────────────────────────────────────────────
# Add or remove tickers freely. Scanner will pull 1H data for each.

WATCHLIST = [
    # ── Tesla Leveraged ETFs (your #1 strategy by volume) ──
    # parent='TSLA' — these are skipped automatically when TSLA is in the list
    {"ticker": "TSLL", "type": "tsll_tslz", "parent": "TSLA"},
    {"ticker": "TSLZ", "type": "tsll_tslz", "parent": "TSLA"},

    # ── Large Cap Stocks (your NFLX/BABA high-avg-win plays) ──
    {"ticker": "NFLX", "type": "stock"},
    {"ticker": "BABA", "type": "stock"},
    {"ticker": "AAPL", "type": "stock"},
    {"ticker": "NVDA", "type": "stock"},
    {"ticker": "TSLA", "type": "stock"},   # underlying — TSLL/TSLZ skipped when this is present

    # ── Add more tickers here ──
    # {"ticker": "AMZN", "type": "stock"},
    # {"ticker": "META", "type": "stock"},
    # {"ticker": "MSFT", "type": "stock"},
    # {"ticker": "GOOGL", "type": "stock"},
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

    # ── Strategy limits ─────────────────────────────────────────────────────
    # These are hard risk gates. If one fails, the scanner returns SKIP even
    # when the technical setup is otherwise clean.
    "max_total_deployed":      60000,
    "max_open_positions":     2,
    "max_stock_position":     10000,
    "max_tsll_tslz_position": 6000,

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
