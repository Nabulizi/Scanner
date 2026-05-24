"""
config.py — User-tunable scanner rules.

Edit these defaults when the trading plan changes. Per-session values in
watchlist.py override DEFAULT_RULES without changing scoring logic.
"""

DEFAULT_RULES = {
    'max_total_deployed': 60_000,
    'max_open_positions': 2,
    'max_stock_position': 10_000,
    'max_tsll_tslz_position': 6_000,
}

TAKE_THRESHOLD = 16
REDUCE_THRESHOLD = 12

RISK_GATES = [
    'no_earnings_24h',
    'no_fed_today',
    'no_tesla_news',
    'max_2_positions',
    'total_under_deployed_limit',
    'position_within_cap',
]
