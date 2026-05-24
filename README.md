# Luminous Path Scanner
**Pre-trade signal scanner — FVG + Bollinger Bands + Stochastic RSI**

Built to mirror your Google Sheets pre-trade checklist exactly.
Scans your watchlist on 1H data and scores each ticker against all 26 checks.

---

## Setup (one time)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Edit your watchlist
#    Open watchlist.py and update PORTFOLIO_STATE before each session

# 3. Run the scanner
python scanner.py
```

---

## Daily workflow

**Before your session, open `watchlist.py` and update:**
```python
PORTFOLIO_STATE = {
    "total_deployed":  9000,   # your real number
    "open_positions":  1,      # how many positions you currently hold
    "fed_day":         False,  # True if FOMC today
    "tesla_catalyst":  False,  # True if Elon news / delivery day
    "position_size":   3000,   # your planned entry size
}
```

**Then run one of these:**

```bash
# Full watchlist scan
python scanner.py

# Show only TAKE THE TRADE setups
python scanner.py --alerts

# Single ticker deep-dive
python scanner.py --ticker TSLL

# Verbose — show detail for every ticker
python scanner.py --verbose
```

---

## How scoring works

Mirrors your checklist exactly — 26 checks across 5 steps:

| Step | Category          | Checks | Key signals |
|------|-------------------|--------|-------------|
| 1    | Market context    | 6      | No earnings, no Fed, no Tesla catalyst |
| 2    | Setup validation  | 6      | **FVG + BB touch + Stoch RSI cross** |
| 3    | Position sizing   | 4      | Max 2 open, under $60K deployed |
| 4    | Trade parameters  | 5      | Size within cap (TSLL/TSLZ $6K, crypto $6K, stocks $10K) |
| 5    | Final go/no-go   | 5      | All 3 signals confirmed + no news |

**Verdict thresholds (exact match to your Apps Script):**
- `✅ TAKE THE TRADE` — 16+ checks
- `⚠️  REDUCE SIZE`   — 12–15 checks
- `🚫 SKIP TRADE`     — < 12 checks

---

## Signal logic

### Fair Value Gap (FVG)
- **Bullish**: `candle[-2].high < candle[0].low` → gap between 2 bars ago high and current low
- **Bearish**: `candle[-2].low > candle[0].high` → gap between 2 bars ago low and current high
- Scans last 40 bars on 1H timeframe

### Bollinger Bands (20, 2σ)
- **Long signal**: Close ≤ BB lower × 1.005 (within 0.5% of lower band)
- **Short signal**: Close ≥ BB upper × 0.995
- **Expanding check**: Current BB width > 5-bar avg width × 1.15 → skip

### Stochastic RSI (14, 3, 3)
- **Long**: K < 20 AND K rising from previous bar (oversold cross UP)
- **Short**: K > 80 AND K falling from previous bar (overbought cross DOWN)
- **Mid-range skip**: K between 40–60 → do not trade

---

## Adding tickers

In `watchlist.py`, add a line to `WATCHLIST`:

```python
{"ticker": "AMZN", "type": "stock"},
{"ticker": "UNI-USD", "type": "crypto"},
```

Types: `"stock"` · `"crypto"` · `"tsll_tslz"`

---

## Notes

- Data from Yahoo Finance (free, no API key needed)
- 1H data limited to ~30 days on free tier — plenty for FVG detection
- Run from any directory: `python /path/to/luminous_scanner/scanner.py`
- Scanner does not place trades — it only scores setups
