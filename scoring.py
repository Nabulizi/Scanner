"""
scoring.py — Checklist scoring engine
======================================
Mirrors your Google Sheets pre-trade checklist (25 checks, stocks only).

Verdict logic (fixed):
  Core gate:  ALL 3 signals must be present — FVG + BB + Stoch
              If any core signal is missing, max verdict is SKIP TRADE.

  Score tiers (only reached if core gate passes):
  ✅ TAKE THE TRADE  — all 3 core signals + score >= 16
  ⚠️  REDUCE SIZE    — 2 of 3 core signals or score 12–15
  🚫 SKIP TRADE      — fewer than 2 core signals or score < 12
"""

from config import DEFAULT_RULES, REDUCE_THRESHOLD, RISK_GATES, TAKE_THRESHOLD
from models import ScoreResult, SignalResult


CHECK_LABELS = {
    'daily_checked': 'Daily chart checked',
    'no_strong_downtrend': 'No strong daily downtrend',
    'no_strong_uptrend': 'No strong daily uptrend',
    'no_earnings_24h': 'No earnings within 24h',
    'no_fed_today': 'No Fed day',
    'no_tesla_news': 'No Tesla catalyst',
    'fvg_identified': 'FVG direction matches',
    'price_near_fvg': 'Price is inside the matching FVG',
    'bb_signal': 'Bollinger Band confirmation',
    'bb_not_expanding': 'Bollinger Bands not expanding',
    'stoch_confirmed': 'Stoch RSI confirmation',
    'stoch_not_mid_range': 'Stoch RSI not mid-range',
    'initial_size_3k': 'Initial size confirmed',
    'max_2_positions': 'Open positions within limit',
    'total_under_deployed_limit': 'Total deployed below limit',
    'max_avgdown_defined': 'Max average-down level defined',
    'profit_target_2_3pct': 'Profit target confirmed',
    'hard_stop_defined': 'Hard stop confirmed',
    'tsll_tslz_max_6k': 'TSLL/TSLZ position within cap',
    'position_within_cap': 'Position size within cap',
    'final_fvg': 'Final FVG gate',
    'final_bb': 'Final BB gate',
    'final_stoch': 'Final Stoch gate',
    'final_bias': 'Final daily bias gate',
    'final_no_news': 'Final no-catalyst gate',
}


def money(value):
    return f"${value:,.0f}"


def portfolio_rule(portfolio, key):
    return portfolio.get(key, DEFAULT_RULES[key])


def position_cap_for(portfolio, instrument_type):
    if instrument_type == 'tsll_tslz':
        return portfolio_rule(portfolio, 'max_tsll_tslz_position')
    return portfolio_rule(portfolio, 'max_stock_position')


def score_signals(ticker, signals: SignalResult, portfolio, instrument_type='stock') -> ScoreResult:
    checks    = {}
    direction = signals.get('direction', 'neutral')
    fvg       = signals.get('fvg', {})
    pos_size  = portfolio.get('position_size', 3_000)
    max_size  = position_cap_for(portfolio, instrument_type)
    max_open_positions = portfolio_rule(portfolio, 'max_open_positions')
    max_total_deployed = portfolio_rule(portfolio, 'max_total_deployed')

    # ── STEP 1 — Market Context ───────────────────────────────────────────────
    # Manual confirmations — set these in PORTFOLIO_STATE before each session
    checks['daily_checked']       = portfolio.get('daily_chart_checked', True)
    checks['no_strong_downtrend'] = portfolio.get('no_strong_downtrend', True)
    checks['no_strong_uptrend']   = portfolio.get('no_strong_uptrend', True)
    checks['no_earnings_24h']     = not signals.get('earnings_soon', False)
    checks['no_fed_today']        = not portfolio.get('fed_day', False)
    checks['no_tesla_news']       = not portfolio.get('tesla_catalyst', False)

    # ── STEP 2 — Setup Validation (the only checks that matter for verdict) ───
    # FVG direction must match trade direction to avoid signal mismatch
    if direction == 'long':
        checks['fvg_identified'] = fvg.get('bullish') is not None
        checks['price_near_fvg'] = (fvg.get('bullish') or {}).get('price_inside', False)
    elif direction == 'short':
        checks['fvg_identified'] = fvg.get('bearish') is not None
        checks['price_near_fvg'] = (fvg.get('bearish') or {}).get('price_inside', False)
    else:  # neutral — accept either
        checks['fvg_identified'] = (
            fvg.get('bullish') is not None or fvg.get('bearish') is not None
        )
        checks['price_near_fvg'] = (
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
    checks['max_2_positions']     = portfolio.get('open_positions', 0) <= max_open_positions
    checks['total_under_deployed_limit'] = portfolio.get('total_deployed', 0) < max_total_deployed
    checks['max_avgdown_defined'] = portfolio.get('max_avgdown_defined', True)

    # ── STEP 4 — Trade Parameters ──────────────────────────────────────────
    # Manual confirmations — set these in PORTFOLIO_STATE before each session
    checks['profit_target_2_3pct'] = portfolio.get('profit_target_confirmed', True)
    checks['hard_stop_defined']    = portfolio.get('hard_stop_confirmed', True)
    checks['tsll_tslz_max_6k']     = pos_size <= max_size if instrument_type == 'tsll_tslz' else True
    checks['position_within_cap']  = pos_size <= max_size

    # ── STEP 5 — Final Go/No-Go ───────────────────────────────────────────────
    checks['final_fvg']     = checks['fvg_identified']
    checks['final_bb']      = checks['bb_signal'] and checks['bb_not_expanding']
    checks['final_stoch']   = checks['stoch_confirmed'] and checks['stoch_not_mid_range']
    checks['final_bias']    = (
        checks['no_strong_downtrend'] if direction == 'long'
        else checks['no_strong_uptrend']
    )
    checks['final_no_news'] = (
        checks['no_earnings_24h'] and checks['no_fed_today'] and checks['no_tesla_news']
    )

    score = sum(1 for v in checks.values() if v)
    total = len(checks)   # 25

    # ── Verdict — risk veto then core gate ──────────────────────────────────────
    has_fvg   = checks['fvg_identified']
    has_bb    = checks['bb_signal'] and checks['bb_not_expanding']
    has_stoch = checks['stoch_confirmed'] and checks['stoch_not_mid_range']
    core_count = sum([has_fvg, has_bb, has_stoch])

    risk_gates = RISK_GATES
    risk_clear = all(checks[key] for key in risk_gates)
    risk_passed = sum(1 for key in risk_gates if checks[key])

    cap_label = 'TSLL/TSLZ' if instrument_type == 'tsll_tslz' else 'stock'
    hard_blockers = []
    data_quality = signals.get('data_quality') or {'valid': True, 'warnings': []}
    if not data_quality.get('valid', True):
        warnings = data_quality.get('warnings') or ['Data quality check failed']
        hard_blockers.append(f"Price data unavailable or incomplete: {warnings[0]}")
    if not checks['no_earnings_24h']:
        hard_blockers.append('Earnings within 24h')
    if not checks['no_fed_today']:
        hard_blockers.append('Fed day active')
    if not checks['no_tesla_news']:
        hard_blockers.append('Tesla catalyst active')
    if not checks['max_2_positions']:
        hard_blockers.append(f"Open positions exceed {max_open_positions}")
    if not checks['total_under_deployed_limit']:
        hard_blockers.append(f"Total deployed at or above {money(max_total_deployed)}")
    if not checks['position_within_cap']:
        hard_blockers.append(f"Position size exceeds {money(max_size)} {cap_label} cap")

    if hard_blockers or not risk_clear:
        verdict = "SKIP"
    elif core_count == 3 and score >= TAKE_THRESHOLD:
        verdict = "TAKE"
    elif core_count >= 2 and score >= REDUCE_THRESHOLD:
        verdict = "REDUCE"
    else:
        verdict = "SKIP"

    setup_reasons = []
    if not has_fvg:
        setup_reasons.append('FVG missing or direction-mismatched')
    if not has_bb:
        setup_reasons.append('Bollinger confirmation missing or expanding')
    if not has_stoch:
        setup_reasons.append('Stoch RSI confirmation missing or mid-range')

    blocker_reasons = hard_blockers or setup_reasons
    check_reasons = [
        {'key': key, 'passed': bool(value), 'label': CHECK_LABELS.get(key, key)}
        for key, value in checks.items()
    ]

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
        'hard_blockers': hard_blockers,
        'blocker_reasons': blocker_reasons,
        'check_reasons': check_reasons,
        'score_sections': {
            'core_setup': f"{core_count}/3",
            'risk_gates': f"{risk_passed}/{len(risk_gates)}",
            'checklist': f"{score}/{total}",
        },
    }
