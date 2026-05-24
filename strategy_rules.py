"""
strategy_rules.py — Default trading plan limits.

User-editable session values live in watchlist.py. These defaults keep the
scoring engine readable and provide fallbacks when a portfolio key is missing.
"""

DEFAULT_RULES = {
    'max_total_deployed': 60_000,
    'max_open_positions': 2,
    'max_stock_position': 10_000,
    'max_tsll_tslz_position': 6_000,
}

TAKE_THRESHOLD = 16
REDUCE_THRESHOLD = 12
