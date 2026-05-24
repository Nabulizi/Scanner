"""
scoring.py — Checklist scoring engine
======================================
Mirrors your Google Sheets pre-trade checklist (26 checks).

Verdict logic (fixed):
  Core gate:  ALL 3 signals must be present — FVG + BB + Stoch
              If any core signal is missing, max verdict is SKIP TRADE.

  Score tiers (only reached if core gate passes):
  ✅ TAKE THE TRADE  — all 3 core signals + score >= 16
  ⚠️  REDUCE SIZE    — 2 of 3 core signals or score 12–15
  🚫 SKIP TRADE      — fewer than 2 core signals or score < 12
"""

MAX_SIZE = {
    'tsll_tslz': 6_000,
    'crypto':    6_000,
    'stock':    10_000,
}

TAKE_THRESHOLD   = 16
REDUCE_THRESHOLD = 12


def score_signals(ticker, signals, portfolio, instrument_type='stock'):
    checks    = {}
    direction = signals.get('direction', 'neutral')
    fvg       = signals.get('fvg', {})
    pos_size  = portfolio.get('position_size', 3_000)
    max_size  = MAX_SIZE.get(instrument_type, 10_000)

    # ── STEP 1 — Market Context ───────────────────────────────────────────────
    # Manual confirmations — set these in PORTFOLIO_STATE before each session
    checks['daily_checked']       = portfolio.get('daily_chart_checked', True)
    checks['no_strong_downtrend'] = portfolio.get('no_strong_downtrend', True)
    checks['no_strong_uptrend']   = portfolio.get('no_strong_uptrend', True)
    checks['no_earnings_24h']     = not signals.get('earnings_soon', False)
    checks['no_fed_today']        = not portfolio.get('fed_day', False)
    checks['no_tesla_news']       = not portfolio.get('tesla_catalyst', False)

    # ── STEP 2 — Setup Validation (the only checks that matter for verdict) ───
    has_bullish = fvg.get('bullish') is not None
    has_bearish = fvg.get('bearish') is not None

    checks['fvg_identified']      = has_bullish or has_bearish
    checks['price_near_fvg']      = (
        (fvg.get('bullish') or {}).get('price_inside', False) or
        (fvg.get('bearish') or {}).get('price_inside', False)
    )

    if direction == 'short':
        checks['bb_signal'] = signals.get('near_upper_bb', False)
    elif direction == 'long':
        checks['bb_signal'] = signals.get('near_lower_bb', False)
    else:  # neutral — accept either band touch
        checks['bb_signal'] = (
            signals.get('near_lower_bb', False) or
            signals.get('near_upper_bb', False)
        )

    checks['bb_not_expanding']    = not signals.get('bb_expanding', True)

    if direction == 'short':
        checks['stoch_confirmed'] = signals.get('stoch_overbought_cross', False)
    else:
        checks['stoch_confirmed'] = signals.get('stoch_oversold_cross', False)

    checks['stoch_not_mid_range'] = not signals.get('stoch_mid_range', True)

    # ── STEP 3 — Position Sizing ──────────────────────────────────────────────
    # Manual confirmations — set these in PORTFOLIO_STATE before each session
    checks['initial_size_3k']     = portfolio.get('initial_size_confirmed', True)
    checks['max_2_positions']     = portfolio.get('open_positions', 0) <= 2
    checks['total_under_60k']     = portfolio.get('total_deployed', 0) < 60_000
    checks['max_avgdown_defined'] = portfolio.get('max_avgdown_defined', True)

    # ── STEP 4 — Trade Parameters ──────────────────────────────────────────
    # Manual confirmations — set these in PORTFOLIO_STATE before each session
    checks['profit_target_2_3pct'] = portfolio.get('profit_target_confirmed', True)
    checks['hard_stop_defined']    = portfolio.get('hard_stop_confirmed', True)
    checks['tsll_tslz_max_6k']     = pos_size <= 6_000 if instrument_type == 'tsll_tslz' else True
    checks['crypto_max_6k']        = pos_size <= 6_000 if instrument_type == 'crypto'    else True
    checks['position_within_cap']  = pos_size <= max_size

    # ── STEP 5 — Final Go/No-Go ───────────────────────────────────────────────
    checks['final_fvg']     = checks['fvg_identified']
    checks['final_bb']      = checks['bb_signal'] and checks['bb_not_expanding']
    checks['final_stoch']   = checks['stoch_confirmed'] and checks['stoch_not_mid_range']
    checks['final_bias']    = (
        checks['no_strong_downtrend'] if direction == 'long'
        else checks['no_strong_uptrend']
    )
    checks['final_no_news'] = checks['no_earnings_24h'] and checks['no_fed_today']

    score = sum(1 for v in checks.values() if v)
    total = len(checks)   # 26

    # ── Verdict — core gate first ─────────────────────────────────────────────
    has_fvg   = checks['fvg_identified']
    has_bb    = checks['bb_signal'] and checks['bb_not_expanding']
    has_stoch = checks['stoch_confirmed'] and checks['stoch_not_mid_range']
    core_count = sum([has_fvg, has_bb, has_stoch])

    if core_count == 3 and score >= TAKE_THRESHOLD:
        verdict = "TAKE"
    elif core_count >= 2 and score >= REDUCE_THRESHOLD:
        verdict = "REDUCE"
    else:
        verdict = "SKIP"

    return {
        'ticker':      ticker,
        'score':       score,
        'total':       total,
        'verdict':     verdict,
        'direction':   direction,
        'checks':      checks,
        'fvg_detail':  fvg,
        'core_count':  core_count,
        'has_fvg':     has_fvg,
        'has_bb':      has_bb,
        'has_stoch':   has_stoch,
    }
