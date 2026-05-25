"""
indicators.py — Technical signal calculations
==============================================
Fetches 1H OHLCV data and computes:
  • Fair Value Gap (FVG) — most recent unfilled bullish/bearish within lookback
  • Bollinger Bands (20, 2σ) — band touch (using Low/High) + expansion check
  • Stochastic RSI (14, 3, 3) — threshold-crossing detection with recency window
  • Daily trend filter — EMA20/EMA50 alignment on the daily chart
  • Earnings calendar — auto-detects if earnings fall within 24h window

All thresholds match your pre-trade checklist logic.
"""

import yfinance as yf
import pandas as pd
import ta
from datetime import date, datetime

from models import SignalResult
from config import (
    BB_EXPAND_LOOKBACK,
    CACHE_TTL_SECONDS,
    DAILY_EMA_FAST,
    DAILY_EMA_SLOW,
    MIN_FVG_AGE_BARS,
    MIN_FVG_SIZE_PCT,
    STOCH_CROSS_LOOKBACK,
)


# ── Configuration (matches your checklist) ───────────────────────────────────

BB_WINDOW          = 20        # Bollinger Bands period
BB_STD             = 2         # Standard deviations
BB_TOUCH_BUFFER    = 0.005     # 0.5% tolerance around the band
BB_EXPAND_FACTOR   = 1.15      # BB is expanding if width > baseline × 1.15

STOCH_WINDOW       = 14
STOCH_SMOOTH1      = 3
STOCH_SMOOTH2      = 3
STOCH_OVERSOLD     = 20        # Long signal threshold
STOCH_OVERBOUGHT   = 80        # Short signal threshold
STOCH_MID_LOW      = 40        # Mid-range (skip zone) lower bound
STOCH_MID_HIGH     = 60        # Mid-range (skip zone) upper bound

FVG_LOOKBACK       = 40        # 1H bars to look back for FVGs (~2 trading days)
FVG_APPROACH_PCT   = 0.02      # Price within 2% of FVG counts as "approaching"

DATA_PERIOD        = "30d"
DATA_INTERVAL      = "1h"
FETCH_RETRIES      = 2

EARNINGS_WINDOW_H  = 24        # Skip trade if earnings within ±24 hours

# Leveraged ETFs — no earnings calendar
NO_EARNINGS_TICKERS = {"TSLL", "TSLZ"}

# Fix #5: cache now stores (DataFrame, fetched_at) tuples so it can expire
_OHLCV_CACHE: dict[str, tuple] = {}


def clear_ohlcv_cache():
    _OHLCV_CACHE.clear()


# ── Data fetcher ─────────────────────────────────────────────────────────────

def _drop_inprogress_bar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fix #1: Remove the last bar if its 1-hour candle has not yet closed.

    yfinance returns the current in-progress bar as the last row. Its Close,
    High, and Low are provisional and change every second until bar close.
    All signals derived from this bar are unreliable.
    """
    if len(df) < 2:
        return df
    last_ts = df.index[-1]
    try:
        tz  = getattr(last_ts, 'tzinfo', None)
        now = pd.Timestamp.now(tz=tz)
        if (now - last_ts) < pd.Timedelta('1h'):
            df = df.iloc[:-1]
    except Exception:
        pass  # timezone comparison failed — keep all bars
    return df


def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    """Download 1H OHLCV from Yahoo Finance, apply cache TTL, and drop the
    in-progress bar so all signals are computed on fully confirmed candles."""
    cache_key = (ticker.upper(), DATA_PERIOD, DATA_INTERVAL)
    now = datetime.now()

    # Fix #5: honour TTL — stale cache causes silently outdated signals
    if cache_key in _OHLCV_CACHE:
        df, fetched_at = _OHLCV_CACHE[cache_key]
        age_seconds = (now - fetched_at).total_seconds()
        if age_seconds < CACHE_TTL_SECONDS:
            return df.copy()

    last_error = None
    df = None
    for _ in range(FETCH_RETRIES):
        try:
            tk = yf.Ticker(ticker)
            df = tk.history(period=DATA_PERIOD, interval=DATA_INTERVAL)
            break
        except Exception as e:
            last_error = e

    if df is None:
        raise ValueError(
            f"Could not fetch 1H data for {ticker} after {FETCH_RETRIES} attempts: {last_error}"
        )

    df = df.dropna()
    # Fix #1: drop the in-progress bar before any signal computation
    df = _drop_inprogress_bar(df)

    if len(df) < BB_WINDOW + 10:
        raise ValueError(
            f"Not enough 1H data for {ticker}: got {len(df)} bars, need {BB_WINDOW + 10}."
        )

    _OHLCV_CACHE[cache_key] = (df.copy(), now)
    return df


# ── Earnings calendar ─────────────────────────────────────────────────────────

def check_earnings_soon(ticker: str, window_hours: int = EARNINGS_WINDOW_H) -> bool:
    """
    Returns True if earnings fall within ±window_hours of today.
    Silently returns False on any fetch error so a bad calendar
    response never crashes the scan session.
    """
    if ticker.upper() in NO_EARNINGS_TICKERS:
        return False

    try:
        cal   = yf.Ticker(ticker).calendar
        dates = cal.get("Earnings Date", [])

        if not dates:
            return False

        today       = date.today()
        window_days = window_hours / 24

        for d in dates:
            if hasattr(d, 'date'):
                d = d.date()
            if abs((d - today).days) <= window_days:
                return True

        return False

    except Exception:
        return False


# ── Daily trend filter ────────────────────────────────────────────────────────

def check_daily_trend(ticker: str) -> tuple[bool, bool]:
    """
    Fix #6: Compute the daily trend from EMA alignment instead of defaulting True.

    Uses EMA20/EMA50 on 60 days of daily data:
      strong downtrend = Close < EMA20 < EMA50  (bearish stack)
      strong uptrend   = Close > EMA20 > EMA50  (bullish stack)

    Returns (no_strong_downtrend, no_strong_uptrend).
    Fails safe — returns (True, True) on any error or insufficient data so
    a bad calendar or network failure never incorrectly blocks a trade.
    """
    try:
        df = yf.Ticker(ticker).history(period="60d", interval="1d").dropna()
        if len(df) < DAILY_EMA_SLOW:
            return True, True  # insufficient history — don't block
        ema_fast = df['Close'].ewm(span=DAILY_EMA_FAST, adjust=False).mean()
        ema_slow = df['Close'].ewm(span=DAILY_EMA_SLOW, adjust=False).mean()
        close    = df['Close'].iloc[-1]
        fast     = ema_fast.iloc[-1]
        slow     = ema_slow.iloc[-1]
        strong_down = close < fast < slow   # bearish EMA stack
        strong_up   = close > fast > slow   # bullish EMA stack
        return not strong_down, not strong_up
    except Exception:
        return True, True


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def calc_bollinger(df: pd.DataFrame) -> pd.DataFrame:
    """Adds BB columns. Returns modified df."""
    bb = ta.volatility.BollingerBands(
        close=df['Close'], window=BB_WINDOW, window_dev=BB_STD
    )
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_mid']   = bb.bollinger_mavg()

    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']

    # Fix #10: compare to a 20-bar baseline (was 5-bar — too noisy) and require
    # two consecutive bars above threshold to filter single-candle spikes
    bb_baseline = df['bb_width'].rolling(BB_EXPAND_LOOKBACK).mean()
    df['bb_expanding'] = (
        (df['bb_width']          > bb_baseline          * BB_EXPAND_FACTOR) &
        (df['bb_width'].shift(1) > bb_baseline.shift(1) * BB_EXPAND_FACTOR)
    )

    # Fix #4: use Low/High (candle extremes) not Close — a wick to the band
    # that closes away from it is actually the strongest bounce signal
    df['near_lower_bb'] = df['Low']  <= df['bb_lower'] * (1 + BB_TOUCH_BUFFER)
    df['near_upper_bb'] = df['High'] >= df['bb_upper'] * (1 - BB_TOUCH_BUFFER)

    return df


# ── Stochastic RSI ────────────────────────────────────────────────────────────

def calc_stoch_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """Adds Stochastic RSI columns. Returns modified df."""
    stoch = ta.momentum.StochRSIIndicator(
        close=df['Close'],
        window=STOCH_WINDOW,
        smooth1=STOCH_SMOOTH1,
        smooth2=STOCH_SMOOTH2,
    )
    df['stoch_k']      = stoch.stochrsi_k() * 100
    df['stoch_d']      = stoch.stochrsi_d() * 100
    df['stoch_k_prev'] = df['stoch_k'].shift(1)

    # Fix #2: a real cross means K *crosses through* the threshold, not just
    # "K is below 20 and ticking up." The old definition fired continuously
    # for every rising bar in oversold territory — a true cross is one bar.
    # K > D adds momentum confirmation from the signal line.
    df['stoch_oversold_cross'] = (
        (df['stoch_k_prev'] < STOCH_OVERSOLD) &   # was below 20
        (df['stoch_k'] >= STOCH_OVERSOLD) &         # now at or above 20
        (df['stoch_k'] > df['stoch_d'])             # K above D = momentum up
    )
    df['stoch_overbought_cross'] = (
        (df['stoch_k_prev'] > STOCH_OVERBOUGHT) &  # was above 80
        (df['stoch_k'] <= STOCH_OVERBOUGHT) &       # now at or below 80
        (df['stoch_k'] < df['stoch_d'])             # K below D = momentum down
    )
    df['stoch_mid_range'] = (
        (df['stoch_k'] >= STOCH_MID_LOW) &
        (df['stoch_k'] <= STOCH_MID_HIGH)
    )
    return df


# ── Fair Value Gap ────────────────────────────────────────────────────────────

def detect_fvg(df: pd.DataFrame, lookback: int = FVG_LOOKBACK) -> dict:
    """
    Detect the most recent qualifying unfilled Fair Value Gap.

    Bullish FVG: candle[i-2].high < candle[i].low
    Bearish FVG: candle[i-2].low  > candle[i].high

    Fix #8: gaps smaller than MIN_FVG_SIZE_PCT are microstructure noise and skipped.
    Fix #9: bar_age (bars since the gap formed) is attached to each FVG result.
    Fix #12: gaps younger than MIN_FVG_AGE_BARS are excluded — they have had no
             fill-check period and may not represent tested imbalance zones.
    """
    results = {'bullish': None, 'bearish': None}
    recent  = df.iloc[-lookback:]
    current_price = df['Close'].iloc[-1]

    for i in range(2, len(recent)):
        # Fix #12: require minimum age so the gap has a confirmed fill-check period
        bar_age = (len(recent) - 1) - i   # 0 = most recent bar
        if bar_age < MIN_FVG_AGE_BARS:
            continue

        h_2 = recent['High'].iloc[i - 2]
        l_2 = recent['Low'].iloc[i - 2]
        l_i = recent['Low'].iloc[i]
        h_i = recent['High'].iloc[i]

        # ── Bullish FVG ──────────────────────────────────────────────────────
        if h_2 < l_i:
            gap_bottom   = h_2
            gap_top      = l_i
            gap_size_pct = (gap_top - gap_bottom) / gap_bottom

            # Fix #8: skip noise gaps
            if gap_size_pct < MIN_FVG_SIZE_PCT:
                continue

            subsequent = recent.iloc[i + 1:]
            gap_filled = len(subsequent) > 0 and (subsequent['Low'] <= gap_bottom).any()
            if not gap_filled:
                if gap_bottom * (1 - FVG_APPROACH_PCT) <= current_price <= gap_top * (1 + FVG_APPROACH_PCT):
                    results['bullish'] = {
                        'gap_bottom':   round(float(gap_bottom), 4),
                        'gap_top':      round(float(gap_top), 4),
                        'price_inside': bool(gap_bottom <= current_price <= gap_top),
                        'gap_size_pct': round(gap_size_pct * 100, 3),
                        'bar_age':      bar_age,  # Fix #9
                    }

        # ── Bearish FVG ──────────────────────────────────────────────────────
        if l_2 > h_i:
            gap_bottom   = h_i
            gap_top      = l_2
            gap_size_pct = (gap_top - gap_bottom) / gap_bottom

            # Fix #8: skip noise gaps
            if gap_size_pct < MIN_FVG_SIZE_PCT:
                continue

            subsequent = recent.iloc[i + 1:]
            gap_filled = len(subsequent) > 0 and (subsequent['High'] >= gap_top).any()
            if not gap_filled:
                if gap_bottom * (1 - FVG_APPROACH_PCT) <= current_price <= gap_top * (1 + FVG_APPROACH_PCT):
                    results['bearish'] = {
                        'gap_bottom':   round(float(gap_bottom), 4),
                        'gap_top':      round(float(gap_top), 4),
                        'price_inside': bool(gap_bottom <= current_price <= gap_top),
                        'gap_size_pct': round(gap_size_pct * 100, 3),
                        'bar_age':      bar_age,  # Fix #9
                    }

    return results


# ── Direction inference ───────────────────────────────────────────────────────

def infer_direction(last_row: pd.Series, fvg: dict) -> str:
    """
    Determine trade direction from signal confluence.
    Long:  near lower BB + oversold Stoch cross + bullish FVG
    Short: near upper BB + overbought Stoch cross + bearish FVG
    """
    long_signals  = sum([
        bool(last_row.get('near_lower_bb')),
        bool(last_row.get('stoch_oversold_cross')),
        fvg.get('bullish') is not None,
    ])
    short_signals = sum([
        bool(last_row.get('near_upper_bb')),
        bool(last_row.get('stoch_overbought_cross')),
        fvg.get('bearish') is not None,
    ])

    if long_signals > short_signals:
        return 'long'
    if short_signals > long_signals:
        return 'short'
    return 'neutral'


# ── Main public function ──────────────────────────────────────────────────────

def fetch_and_analyze(ticker: str) -> SignalResult:
    """
    Fetch confirmed 1H data for ticker, run all indicators, return signal dict.
    This dict is fed directly into scoring.score_signals().

    Key improvements vs original:
    - Only confirmed (closed) bars are used — in-progress bar is dropped
    - Stochastic cross uses a 3-bar recency window so recent crosses aren't missed
    - Daily trend (EMA20/50) is computed automatically, not defaulted True
    """
    df           = fetch_ohlcv(ticker)   # already has in-progress bar dropped
    data_quality = {
        'valid':        True,
        'bars_returned': len(df),
        'required_bars': BB_WINDOW + 10,
        'warnings':     [],
    }
    df            = calc_bollinger(df)
    df            = calc_stoch_rsi(df)
    fvg           = detect_fvg(df)
    last          = df.iloc[-1]
    direction     = infer_direction(last, fvg)
    earnings_soon = check_earnings_soon(ticker)

    # Fix #6: compute daily trend from EMA alignment instead of defaulting True
    no_strong_down, no_strong_up = check_daily_trend(ticker)

    return {
        # Bollinger Band signals (Fix #4: Low/High used in calc_bollinger)
        'near_lower_bb':  bool(last['near_lower_bb']),
        'near_upper_bb':  bool(last['near_upper_bb']),
        'bb_expanding':   bool(last['bb_expanding']),

        # Stochastic RSI signals
        # Fix #3: use a lookback window — a cross remains valid for STOCH_CROSS_LOOKBACK bars
        # so a confirmed cross 1-2 hours ago is not silently dropped
        'stoch_oversold_cross':   bool(df['stoch_oversold_cross'].iloc[-STOCH_CROSS_LOOKBACK:].any()),
        'stoch_overbought_cross': bool(df['stoch_overbought_cross'].iloc[-STOCH_CROSS_LOOKBACK:].any()),
        'stoch_mid_range':        bool(last['stoch_mid_range']),   # current state, no window

        # Fair Value Gap
        'fvg': fvg,

        # Inferred direction
        'direction': direction,

        # Raw price data for display
        'price_data': {
            'close':    round(float(last['Close']), 4),
            'bb_lower': round(float(last['bb_lower']), 4),
            'bb_upper': round(float(last['bb_upper']), 4),
            'bb_mid':   round(float(last['bb_mid']), 4),
            'stoch_k':  round(float(last['stoch_k']), 2),
            'stoch_d':  round(float(last['stoch_d']), 2),
        },

        # Catalyst / news flags
        'earnings_soon':       earnings_soon,
        'data_quality':        data_quality,
        'fed_day':             False,
        'tesla_catalyst':      False,

        # Fix #6: computed from daily EMA alignment, not hardcoded True
        'no_strong_downtrend': no_strong_down,
        'no_strong_uptrend':   no_strong_up,
    }
