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

# ── Verdict thresholds ────────────────────────────────────────────────────────
# Score is now out of 20 signal-quality checks (5 administrative defaults that
# were always True have been moved to hard gates and excluded from the score).
# Selectivity is kept proportionally the same as the original 16/25 and 12/25.
TAKE_THRESHOLD   = 13   # ≥65% of scored checks must pass
REDUCE_THRESHOLD = 10   # ≥50% of scored checks must pass

# ── Risk gates — must all pass or verdict is SKIP regardless of score ─────────
RISK_GATES = [
    'no_earnings_24h',
    'no_fed_today',
    'no_tesla_news',
    'max_2_positions',
    'total_under_deployed_limit',
    'position_within_cap',
]

# ── Data quality parameters ───────────────────────────────────────────────────
CACHE_TTL_SECONDS    = 900    # 15-minute OHLCV cache expiry; prevents stale signals
                               # in long-running processes or repeated scans

# ── FVG detection parameters ──────────────────────────────────────────────────
MIN_FVG_SIZE_PCT     = 0.0010  # 0.10% minimum — below this is bid/ask noise
MIN_FVG_AGE_BARS     = 2       # gap must be ≥2 bars old so there is a fill-check period

# ── Stochastic RSI parameters ─────────────────────────────────────────────────
STOCH_CROSS_LOOKBACK = 3       # a confirmed cross remains actionable for this many bars

# ── Bollinger Band expansion parameters ───────────────────────────────────────
BB_EXPAND_LOOKBACK   = 20      # rolling-window baseline (was 5 — too noisy)

# ── Daily trend filter ────────────────────────────────────────────────────────
DAILY_EMA_FAST       = 20      # fast EMA period for daily trend detection
DAILY_EMA_SLOW       = 50      # slow EMA period for daily trend detection
