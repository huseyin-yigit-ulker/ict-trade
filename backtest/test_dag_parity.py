"""DAG-vs-backtest parity test.

The DAG and live_runner only fetch the last WARMUP_HOURS of data, then run
the engine on the last bar. This tests whether that limited-window run
produces the same signal as a long-history backtest at the same bar T.

If signals match across many sample bars, the DAG is bit-perfect with the
backtest engine — meaning what you saw in the backtest is what the DAG
will emit in production."""

from __future__ import annotations
import sys
import random
from pathlib import Path

import click
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from ict.data import fetch_klines
from engine import run_engine


WARMUP_HOURS = 6000   # must match dag/dag.py and live_runner.py (~250 days)


def signal_key(s) -> tuple:
    return (
        str(s.timestamp),
        s.strategy,
        s.direction,
        round(s.entry, 6),
        round(s.stop_loss, 6),
        round(s.take_profit_1, 6) if s.take_profit_1 is not None else None,
    )


@click.command()
@click.option("--symbol", default="BTCUSDT")
@click.option("--days", default=180, type=int)
@click.option("--interval", default="1h")
@click.option("--samples", default=30, type=int)
@click.option("--seed", default=42, type=int)
def main(symbol, days, interval, samples, seed):
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=days)
    click.echo(f"fetching {symbol} {interval} for {days} days...")
    df = fetch_klines(symbol, interval,
                      int(start.timestamp() * 1000),
                      int(end.timestamp() * 1000))
    if df.empty:
        click.echo("no data"); return
    click.echo(f"  {len(df)} bars")

    click.echo("\nrunning FULL-history backtest...")
    full_signals = run_engine(symbol, df)
    by_bar: dict[int, set[tuple]] = {}
    for s in full_signals:
        by_bar.setdefault(s.bar_index, set()).add(signal_key(s))

    if not by_bar:
        click.echo("no signals"); return
    click.echo(f"  {len(full_signals)} total, on {len(by_bar)} unique bars")

    # Only sample bars where we have enough warmup behind them.
    eligible = [b for b in by_bar.keys() if b >= WARMUP_HOURS]
    if not eligible:
        click.echo(f"no signals at bars >= {WARMUP_HOURS}, increase --days"); return

    rng = random.Random(seed)
    sample_bars = rng.sample(eligible, min(samples, len(eligible)))
    sample_bars.sort()
    click.echo(f"\nre-running engine on {len(sample_bars)} DAG-style windows "
               f"(last {WARMUP_HOURS} bars only)...")

    mismatches = []
    for i, bar_idx in enumerate(sample_bars):
        # Mimic exactly what the DAG sees at bar `bar_idx`:
        # fetch_klines returns bars from (now - 720h) to now,
        # so the slice is [bar_idx - 720 + 1 : bar_idx + 1] = 720 bars total.
        slice_start = bar_idx - WARMUP_HOURS + 1
        df_window = df.iloc[slice_start:bar_idx + 1].copy()
        window_signals = run_engine(symbol, df_window,
                                    start_index=len(df_window) - 1,
                                    end_index=len(df_window) - 1)

        # `bar_index` inside window_signals is local to df_window, so re-key
        # by our absolute bar_idx for comparison.
        wkeys = {signal_key(s) for s in window_signals}
        full_set = by_bar.get(bar_idx, set())

        match = full_set == wkeys
        marker = "OK" if match else "MISMATCH"
        click.echo(f"  [{i+1:>3}/{len(sample_bars)}] bar {bar_idx:>5} "
                   f"full={len(full_set)} window={len(wkeys)} -> {marker}")
        if not match:
            mismatches.append({
                "bar": bar_idx,
                "only_in_full": full_set - wkeys,
                "only_in_window": wkeys - full_set,
            })

    click.echo("\n" + "=" * 60)
    if not mismatches:
        click.echo(f"PASS — all {len(sample_bars)} sample bars match.")
        click.echo(f"DAG with {WARMUP_HOURS}h warmup produces signals identical")
        click.echo(f"to a {days}-day backtest.")
    else:
        click.echo(f"FAIL — {len(mismatches)}/{len(sample_bars)} mismatches:")
        for m in mismatches[:5]:
            click.echo(f"\n  bar {m['bar']}:")
            for s in m["only_in_full"]:
                click.echo(f"    only in FULL  : {s}")
            for s in m["only_in_window"]:
                click.echo(f"    only in WINDOW: {s}")


if __name__ == "__main__":
    main()
