"""
Luminous Path LLC — Pre-Trade Signal Scanner
============================================
Usage:
  python3 scanner.py              # full watchlist scan
  python3 scanner.py --alerts     # only TAKE THE TRADE setups
  python3 scanner.py --ticker TSLL
  python3 scanner.py --verbose    # detail for every ticker
"""

import argparse, sys
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich import box

from watchlist import WATCHLIST, PORTFOLIO_STATE
from indicators import fetch_and_analyze
from scoring import score_signals

console = Console()


# ── Verdict helpers ───────────────────────────────────────────────────────────

VERDICT_STYLE = {
    "TAKE":   ("bold green",  "✅ TAKE TRADE"),
    "REDUCE": ("bold yellow", "⚠  REDUCE SIZE"),
    "SKIP":   ("bold red",    "✖  SKIP"),
}

DIR_STYLE = {
    "long":    ("green",  "▲ LONG"),
    "short":   ("red",    "▼ SHORT"),
    "neutral": ("white",  "── NEUTRAL"),
}

def verdict_text(verdict):
    style, label = VERDICT_STYLE.get(verdict, ("white", verdict))
    return Text(label, style=style)

def signal_cell(val: bool, label_on="", label_off=""):
    if val:
        return Text(f"✔  {label_on}" if label_on else "✔", style="green")
    return Text(f"✘  {label_off}" if label_off else "✘", style="dim red")


# ── Header ────────────────────────────────────────────────────────────────────

def print_header():
    now = datetime.now().strftime("%a %b %d, %Y  %I:%M %p")
    console.print()
    console.rule(f"[bold cyan]LUMINOUS PATH SCANNER[/bold cyan]  ·  [dim]{now}[/dim]")
    console.print()


# ── Portfolio state panel ─────────────────────────────────────────────────────

def print_portfolio(portfolio):
    deployed   = portfolio.get('total_deployed', 0)
    open_pos   = portfolio.get('open_positions', 0)
    fed        = portfolio.get('fed_day', False)
    tesla_news = portfolio.get('tesla_catalyst', False)
    pos_size   = portfolio.get('position_size', 3000)

    flags = []
    if fed:        flags.append("[bold red]⚠  FED DAY[/bold red]")
    if tesla_news: flags.append("[bold red]⚠  TESLA CATALYST[/bold red]")
    if not flags:  flags.append("[green]No active alerts[/green]")

    t = Table.grid(padding=(0, 3))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("Capital deployed",  f"[bold]${deployed:,.0f}[/bold]")
    t.add_row("Open positions",    f"[bold]{open_pos}[/bold]")
    t.add_row("Entry size",        f"[bold]${pos_size:,.0f}[/bold]")
    t.add_row("Alerts",            "  ".join(flags))

    console.print(Panel(t, title="[bold]Portfolio State[/bold]", border_style="dim", padding=(0,1)))
    console.print()


# ── Main results table ────────────────────────────────────────────────────────

def print_results_table(results):
    t = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        show_lines=False,
        pad_edge=False,
    )

    t.add_column("TICKER",    style="bold", width=10)
    t.add_column("DIR",       width=10)
    t.add_column("FVG",       width=6,  justify="center")
    t.add_column("BB",        width=6,  justify="center")
    t.add_column("STOCH",     width=8,  justify="center")
    t.add_column("SCORE",     width=8,  justify="center")
    t.add_column("CLOSE",     width=10, justify="right")
    t.add_column("VERDICT",   width=16)

    for r in results:
        pd   = r.get('price_data') or {}
        vstyle, vlabel = VERDICT_STYLE.get(r['verdict'], ("white", r['verdict']))
        dstyle, dlabel = DIR_STYLE.get(r['direction'], ("white", r['direction'].upper()))

        fvg_cell   = Text("✔", style="green") if r['has_fvg']   else Text("✘", style="dim red")
        bb_cell    = Text("✔", style="green") if r['has_bb']    else Text("✘", style="dim red")
        stoch_cell = Text("✔", style="green") if r['has_stoch'] else Text("✘", style="dim red")

        score_pct = r['score'] / r['total']
        if score_pct >= 0.75:   score_style = "green"
        elif score_pct >= 0.50: score_style = "yellow"
        else:                   score_style = "red"

        close_str = f"${pd.get('close', 0):.4f}" if pd.get('close') else "—"

        t.add_row(
            r['ticker'],
            Text(dlabel, style=dstyle),
            fvg_cell,
            bb_cell,
            stoch_cell,
            Text(f"{r['score']}/{r['total']}", style=score_style),
            close_str,
            Text(vlabel, style=vstyle),
        )

    console.print(t)


# ── Detail panel for a single ticker ─────────────────────────────────────────

def print_detail(r):
    c  = r['checks']
    pd = r.get('price_data') or {}
    vstyle, vlabel = VERDICT_STYLE.get(r['verdict'], ("white", r['verdict']))
    dstyle, dlabel = DIR_STYLE.get(r['direction'], ("white", r['direction'].upper()))
    fvg = r.get('fvg_detail', {})

    # ── Price strip ───────────────────────────────────────────────────────────
    price_row = Table.grid(padding=(0, 4))
    price_row.add_column(); price_row.add_column(); price_row.add_column(); price_row.add_column()
    price_row.add_row(
        f"[dim]Price[/dim]  [bold]${pd.get('close',0):.4f}[/bold]",
        f"[dim]BB lower[/dim]  [cyan]{pd.get('bb_lower',0):.4f}[/cyan]",
        f"[dim]BB upper[/dim]  [cyan]{pd.get('bb_upper',0):.4f}[/cyan]",
        f"[dim]Stoch K[/dim]  [bold]{pd.get('stoch_k',0):.1f}[/bold]",
    )

    # ── Signal grid ───────────────────────────────────────────────────────────
    sig = Table.grid(padding=(0, 3))
    sig.add_column(width=22); sig.add_column(width=22); sig.add_column(width=22)
    sig.add_row(
        signal_cell(r['has_fvg'],   "FVG present",   "No FVG"),
        signal_cell(r['has_bb'],    "BB confirmed",  "No BB touch"),
        signal_cell(r['has_stoch'], "Stoch cross",   "No Stoch cross"),
    )

    # ── FVG zone detail ───────────────────────────────────────────────────────
    fvg_lines = []
    if fvg.get('bullish'):
        b = fvg['bullish']
        inside = " [green][INSIDE][/green]" if b.get('price_inside') else ""
        fvg_lines.append(f"  [green]Bullish FVG[/green]  ${b['gap_bottom']} – ${b['gap_top']}  ({b['gap_size_pct']}%){inside}")
    if fvg.get('bearish'):
        b = fvg['bearish']
        inside = " [red][INSIDE][/red]" if b.get('price_inside') else ""
        fvg_lines.append(f"  [red]Bearish FVG[/red]   ${b['gap_bottom']} – ${b['gap_top']}  ({b['gap_size_pct']}%){inside}")

    # ── Checklist mini-table ──────────────────────────────────────────────────
    chk = Table.grid(padding=(0, 2))
    chk.add_column(width=28); chk.add_column(width=28)

    step2_keys = [
        ('fvg_identified',      'FVG identified'),
        ('price_near_fvg',      'Price near FVG'),
        ('bb_signal',           'BB band touch'),
        ('bb_not_expanding',    'BB not expanding'),
        ('stoch_confirmed',     'Stoch RSI cross'),
        ('stoch_not_mid_range', 'Stoch not mid-range'),
    ]
    step5_keys = [
        ('final_fvg',     'Final: FVG'),
        ('final_bb',      'Final: BB'),
        ('final_stoch',   'Final: Stoch'),
        ('final_bias',    'Final: Bias aligned'),
        ('final_no_news', 'Final: No catalyst'),
    ]
    pairs = list(zip(step2_keys, step5_keys + [('','')]))
    for (k2, l2), (k5, l5) in pairs:
        left  = Text(f"{'✔' if c.get(k2) else '✘'}  {l2}", style="green" if c.get(k2) else "dim red")
        right = Text(f"{'✔' if c.get(k5) else '✘'}  {l5}", style="green" if c.get(k5) else "dim red") if k5 else Text("")
        chk.add_row(left, right)

    # ── Assemble panel ────────────────────────────────────────────────────────
    content = Text()

    score_pct = r['score'] / r['total']
    bar_filled = round(score_pct * 20)
    bar = "[" + "█" * bar_filled + "░" * (20 - bar_filled) + f"]  {r['score']}/{r['total']}"

    console.print(Panel(
        "\n".join([
            "",
            f"  [dim]Direction[/dim]  [{dstyle}]{dlabel}[/{dstyle}]          [dim]Score[/dim]  [{('green' if score_pct>=0.75 else 'yellow' if score_pct>=0.5 else 'red')}]{bar}[/]",
            "",
            "  [bold dim]─── Core Signals ────────────────────────────────[/bold dim]",
            "",
        ]),
        title=f"[bold]{r['ticker']}[/bold]  [{vstyle}]{vlabel}[/]",
        border_style=vstyle.split()[1] if ' ' in vstyle else vstyle,
        padding=(0, 1),
    ))

    # Print sub-content outside panel for cleaner layout
    console.print(sig)
    if fvg_lines:
        for line in fvg_lines:
            console.print(line)
    console.print()
    console.print("  [dim]Step 2 — Setup          Step 5 — Final Gate[/dim]")
    console.print(chk)
    console.print()
    console.print("  [dim]Price data[/dim]")
    console.print(price_row)
    console.print()
    console.rule(style="dim")
    console.print()


# ── Summary stats ─────────────────────────────────────────────────────────────

def print_summary(results):
    takes   = sum(1 for r in results if r['verdict'] == 'TAKE')
    reduces = sum(1 for r in results if r['verdict'] == 'REDUCE')
    skips   = sum(1 for r in results if r['verdict'] == 'SKIP')

    t = Table.grid(padding=(0, 4))
    t.add_column(); t.add_column(); t.add_column(); t.add_column()
    t.add_row(
        f"[green]✅ TAKE   {takes}[/green]",
        f"[yellow]⚠  REDUCE  {reduces}[/yellow]",
        f"[dim]✖  SKIP   {skips}[/dim]",
        f"[dim]Total   {len(results)}[/dim]",
    )
    console.print(t)
    console.print()


# ── Main ──────────────────────────────────────────────────────────────────────

def run_scan(tickers=None, alerts_only=False, verbose=False):
    print_header()
    print_portfolio(PORTFOLIO_STATE)

    scan_list = tickers or [w['ticker'] for w in WATCHLIST]
    results, errors = [], []

    console.print(f"  [dim]Scanning {len(scan_list)} ticker(s) on 1H data…[/dim]\n")

    for ticker in scan_list:
        wl_entry = next((w for w in WATCHLIST if w['ticker'] == ticker), None)
        itype    = wl_entry['type'] if wl_entry else 'stock'
        try:
            signals = fetch_and_analyze(ticker)
            result  = score_signals(ticker, signals, PORTFOLIO_STATE, itype)
            result['price_data'] = signals.get('price_data')
            results.append(result)
            vstyle, vlabel = VERDICT_STYLE.get(result['verdict'], ("white", result['verdict']))
            console.print(f"  [{vstyle}]{vlabel:<18}[/{vstyle}]  [bold]{ticker}[/bold]")
        except Exception as e:
            errors.append((ticker, str(e)))
            console.print(f"  [dim]ERROR        [/dim]  {ticker}  [dim red]{e}[/dim red]")

    console.print()
    console.rule(style="dim")
    console.print()

    display = [r for r in results if r['verdict'] == 'TAKE'] if alerts_only else results

    if not display:
        console.print("  [yellow]No setups matched filters right now.[/yellow]\n")
        return

    print_results_table(display)
    console.print()
    print_summary(results)

    # Detail for TAKE + REDUCE, or all if verbose
    for r in display:
        if verbose or r['verdict'] in ('TAKE', 'REDUCE'):
            print_detail(r)

    if errors:
        console.rule("[dim]Fetch Errors[/dim]", style="dim red")
        for t, e in errors:
            console.print(f"  [dim red]{t}[/dim red]: {e}")
        console.print()


def main():
    p = argparse.ArgumentParser(description="Luminous Path Pre-Trade Scanner")
    p.add_argument('--alerts',  action='store_true', help='Only show TAKE setups')
    p.add_argument('--ticker',  type=str, help='Single ticker, e.g. --ticker TSLL')
    p.add_argument('--verbose', action='store_true', help='Detail for every ticker')
    args = p.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else None
    run_scan(tickers=tickers, alerts_only=args.alerts, verbose=args.verbose)


if __name__ == "__main__":
    main()
