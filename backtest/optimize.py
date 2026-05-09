"""Grid search: for BTC+ETH over the last N days, evaluate every (timeframe, strategy)
combination and report comparison metrics. No DB writes."""

from __future__ import annotations
import sys
from collections import defaultdict
from pathlib import Path

import click
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from ict.data import fetch_klines
from engine import run_engine
from backtester import simulate_signals, TradeStatus


def _empty():
    return {"n": 0, "tp": 0, "sl": 0, "cancel": 0, "active": 0, "total_r": 0.0}


def aggregate_by_strategy(trades) -> dict:
    out = defaultdict(_empty)
    for tr in trades:
        s = tr.signal.strategy
        out[s]["n"] += 1
        if tr.status == TradeStatus.TP_HIT:
            out[s]["tp"] += 1
            out[s]["total_r"] += tr.pnl_r or 0
        elif tr.status == TradeStatus.SL_HIT:
            out[s]["sl"] += 1
            out[s]["total_r"] += tr.pnl_r or 0
        elif tr.status == TradeStatus.ACTIVE:
            out[s]["active"] += 1
        else:
            out[s]["cancel"] += 1
    return out


def merge(*dicts):
    combined: dict = defaultdict(_empty)
    for d in dicts:
        for k, v in d.items():
            for kk, vv in v.items():
                combined[k][kk] += vv
    return combined


def fmt_row(strategy: str, m: dict, tf: str) -> str:
    closed = m["tp"] + m["sl"]
    wr = (m["tp"] / closed * 100) if closed else 0.0
    exp_r = (m["total_r"] / closed) if closed else 0.0
    fill_rate = (closed / m["n"] * 100) if m["n"] else 0.0
    return (f"  {tf:>4} {strategy:<32} n={m['n']:>4} "
            f"closed={closed:>3} TP={m['tp']:>3} SL={m['sl']:>3} "
            f"win={wr:>5.1f}% fill={fill_rate:>4.1f}% "
            f"totalR={m['total_r']:>+8.2f} expR={exp_r:>+6.2f}")


@click.command()
@click.option("--days", default=60, type=int)
@click.option("--symbols", default="BTCUSDT,ETHUSDT")
@click.option("--timeframes", default="5m,15m,1h")
def main(days: int, symbols: str, timeframes: str):
    syms = [s.strip() for s in symbols.split(",")]
    tfs = [t.strip() for t in timeframes.split(",")]
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=days)
    click.echo(f"period: {start.date()} -> {end.date()}  ({days} days)\n")

    grid: dict[str, dict] = {}  # tf -> aggregate dict

    for tf in tfs:
        per_symbol = []
        click.echo(f"--- {tf} ---")
        for sym in syms:
            df = fetch_klines(sym, tf,
                              int(start.timestamp() * 1000),
                              int(end.timestamp() * 1000))
            if df.empty:
                click.echo(f"  {sym}: no data")
                continue
            sigs = run_engine(sym, df)
            trades = simulate_signals(sigs, df)
            agg = aggregate_by_strategy(trades)
            per_symbol.append(agg)
            click.echo(f"  {sym}: {len(df)} bars, {len(sigs)} signals, "
                       f"{sum(t.status == TradeStatus.TP_HIT for t in trades)} TP, "
                       f"{sum(t.status == TradeStatus.SL_HIT for t in trades)} SL")
        grid[tf] = merge(*per_symbol) if per_symbol else {}

    click.echo("\n" + "=" * 110)
    click.echo("BTC+ETH combined per (timeframe, strategy):")
    click.echo("=" * 110)

    rows = []
    for tf, agg in grid.items():
        for strat, m in agg.items():
            rows.append((tf, strat, m))
        # also print "ALL" aggregate per TF
        all_m = _empty()
        for m in agg.values():
            for k in all_m:
                all_m[k] += m[k]
        rows.append((tf, "ALL_combined", all_m))

    # sort by total_r desc, then closed-trades count for sample-size sanity
    rows.sort(key=lambda r: (r[2]["total_r"], r[2]["tp"] + r[2]["sl"]), reverse=True)
    click.echo("\nRanked by total R (BTC+ETH combined):\n")
    for tf, strat, m in rows:
        click.echo(fmt_row(strat, m, tf))

    click.echo("\n" + "=" * 110)
    click.echo("Top 5 highest-expectancy single-strategy cells (min 5 closed):")
    click.echo("=" * 110)
    sized = [r for r in rows if r[1] != "ALL_combined" and (r[2]["tp"] + r[2]["sl"]) >= 5]
    sized.sort(key=lambda r: (r[2]["total_r"] / max(r[2]["tp"] + r[2]["sl"], 1)), reverse=True)
    for tf, strat, m in sized[:5]:
        click.echo(fmt_row(strat, m, tf))


if __name__ == "__main__":
    main()
