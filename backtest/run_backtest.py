"""CLI entry point for running an ICT backtest.

Examples
--------
# Pull 90 days of BTC 5m from Binance futures and backtest it:
python run_backtest.py --symbol BTCUSDT --interval 5m --days 90

# Use a local CSV (timestamp,open,high,low,close,volume):
python run_backtest.py --csv ./data/btc_5m.csv --symbol BTCUSDT

Output:
    ./out/{symbol}_{interval}_{from}_{to}.json   (signals, trades, metrics)
"""

from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import pandas as pd

# allow `python run_backtest.py` from this dir
sys.path.insert(0, str(Path(__file__).parent))

from ict.data import fetch_klines, load_csv
from engine import run_engine
from backtester import simulate_signals, compute_metrics, export_results


@click.command()
@click.option("--symbol", default="BTCUSDT", help="Symbol (Binance format).")
@click.option("--interval", default="5m", help="Kline interval (1m/5m/15m/1h/4h/1d).")
@click.option("--days", default=30, type=int, help="Days back from now (ignored when --csv).")
@click.option("--csv", "csv_path", default=None, help="Use a local CSV instead of Binance.")
@click.option("--futures/--spot", default=True)
@click.option("--out", "out_dir", default="./out", help="Output dir.")
@click.option("--start", default=None, help="ISO start (UTC), e.g. 2024-01-01. Overrides --days.")
@click.option("--end", default=None, help="ISO end (UTC).")
def main(symbol: str, interval: str, days: int, csv_path: str | None,
         futures: bool, out_dir: str, start: str | None, end: str | None) -> None:
    if csv_path:
        click.echo(f"loading CSV {csv_path}")
        df = load_csv(csv_path)
    else:
        end_dt = pd.Timestamp(end, tz="UTC") if end else pd.Timestamp.utcnow().tz_localize("UTC")
        if start:
            start_dt = pd.Timestamp(start, tz="UTC")
        else:
            start_dt = end_dt - pd.Timedelta(days=days)
        click.echo(f"fetching {symbol} {interval} {start_dt} -> {end_dt} (futures={futures})")
        df = fetch_klines(symbol, interval,
                          int(start_dt.timestamp() * 1000),
                          int(end_dt.timestamp() * 1000),
                          futures=futures)

    if df.empty:
        click.echo("No data.")
        sys.exit(1)
    click.echo(f"loaded {len(df)} bars: {df.index[0]} -> {df.index[-1]}")

    click.echo("running signal engine...")
    signals = run_engine(symbol, df)
    click.echo(f"  -> {len(signals)} signals after confluence merge")

    click.echo("simulating trades...")
    trades = simulate_signals(signals, df)
    metrics = compute_metrics(trades)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    fname = f"{symbol}_{interval}_{df.index[0].strftime('%Y%m%d')}_{df.index[-1].strftime('%Y%m%d')}.json"
    out_path = Path(out_dir) / fname
    export_results(trades, out_path)

    click.echo("\nMetrics:")
    for k, v in metrics.items():
        if isinstance(v, dict):
            click.echo(f"  {k}:")
            for sk, sv in v.items():
                click.echo(f"    {sk}: {sv}")
        else:
            click.echo(f"  {k}: {v}")
    click.echo(f"\nresults -> {out_path}")


if __name__ == "__main__":
    main()
