"""Look-ahead bias validation.

If the engine has no look-ahead, then for any bar i:
  signals_at(i) when given full data == signals_at(i) when given data[0..i+1]

This test runs the engine twice — once with the full DataFrame, once with
incrementally truncated DataFrames — and asserts the resulting signal sets
at each bar are identical.

To keep runtime sane we only re-run the truncated engine on a sample of bars
that produced a signal in the full run."""

from __future__ import annotations
import sys
import random
from pathlib import Path

import click
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from ict.data import fetch_klines, fetch_funding
from ict.strategies import strategy_f, strategy_g, set_funding
from engine import run_engine

# Named strategy sets: None = engine default (A-E per STRATEGIES); radar = F-only (v3);
# squeeze = G-only (v4, needs funding registration — handled inside main()).
_SETS = {"default": None, "radar": [strategy_f], "squeeze": [strategy_g]}

FUNDING_WARMUP_DAYS = 45   # > SQUEEZE_PCTL_WINDOW (30d) + slack for the shift(1)


def signal_key(s) -> tuple:
    """Stable identity for a signal (timestamp + strategy + dir + entry)."""
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
@click.option("--days", default=60, type=int)
@click.option("--interval", default="1h")
@click.option("--samples", default=20, type=int,
              help="How many bars (with signals) to re-run truncated.")
@click.option("--seed", default=42, type=int)
@click.option("--strats", default="default", type=click.Choice(list(_SETS)),
              help="Strategy set to test (default = A-E engine set, radar = F-only).")
def main(symbol: str, days: int, interval: str, samples: int, seed: int, strats: str):
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=days)
    click.echo(f"fetching {symbol} {interval} for {days} days...")
    df = fetch_klines(symbol, interval,
                      int(start.timestamp() * 1000),
                      int(end.timestamp() * 1000))
    if df.empty:
        click.echo("no data")
        return
    click.echo(f"  {len(df)} bars")

    bar_dur = df.index[1] - df.index[0]
    fdf = None
    if strats == "squeeze":
        fdf = fetch_funding(symbol,
                            int((start - pd.Timedelta(days=FUNDING_WARMUP_DAYS)).timestamp() * 1000),
                            int(end.timestamp() * 1000))
        if fdf.empty:
            click.echo("no funding history — squeeze untestable on this symbol")
            return
        click.echo(f"  {len(fdf)} funding events")
        set_funding(symbol, fdf)

    click.echo("running engine on FULL dataset...")
    full_signals = run_engine(symbol, df, strategies=_SETS[strats])
    click.echo(f"  {len(full_signals)} signals")

    if not full_signals:
        click.echo("nothing to test (no signals)")
        return

    # Group full signals by bar_index for comparison.
    full_by_bar: dict[int, set[tuple]] = {}
    for s in full_signals:
        full_by_bar.setdefault(s.bar_index, set()).add(signal_key(s))

    bars_with_signals = sorted(full_by_bar.keys())
    click.echo(f"  signals span bars {bars_with_signals[0]} -> {bars_with_signals[-1]}")

    # Pick a random sample of those bars
    rng = random.Random(seed)
    sample_bars = rng.sample(bars_with_signals,
                             min(samples, len(bars_with_signals)))
    sample_bars.sort()
    click.echo(f"\nre-running engine on {len(sample_bars)} truncated slices...")

    mismatches = []
    for i, bar_idx in enumerate(sample_bars):
        # Truncate so the engine sees only [0..bar_idx]
        df_truncated = df.iloc[: bar_idx + 1].copy()
        if fdf is not None:
            # Funding no-lookahead: the truncated run may only know events SETTLED
            # by bar_idx's close. If the full run (full funding registered) still
            # matches per-bar, the funding plumbing leaks nothing from the future.
            trunc_close = df.index[bar_idx] + bar_dur
            set_funding(symbol, fdf[fdf.index <= trunc_close])
        truncated_signals = run_engine(symbol, df_truncated,
                                       start_index=bar_idx, end_index=bar_idx,
                                       strategies=_SETS[strats])
        if fdf is not None:
            set_funding(symbol, fdf)   # restore for the next iteration

        full_set = full_by_bar.get(bar_idx, set())
        trunc_set = {signal_key(s) for s in truncated_signals}

        match = full_set == trunc_set
        marker = "OK" if match else "MISMATCH"
        click.echo(f"  [{i+1:>3}/{len(sample_bars)}] bar {bar_idx:>5} "
                   f"full={len(full_set)} trunc={len(trunc_set)} -> {marker}")
        if not match:
            mismatches.append({
                "bar": bar_idx,
                "only_in_full": full_set - trunc_set,
                "only_in_trunc": trunc_set - full_set,
            })

    click.echo("\n" + "=" * 60)
    if not mismatches:
        click.echo(f"PASS — all {len(sample_bars)} sampled bars produce identical signals")
        click.echo("under full and truncated runs. NO LOOK-AHEAD BIAS DETECTED.")
    else:
        click.echo(f"FAIL — {len(mismatches)}/{len(sample_bars)} bars differ:")
        for m in mismatches[:10]:
            click.echo(f"\n  bar {m['bar']}:")
            for s in m["only_in_full"]:
                click.echo(f"    only in FULL  : {s}")
            for s in m["only_in_trunc"]:
                click.echo(f"    only in TRUNC : {s}")


if __name__ == "__main__":
    main()
