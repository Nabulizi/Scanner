# Luminous Path Scanner
**Pre-trade signal scanner — FVG + Bollinger Bands + Stochastic RSI**

Built to mirror your Google Sheets pre-trade checklist exactly.
Scans your watchlist on 1H data and scores each ticker against all 25 checks.

---

## Setup (one time)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Edit your watchlist/session state
#    Open watchlist.py and update PORTFOLIO_STATE before each session
#    Trading-rule defaults live in config.py

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

    # hard risk gates
    "max_total_deployed":      60000,
    "max_open_positions":     2,
    "max_stock_position":     10000,
    "max_tsll_tslz_position": 6000,
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

# Load a TradingView-style text watchlist
python scanner.py --watchlist swing

# Explain blockers and score sections
python scanner.py --ticker TSLL --explain

# Machine-readable output
python scanner.py --watchlist swing --json

# Verbose — show detail for every ticker
python scanner.py --verbose
```

---

## How scoring works

Mirrors your checklist exactly — 25 checks across 5 steps:

| Step | Category          | Checks | Key signals |
|------|-------------------|--------|-------------|
| 1    | Market context    | 6      | No earnings, no Fed, no Tesla catalyst |
| 2    | Setup validation  | 6      | **FVG + BB touch + Stoch RSI cross** |
| 3    | Position sizing   | 4      | Max 2 open, under $60K deployed |
| 4    | Trade parameters  | 4      | Size within cap (TSLL/TSLZ $6K, stocks $10K) |
| 5    | Final go/no-go   | 5      | All 3 signals confirmed + no news |

**Verdict thresholds (exact match to your Apps Script):**
- `✅ TAKE THE TRADE` — 16+ checks
- `⚠️  REDUCE SIZE`   — 12–15 checks
- `🚫 SKIP TRADE`     — < 12 checks

Hard risk gates are evaluated before the score threshold. Earnings, Fed day,
Tesla catalyst, open-position count, total deployed, and position cap failures
force `SKIP` and are shown in the `WHY` column / `--explain` view.

`--explain` also separates core setup, risk gates, and checklist score so you can
see whether a ticker is technically clean but risk-blocked.

---

## Project structure

| File | Purpose |
|------|---------|
| `scanner.py` | CLI display, filters, and `--explain` output |
| `indicators.py` | Yahoo 1H data, FVG, Bollinger Bands, Stoch RSI, data quality |
| `scoring.py` | Checklist scoring, hard blockers, and per-check reasons |
| `config.py` | Strategy defaults, score thresholds, and risk-gate list |
| `models.py` | Typed result contracts shared between modules |
| `watchlist.py` | Tickers and current portfolio/session state |

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
```

Types: `"stock"` · `"tsll_tslz"`

You can also create optional text files under `watchlists/` and pass them with
`--watchlist`. Files can be comma- or newline-separated and may use simple
TradingView symbols:

```text
# comments are allowed
NASDAQ:AAPL, NYSE:BABA
NYSE:BRK.B
TSLA
```

Unsupported symbols are reported as skipped instead of silently ignored.

---

## Notes

- Data from Yahoo Finance (free, no API key needed)
- 1H fetches retry once, cache results during the process, and report clearer fetch errors
- 1H data limited to ~30 days on free tier — plenty for FVG detection
- Run from any directory: `python /path/to/luminous_scanner/scanner.py`
- Scanner does not place trades — it only scores setups
