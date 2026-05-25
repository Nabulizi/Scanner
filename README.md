# Luminous Path Scanner
**Pre-trade signal scanner — FVG + Bollinger Bands + Stochastic RSI**

Built to mirror your Google Sheets pre-trade checklist exactly.
Scans your watchlist on 1H data, scores each ticker against 20 signal-quality checks,
and auto-detects FOMC days so you never trade into a Fed announcement by accident.

---

## Setup (one time)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Edit your watchlist (tickers only — no need to touch PORTFOLIO_STATE)
#    Open watchlist.py, update WATCHLIST and the strategy-limit defaults
#    Trading-rule hard limits live in config.py

# 3. Run the scanner
python3 scanner.py
```

---

## Daily workflow

**Before your session, pass your real numbers via CLI flags:**

```bash
# Set open positions and deployed capital
python3 scanner.py --positions 1 --deployed 9000

# Mark today as a Fed/FOMC day (auto-detected, but you can force it)
python3 scanner.py --fed

# Mark a Tesla catalyst active (Elon news, delivery day, etc.)
python3 scanner.py --catalyst

# Combine: new position opened, $3 000 more deployed
python3 scanner.py --positions 2 --deployed 12000

# Reset after close
python3 scanner.py --positions 0 --deployed 0
```

State is saved to `portfolio.json` (gitignored) and reloaded automatically on the
next run — you only need to re-pass flags when something changes.

**Then scan normally:**

```bash
python3 scanner.py                # full watchlist scan
python3 scanner.py --alerts       # only TAKE setups
python3 scanner.py --ticker TSLL  # single ticker deep-dive
python3 scanner.py --watchlist swing
python3 scanner.py --explain      # show blockers and score breakdown
python3 scanner.py --verbose      # detail for every ticker
python3 scanner.py --json         # machine-readable scan payload
```

### Portfolio flags reference

| Flag | Type | Example | What it does |
|------|------|---------|--------------|
| `--positions` | int | `--positions 1` | Current open position count |
| `--deployed` | float | `--deployed 9000` | Total capital deployed ($) |
| `--fed` | flag | `--fed` | Force-mark today as Fed/FOMC day |
| `--catalyst` | flag | `--catalyst` | Mark Tesla catalyst active |

> **FOMC auto-detection** — The scanner checks today's date against the Fed's published
> announcement schedule. If it's an FOMC decision day, `fed_day` is forced `True`
> automatically — you never need to set it manually for scheduled meetings.

---

## How portfolio state works

State is resolved in priority order:

| Priority | Source | Contents |
|----------|--------|----------|
| 1 (highest) | CLI flags | `--positions`, `--deployed`, `--fed`, `--catalyst` |
| 2 | `portfolio.json` | Last saved session state |
| 3 (fallback) | `watchlist.py` `PORTFOLIO_STATE` | Strategy-limit defaults |

`portfolio.json` is written only when you explicitly pass CLI flags, so a plain
`python3 scanner.py` (no flags) never silently overwrites your state.

Strategy limits (`max_total_deployed`, `max_open_positions`, etc.) always come from
`watchlist.py` — they're trading rules, not session state.

If `portfolio.json` is more than one calendar day old **and** shows open positions or
deployed capital, the scanner prints a stale-state warning and prompts you to refresh.

---

## How scoring works

Mirrors your checklist — **20 scored signal-quality checks** plus 5 administrative gates.

| Step | Category         | Scored checks | Key signals |
|------|------------------|---------------|-------------|
| 1    | Market context   | 5             | No earnings, no Fed, no Tesla catalyst, no strong trend |
| 2    | Setup validation | 6             | **FVG + BB touch + Stoch RSI cross** |
| 3    | Position sizing  | 4             | Max 2 open, under $60 K deployed |
| 5    | Final go/no-go  | 5             | All 3 signals confirmed + no news |

**Administrative gates (not scored):** Daily chart checked, initial size confirmed,
max average-down defined, profit target confirmed, hard stop defined. These are
hard gates — if any is explicitly `False` the trade is blocked, but they don't
inflate the score when `True`.

**Verdict thresholds:**
- `✅ TAKE THE TRADE` — all 3 core signals present **and** score ≥ 13/20 (65 %)
- `⚠️  REDUCE SIZE`   — 2 of 3 core signals **and** score ≥ 10/20 (50 %)
- `🚫 SKIP TRADE`     — anything else

**Hard risk gates** are checked before the score. Earnings, Fed day, Tesla catalyst,
position-count limit, total-deployed limit, and position-cap failures force `SKIP`
and are shown in the `WHY` column / `--explain` view.

`--explain` separates core setup, risk gates, and checklist score so you can see
whether a ticker is technically clean but risk-blocked.

---

## Project structure

| File | Purpose |
|------|---------|
| `scanner.py` | CLI display, filters, portfolio flags, and `--explain` output |
| `portfolio.py` | Three-layer portfolio state loader, FOMC calendar, `portfolio.json` persistence |
| `indicators.py` | Yahoo 1H data, FVG, Bollinger Bands, Stoch RSI, data quality |
| `scoring.py` | Checklist scoring, hard blockers, and per-check reasons |
| `config.py` | Strategy defaults, score thresholds, and risk-gate list |
| `models.py` | Typed result contracts shared between modules |
| `watchlist.py` | Tickers and strategy-limit defaults |

`portfolio.json` — auto-created at runtime, gitignored, holds your session state.

---

## Signal logic

### Fair Value Gap (FVG)
- **Bullish**: `candle[-2].high < candle[0].low` — gap between 2-bars-ago high and current low
- **Bearish**: `candle[-2].low > candle[0].high` — gap between 2-bars-ago low and current high
- Gap must be ≥ 0.10 % of price (filters bid/ask noise) and ≥ 2 bars old
- Scans last 40 bars on 1H timeframe

### Bollinger Bands (20, 2σ)
- **Long signal**: bar `Low` ≤ BB lower band × 1.005 (within 0.5 % of lower band)
- **Short signal**: bar `High` ≥ BB upper band × 0.995
- **Expanding check**: current BB width > 20-bar rolling avg × 1.15 for 2 consecutive bars → skip

### Stochastic RSI (14, 3, 3)
- **Long**: K < 20 **and** K crosses above D (K/D crossover inside oversold zone)
- **Short**: K > 80 **and** K crosses below D (K/D crossover inside overbought zone)
- Cross is detected over the last 6 bars (≈ one full 1H session) so a cross at open isn't missed at close
- **Mid-range skip**: K between 40–60 → do not trade

### Daily trend filter
- EMA 20 / EMA 50 on daily data
- `no_strong_downtrend`: EMA20 > EMA50 (or flat) — safe to go long
- `no_strong_uptrend`: EMA20 < EMA50 (or flat) — safe to go short
- A neutral-direction signal (no dominant long or short bias) always results in SKIP

---

## Adding tickers

In `watchlist.py`, add a line to `WATCHLIST`:

```python
{"ticker": "AMZN", "type": "stock"},
```

Types: `"stock"` · `"tsll_tslz"`

You can also create optional text files under `watchlists/` and pass them with
`--watchlist`. Files can be comma- or newline-separated and may use TradingView symbols:

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
- 1H fetches cache results for 15 minutes; in-progress bars are dropped so signals aren't stale
- 1H data limited to ~30 days on free tier — plenty for FVG detection
- Run from any directory: `python3 /path/to/luminous_scanner/scanner.py`
- Scanner does not place trades — it only scores setups
