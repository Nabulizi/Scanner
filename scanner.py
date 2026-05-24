"""
Luminous Path LLC — Pre-Trade Signal Scanner
============================================
Usage:
  python3 scanner.py              # full watchlist scan
  python3 scanner.py --alerts     # only TAKE THE TRADE setups
  python3 scanner.py --ticker TSLL
  python3 scanner.py --watchlist swing
  python3 scanner.py --explain    # show blockers and score breakdown
  python3 scanner.py --json       # machine-readable scan payload
  python3 scanner.py --verbose    # detail for every ticker
"""

import argparse, json, os, sys
from datetime import datetime
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn
from rich import box

from watchlist import WATCHLIST, PORTFOLIO_STATE, load_watchlist_file, resolve_watchlist_path, DEFAULT_WATCHLIST_FILE
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

def reason_summary(r):
    reasons = r.get('blocker_reasons') or []
    if not reasons:
        return "—"
    first = reasons[0]
    return (
        first
        .replace("Total deployed at or above", "Deployed >=")
        .replace("Position size exceeds", "Size >")
        .replace("FVG missing or direction-mismatched", "No matching FVG")
        .replace("Bollinger confirmation missing or expanding", "No BB confirmation")
        .replace("Stoch RSI confirmation missing or mid-range", "No Stoch confirmation")
    )


# ── Header ────────────────────────────────────────────────────────────────────

def print_header():
    now = datetime.now().strftime("%a %b %d, %Y  %I:%M %p")
    console.print()
    console.rule(f"[bold cyan]LUMINOUS PATH SCANNER[/bold cyan]  ·  [dim]{now}[/dim]")
    console.print()


# ── Portfolio state panel ─────────────────────────────────────────────────────

def print_portfolio(portfolio):
    deployed      = portfolio.get('total_deployed', 0)
    open_pos      = portfolio.get('open_positions', 0)
    fed           = portfolio.get('fed_day', False)
    tesla_news    = portfolio.get('tesla_catalyst', False)
    pos_size      = portfolio.get('position_size', 3000)
    max_deployed  = portfolio.get('max_total_deployed', 60_000)
    max_positions = portfolio.get('max_open_positions', 2)

    flags = []
    if fed:        flags.append("[bold red]⚠  FED DAY[/bold red]")
    if tesla_news: flags.append("[bold red]⚠  TESLA CATALYST[/bold red]")
    if not flags:  flags.append("[green]No active alerts[/green]")

    t = Table.grid(padding=(0, 3))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("Capital deployed", f"[bold]${deployed:,.0f}[/bold]")
    t.add_row("Open positions",   f"[bold]{open_pos}[/bold]")
    t.add_row("Entry size",       f"[bold]${pos_size:,.0f}[/bold]")
    t.add_row("Risk limits",      f"[bold]${max_deployed:,.0f}[/bold] deployed · [bold]{max_positions}[/bold] positions")
    t.add_row("Alerts",           "  ".join(flags))

    console.print(Panel(t, title="[bold]Portfolio State[/bold]", border_style="dim", padding=(0, 1)))
    console.print()


# ── Main results table ────────────────────────────────────────────────────────

def print_results_table(results):
    t = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        show_lines=False,
        pad_edge=False,
        expand=True,
    )

    t.add_column("TICKER",  style="bold", width=8,  no_wrap=True)
    t.add_column("DIR",     width=10, no_wrap=True)
    t.add_column("FVG",     width=5,  justify="center", no_wrap=True)
    t.add_column("BB",      width=5,  justify="center", no_wrap=True)
    t.add_column("STOCH",   width=7,  justify="center", no_wrap=True)
    t.add_column("SCORE",   width=7,  justify="center", no_wrap=True)
    t.add_column("CLOSE",   width=10, justify="right",  no_wrap=True)
    t.add_column("VERDICT", width=16, no_wrap=True)
    # Fix 5: ellipsis keeps WHY to one clean line instead of wrapping mid-word
    t.add_column("WHY",     min_width=20, ratio=1, overflow="ellipsis", no_wrap=True)

    for r in results:
        pd     = r.get('price_data') or {}
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
            reason_summary(r),
        )

    console.print(t)


# ── Detail panel for a single ticker ─────────────────────────────────────────

def print_detail(r, show_all_checks=False):
    c        = r['checks']
    pd       = r.get('price_data') or {}
    vstyle, vlabel = VERDICT_STYLE.get(r['verdict'], ("white", r['verdict']))
    dstyle, dlabel = DIR_STYLE.get(r['direction'], ("white", r['direction'].upper()))
    fvg      = r.get('fvg_detail', {})
    sections = r.get('score_sections') or {}

    score_pct   = r['score'] / r['total']
    bar_filled  = round(score_pct * 20)
    score_color = 'green' if score_pct >= 0.75 else 'yellow' if score_pct >= 0.5 else 'red'

    # Fix 2: one labeled row per field instead of cramming onto two lines
    meta = Table.grid(padding=(0, 3))
    meta.add_column(style="dim", width=12)
    meta.add_column()

    score_text = Text()
    score_text.append(
        "[" + "█" * bar_filled + "░" * (20 - bar_filled) + f"]  {r['score']}/{r['total']}",
        style=score_color,
    )

    meta.add_row("Direction", Text(dlabel, style=dstyle))
    meta.add_row("Score",     score_text)
    meta.add_row(
        "Sections",
        f"Core [bold]{sections.get('core_setup', '—')}[/bold]   "
        f"Risk [bold]{sections.get('risk_gates', '—')}[/bold]   "
        f"Checklist [bold]{sections.get('checklist', '—')}[/bold]",
    )

    # Core signals row
    sig = Table.grid(padding=(0, 3))
    sig.add_column(width=22); sig.add_column(width=22); sig.add_column(width=22)
    sig.add_row(
        signal_cell(r['has_fvg'],   "FVG present",  "No FVG"),
        signal_cell(r['has_bb'],    "BB confirmed", "No BB touch"),
        signal_cell(r['has_stoch'], "Stoch cross",  "No Stoch cross"),
    )

    # FVG zone detail
    fvg_renderables = []
    for kind in ('bullish', 'bearish'):
        z = fvg.get(kind)
        if z:
            color = "green" if kind == 'bullish' else "red"
            label = "Bullish FVG" if kind == 'bullish' else "Bearish FVG"
            line = Text()
            line.append(f"  {label}  ", style=color)
            line.append(f"${z['gap_bottom']} – ${z['gap_top']}  ({z['gap_size_pct']}%)")
            if z.get('price_inside'):
                line.append("  INSIDE", style=f"{color} bold")
            fvg_renderables.append(line)

    # Blocker reasons
    blocker_renderables = []
    if r.get('blocker_reasons'):
        blocker_renderables.append(Text("  Why", style="dim"))
        for reason in r['blocker_reasons']:
            line = Text()
            line.append("  • ", style="red")
            line.append(reason)
            blocker_renderables.append(line)

    # Failed checks
    failed_checks = [item for item in r.get('check_reasons', []) if not item.get('passed')]
    check_renderables = []
    if failed_checks:
        check_renderables.append(Text("  Failed checks", style="dim"))
        visible = failed_checks if show_all_checks else failed_checks[:6]
        for item in visible:
            line = Text()
            line.append("  • ", style="red")
            line.append(item['label'])
            check_renderables.append(line)
        hidden = len(failed_checks) - len(visible)
        if hidden:
            check_renderables.append(Text(f"  + {hidden} more  (run --explain to show all)", style="dim"))

    # Fix 3: proper Table with column headers so they actually align with the data
    chk = Table(box=None, show_header=True, header_style="dim", pad_edge=False, show_lines=False)
    chk.add_column("Step 2 — Setup",      width=28)
    chk.add_column("Step 5 — Final Gate", width=28)

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
    for (k2, l2), (k5, l5) in zip(step2_keys, step5_keys + [('', '')]):
        left  = Text(f"{'✔' if c.get(k2) else '✘'}  {l2}", style="green" if c.get(k2) else "dim red")
        right = Text(f"{'✔' if c.get(k5) else '✘'}  {l5}", style="green" if c.get(k5) else "dim red") if k5 else Text("")
        chk.add_row(left, right)

    # Price data strip
    price_row = Table.grid(padding=(0, 4))
    price_row.add_column(); price_row.add_column(); price_row.add_column(); price_row.add_column()
    price_row.add_row(
        f"[dim]Price[/dim]  [bold]${pd.get('close', 0):.4f}[/bold]",
        f"[dim]BB lower[/dim]  [cyan]{pd.get('bb_lower', 0):.4f}[/cyan]",
        f"[dim]BB upper[/dim]  [cyan]{pd.get('bb_upper', 0):.4f}[/cyan]",
        f"[dim]Stoch K[/dim]  [bold]{pd.get('stoch_k', 0):.1f}[/bold]",
    )

    # Fix 1: everything inside one Panel via Group — no more floating content below the box
    body = [
        Text(""),
        meta,
        Text(""),
        Text("  Core Signals", style="bold dim"),
        Text(""),
        sig,
        *fvg_renderables,
        *([Text("")] if blocker_renderables else []),
        *blocker_renderables,
        *([Text("")] if check_renderables else []),
        *check_renderables,
        Text(""),
        Text("  Checklist", style="bold dim"),
        chk,
        Text(""),
        Text("  Price Data", style="dim"),
        price_row,
        Text(""),
    ]

    border_color = vstyle.split()[1] if ' ' in vstyle else vstyle
    console.print(Panel(
        Group(*body),
        title=f"[bold]{r['ticker']}[/bold]  [{vstyle}]{vlabel}[/]",
        border_style=border_color,
        padding=(0, 1),
    ))
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

def build_scan_entries(tickers=None, watchlist_entries=None, file_skipped=None):
    file_skipped = file_skipped or []
    if tickers:
        base = watchlist_entries if watchlist_entries is not None else WATCHLIST
        scan_entries = [w for w in base if w['ticker'] in tickers] or \
                       [{'ticker': t, 'type': 'stock'} for t in tickers]
    else:
        scan_entries = list(watchlist_entries if watchlist_entries is not None else WATCHLIST)

    all_tickers_in_scan = {e['ticker'] for e in scan_entries}
    skipped = list(file_skipped)
    filtered_entries = []
    for entry in scan_entries:
        parent = entry.get('parent')
        if parent and parent in all_tickers_in_scan:
            skipped.append({
                'symbol': entry['ticker'],
                'reason': f"Skipped because parent {parent} is in watchlist",
            })
        else:
            filtered_entries.append(entry)
    return filtered_entries, skipped


def load_requested_watchlist(watchlist_name=None):
    name = watchlist_name or DEFAULT_WATCHLIST_FILE
    path = resolve_watchlist_path(name)
    if os.path.exists(path):
        return load_watchlist_file(path)
    if watchlist_name:
        raise FileNotFoundError(f"Watchlist file not found: {path}")
    # Default file missing — fall back to hardcoded list
    return list(WATCHLIST), []


def run_scan(tickers=None, alerts_only=False, verbose=False, explain=False, watchlist_name=None, output_json=False):
    watchlist_entries, file_skipped = load_requested_watchlist(watchlist_name)
    filtered_entries, skipped = build_scan_entries(
        tickers=tickers,
        watchlist_entries=watchlist_entries,
        file_skipped=file_skipped,
    )

    if not output_json:
        print_header()
        print_portfolio(PORTFOLIO_STATE)

    if skipped:
        for item in skipped:
            if not output_json:
                console.print(f"  [dim]SKIPPED  {item['symbol']:<10} ({item['reason']})[/dim]")
        if not output_json:
            console.print()

    results, errors = [], []

    if output_json:
        # JSON mode: no UI, plain loop
        for entry in filtered_entries:
            ticker = entry['ticker']
            itype  = entry.get('type', 'stock')
            try:
                signals = fetch_and_analyze(ticker)
                result  = score_signals(ticker, signals, PORTFOLIO_STATE, itype)
                result['price_data'] = signals.get('price_data')
                results.append(result)
            except Exception as e:
                errors.append((ticker, str(e)))
    else:
        # Fix 6: Progress bar clears itself (transient=True) before results print
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                f"[dim]Scanning {len(filtered_entries)} ticker(s) on 1H data…[/dim]",
                total=len(filtered_entries),
            )
            for entry in filtered_entries:
                ticker = entry['ticker']
                itype  = entry.get('type', 'stock')
                progress.update(task, description=f"[dim]Fetching[/dim] [bold]{ticker}[/bold]")
                try:
                    signals = fetch_and_analyze(ticker)
                    result  = score_signals(ticker, signals, PORTFOLIO_STATE, itype)
                    result['price_data'] = signals.get('price_data')
                    results.append(result)
                except Exception as e:
                    errors.append((ticker, str(e)))
                progress.advance(task)

    payload = {
        'results': results,
        'errors': [{'ticker': t, 'error': e} for t, e in errors],
        'skipped': skipped,
    }

    if output_json:
        print(json.dumps(payload, indent=2))
        return payload

    console.print()
    console.rule(style="dim")
    console.print()

    display = [r for r in results if r['verdict'] == 'TAKE'] if alerts_only else results

    if not display:
        console.print("  [yellow]No setups matched filters right now.[/yellow]\n")
        return payload

    print_results_table(display)
    console.print()
    print_summary(results)

    # Fix 4: detail panels grouped by verdict with labeled section dividers
    verdict_groups = [
        ('TAKE',   '✅ TAKE TRADES',  'green'),
        ('REDUCE', '⚠  REDUCE SIZE', 'yellow'),
        ('SKIP',   '✖  SKIPPED',     'dim'),
    ]
    for verdict, label, color in verdict_groups:
        group = [r for r in display if r['verdict'] == verdict]
        if not group:
            continue
        show_detail = verbose or explain or verdict in ('TAKE', 'REDUCE')
        if not show_detail:
            continue
        console.rule(f"[{color}]{label}  ({len(group)})[/]", style=color)
        console.print()
        for r in group:
            print_detail(r, show_all_checks=verbose or explain)

    if errors:
        console.rule("[dim]Fetch Errors[/dim]", style="dim red")
        for t, e in errors:
            console.print(f"  [dim red]{t}[/dim red]: {e}")
        console.print()

    return payload


def main():
    p = argparse.ArgumentParser(description="Luminous Path Pre-Trade Scanner")
    p.add_argument('--alerts',    action='store_true', help='Only show TAKE setups')
    p.add_argument('--ticker',    type=str, help='Single ticker, e.g. --ticker TSLL')
    p.add_argument('--watchlist', type=str, help='Watchlist file path or name under watchlists/')
    p.add_argument('--explain',   action='store_true', help='Show blockers and score breakdown')
    p.add_argument('--json',      action='store_true', help='Print machine-readable JSON')
    p.add_argument('--verbose',   action='store_true', help='Detail for every ticker')
    args = p.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else None
    run_scan(
        tickers=tickers,
        alerts_only=args.alerts,
        verbose=args.verbose,
        explain=args.explain,
        watchlist_name=args.watchlist,
        output_json=args.json,
    )


if __name__ == "__main__":
    main()
