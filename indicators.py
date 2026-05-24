"""
indicators.py — Technical signal calculations
==============================================
Fetches 1H OHLCV data and computes:
  • Fair Value Gap (FVG) — most recent bullish and bearish within lookback
  • Bollinger Bands (20, 2σ) — band touch + expansion check
  • Stochastic RSI (14, 3, 3) — oversold/overbought cross detection
  • Earnings calendar — auto-detects if earnings fall within 24h window

All thresholds match your pre-trade checklist logic.
"""

import yfinance as yf
import pandas as pd
import ta
from datetime import date


# ── Configuration (matches your checklist) ───────────────────────────────────

BB_WINDOW          = 20        # Bollinger Bands period
BB_STD             = 2         # Standard deviations
BB_TOUCH_BUFFER    = 0.005     # 0.5% — how close price must be to the band
BB_EXPAND_FACTOR   = 1.15      # BB expanding if width > 5-bar avg × 1.15

STOCH_WINDOW       = 14
STOCH_SMOOTH1      = 3
STOCH_SMOOTH2      = 3
STOCH_OVERSOLD     = 20        # Long signal threshold
STOCH_OVERBOUGHT   = 80        # Short signal threshold
STOCH_MID_LOW      = 40        # Mid-range (skip zone) lower bound
STOCH_MID_HIGH     = 60        # Mid-range (skip zone) upper bound

FVG_LOOKBACK       = 40        # How many 1H bars to look back for FVGs
FVG_APPROACH_PCT   = 0.02      # Price within 2% of FVG counts as "approaching"

DATA_PERIOD        = "30d"     # 30 days of 1H data (~240 bars on trading days)
DATA_INTERVAL      = "1h"

EARNINGS_WINDOW_H  = 24        # Skip trade if earnings within ±24 hours

# Tickers that never have earnings reports — always return False
NO_EARNINGS_TICKERS = {
    "TSLL", "TSLZ",                            # leveraged ETFs
    "BTC-USD", "ETH-USD", "DOGE-USD",          # direct crypto
    "IBIT", "BITI",                            # bitcoin ETFs
    "UNI-USD", "LINK-USD", "ETC-USD",          # DeFi / alt crypto
}


# ── Data fetcher ─────────────────────────────────────────────────────────────

def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    """Download 1H OHLCV from Yahoo Finance and clean it."""
    tk = yf.Ticker(ticker)
    df = tk.history(period=DATA_PERIOD, interval=DATA_INTERVAL)
    df = df.dropna()

    if len(df) < BB_WINDOW + 10:
        raise ValueError(f"Not enough data for {ticker} — only {len(df)} bars returned.")

    return df


# ── Earnings calendar ─────────────────────────────────────────────────────────

def check_earnings_soon(ticker: str, window_hours: int = EARNINGS_WINDOW_H) -> bool:
    """
    Returns True if earnings fall within ±window_hours of today.

    Silently returns False on any fetch error so a bad calendar
    response never crashes your whole scan session.

    Crypto and leveraged ETFs are skipped immediately — they have
    no earnings and the Yahoo Finance call would just waste time.
    """
    if ticker.upper() in NO_EARNINGS_TICKERS:
        return False

    try:
        cal   = yf.Ticker(ticker).calendar          # dict or empty dict
        dates = cal.get("Earnings Date", [])

        if not dates:
            return False

        today       = date.today()
        window_days = window_hours / 24

        for d in dates:
            # yfinance returns date objects; guard against datetime objects too
            if hasattr(d, 'date'):
                d = d.date()
            if abs((d - today).days) <= window_days:
                return True

        return False

    except Exception:
        # Network error, parsing error, etc. — fail safe: don't block the trade
        return False




def calc_bollinger(df: pd.DataFrame) -> pd.DataFrame:
    """Adds BB columns. Returns modified df."""
    bb = ta.volatility.BollingerBands(
        close=df['Close'], window=BB_WINDOW, window_dev=BB_STD
    )
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_mid']   = bb.bollinger_mavg()

    # Bandwidth as fraction of mid — normalised so we can compare across price levels
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']

    # Expanding if current width > recent 5-bar average × expand factor
    df['bb_expanding'] = df['bb_width'] > df['bb_width'].rolling(5).mean() * BB_EXPAND_FACTOR

    # Touch signals
    df['near_lower_bb'] = df['Close'] <= df['bb_lower'] * (1 + BB_TOUCH_BUFFER)
    df['near_upper_bb'] = df['Close'] >= df['bb_upper'] * (1 - BB_TOUCH_BUFFER)

    return df


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

    # Oversold cross UP: K < 20 AND rising from previous bar
    df['stoch_oversold_cross'] = (
        (df['stoch_k'] < STOCH_OVERSOLD) &
        (df['stoch_k'] > df['stoch_k_prev'])
    )
    # Overbought cross DOWN: K > 80 AND falling
    df['stoch_overbought_cross'] = (
        (df['stoch_k'] > STOCH_OVERBOUGHT) &
        (df['stoch_k'] < df['stoch_k_prev'])
    )
    # Mid-range — do NOT trade (your checklist Step 2 rule)
    df['stoch_mid_range'] = (
        (df['stoch_k'] >= STOCH_MID_LOW) &
        (df['stoch_k'] <= STOCH_MID_HIGH)
    )
    return df


def detect_fvg(df: pd.DataFrame, lookback: int = FVG_LOOKBACK) -> dict:
    """
    Detect the most recent unfilled Fair Value Gap.

    Bullish FVG: candle[i-2].high < candle[i].low
                 → gap between high 2 bars ago and current low
                 → price reverting INTO gap from below = long setup

    Bearish FVG: candle[i-2].low > candle[i].high
                 → gap between low 2 bars ago and current high
                 → price reverting INTO gap from above = short setup
    """
    results = {'bullish': None, 'bearish': None}
    recent  = df.iloc[-lookback:]
    current_price = df['Close'].iloc[-1]

    for i in range(2, len(recent)):
        h_2 = recent['High'].iloc[i - 2]
        l_2 = recent['Low'].iloc[i - 2]
        l_i = recent['Low'].iloc[i]
        h_i = recent['High'].iloc[i]

        # ── Bullish FVG ──────────────────────────────────────────────────────
        if h_2 < l_i:
            gap_bottom = h_2
            gap_top    = l_i
            # Current price is within approach range of the gap (above floor, below ceiling)
            if gap_bottom * (1 - FVG_APPROACH_PCT) <= current_price <= gap_top * (1 + FVG_APPROACH_PCT):
                results['bullish'] = {
                    'gap_bottom':   round(float(gap_bottom), 4),
                    'gap_top':      round(float(gap_top), 4),
                    'price_inside': bool(gap_bottom <= current_price <= gap_top),
                    'gap_size_pct': round((gap_top - gap_bottom) / gap_bottom * 100, 3),
                }

        # ── Bearish FVG ──────────────────────────────────────────────────────
        if l_2 > h_i:
            gap_bottom = h_i
            gap_top    = l_2
            # Current price is within approach range of the gap (above floor, below ceiling)
            if gap_bottom * (1 - FVG_APPROACH_PCT) <= current_price <= gap_top * (1 + FVG_APPROACH_PCT):
                results['bearish'] = {
                    'gap_bottom':   round(float(gap_bottom), 4),
                    'gap_top':      round(float(gap_top), 4),
                    'price_inside': bool(gap_bottom <= current_price <= gap_top),
                    'gap_size_pct': round((gap_top - gap_bottom) / gap_bottom * 100, 3),
                }

    return results


# ── Direction inference ───────────────────────────────────────────────────────

def infer_direction(last_row: pd.Series, fvg: dict) -> str:
    """
    Determine trade direction from signal confluence.
    Long:  near lower BB + oversold Stoch + bullish FVG
    Short: near upper BB + overbought Stoch + bearish FVG
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

def fetch_and_analyze(ticker: str) -> dict:
    """
    Fetch 1H data for ticker, run all indicators, return signal dict.
    This dict is fed directly into scoring.score_signals().

    Earnings check runs in parallel with price fetch — if Yahoo Finance
    has no calendar data the field silently defaults to False.
    """
    df            = fetch_ohlcv(ticker)
    df            = calc_bollinger(df)
    df            = calc_stoch_rsi(df)
    fvg           = detect_fvg(df)
    last          = df.iloc[-1]
    direction     = infer_direction(last, fvg)
    earnings_soon = check_earnings_soon(ticker)   # ← live calendar lookup

    return {
        # Bollinger Band signals
        'near_lower_bb':          bool(last['near_lower_bb']),
        'near_upper_bb':          bool(last['near_upper_bb']),
        'bb_expanding':           bool(last['bb_expanding']),

        # Stochastic RSI signals
        'stoch_oversold_cross':   bool(last['stoch_oversold_cross']),
        'stoch_overbought_cross': bool(last['stoch_overbought_cross']),
        'stoch_mid_range':        bool(last['stoch_mid_range']),

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

        # News/catalyst flags
        # earnings_soon: auto-detected from Yahoo Finance calendar
        # fed_day / tesla_catalyst: set manually in watchlist.py PORTFOLIO_STATE
        'earnings_soon':       earnings_soon,
        'fed_day':             False,
        'tesla_catalyst':      False,
        # These are session-level manual confirmations — passed in via PORTFOLIO_STATE
        # and forwarded here so scoring.py can read them from signals.
        # They default True to preserve backwards compatibility but should be set
        # in watchlist.py PORTFOLIO_STATE before each session.
        'no_strong_downtrend': True,
        'no_strong_uptrend':   True,
        'daily_checked':       True,
    }
