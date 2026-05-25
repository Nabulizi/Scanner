"""
portfolio.py — Portfolio state loader
======================================
Resolves the active portfolio state from three sources, in priority order:

  1. CLI flags        --positions / --deployed / --fed / --catalyst
  2. portfolio.json   persists between runs on the same day
  3. watchlist.py     PORTFOLIO_STATE — fallback / strategy-limit defaults

Also auto-detects Fed/FOMC announcement days from a hardcoded schedule so
you never have to set fed_day=True manually.

Usage from scanner.py:
    from portfolio import load_portfolio, save_portfolio

    portfolio, warnings = load_portfolio(overrides={'open_positions': 1, 'total_deployed': 9500})
    save_portfolio(portfolio)   # only called when CLI flags were provided
"""

from __future__ import annotations

import json
import os
from datetime import date

PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolio.json')

# ── FOMC announcement days ────────────────────────────────────────────────────
# These are the SECOND day of each 2-day FOMC meeting — when the rate decision
# is announced. Traders avoid new entries on these days due to extreme volatility.
#
# Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
# Update this set each January when the Fed publishes the new year's schedule.

FOMC_DATES = {
    # ── 2025 ──
    date(2025,  1, 29),
    date(2025,  3, 19),
    date(2025,  5,  7),
    date(2025,  6, 18),
    date(2025,  7, 30),
    date(2025,  9, 17),
    date(2025, 10, 29),
    date(2025, 12, 10),
    # ── 2026 ──
    date(2026,  1, 28),
    date(2026,  3, 18),
    date(2026,  4, 29),
    date(2026,  6, 17),
    date(2026,  7, 29),
    date(2026,  9, 16),
    date(2026, 10, 28),
    date(2026, 12,  9),
}


def is_fomc_today() -> bool:
    """Return True if today is a scheduled Fed announcement day."""
    return date.today() in FOMC_DATES


# Fields that are runtime-mutable (saved/loaded).
# Strategy limits (max_total_deployed etc.) stay in watchlist.py and are never
# overwritten by portfolio.json — they belong to your trading rules, not your
# session state.
_MUTABLE_KEYS = {
    'total_deployed',
    'open_positions',
    'fed_day',
    'tesla_catalyst',
    'position_size',
}


def load_portfolio(overrides: dict | None = None) -> tuple[dict, list[str]]:
    """
    Build and return (portfolio_state, warnings).

    Layer 3 — watchlist.py PORTFOLIO_STATE  (strategy limits + defaults)
    Layer 2 — portfolio.json                (last saved session state)
    Layer 1 — overrides dict                (CLI flags, highest priority)

    Auto-detection: if today is an FOMC day, fed_day is forced True
    regardless of what portfolio.json or overrides say.

    Stale warning: emitted when portfolio.json was saved on a previous day
    AND has open positions or deployed capital that may have changed.
    """
    from watchlist import PORTFOLIO_STATE as defaults

    state    = dict(defaults)   # start from watchlist.py defaults
    warnings = []

    # ── Layer 2: portfolio.json ───────────────────────────────────────────────
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE) as f:
                saved = json.load(f)

            # Stale-state warning (only if there is capital/positions to care about)
            last_updated = saved.get('_last_updated')
            if last_updated:
                saved_date = date.fromisoformat(last_updated)
                today      = date.today()
                has_open   = (
                    saved.get('open_positions', 0) > 0 or
                    saved.get('total_deployed',  0) > 0
                )
                if saved_date < today and has_open:
                    days_old = (today - saved_date).days
                    warnings.append(
                        f"Portfolio state is {days_old} day(s) old "
                        f"(last saved {last_updated}) — "
                        f"run with --positions / --deployed to refresh."
                    )

            # Apply saved mutable fields
            for k, v in saved.items():
                if not k.startswith('_'):
                    state[k] = v

        except (json.JSONDecodeError, OSError) as e:
            warnings.append(f"Could not read portfolio.json ({e}) — using defaults.")

    # ── Auto-detect Fed day (additive — can only set True, never suppress it) ─
    if is_fomc_today():
        state['fed_day'] = True

    # ── Layer 1: CLI overrides (highest priority) ─────────────────────────────
    if overrides:
        state.update({k: v for k, v in overrides.items() if v is not None})

    return state, warnings


def save_portfolio(state: dict) -> None:
    """
    Persist the mutable session fields to portfolio.json.
    Called only when the user explicitly provides CLI flags so that a
    plain `python3 scanner.py` (no flags) never silently overwrites state.
    """
    payload = {k: v for k, v in state.items() if k in _MUTABLE_KEYS}
    payload['_last_updated'] = date.today().isoformat()
    try:
        with open(PORTFOLIO_FILE, 'w') as f:
            json.dump(payload, f, indent=2)
    except OSError:
        pass   # non-fatal — scanner still runs with the in-memory state
