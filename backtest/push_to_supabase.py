"""Run backtest and push results to Supabase Postgres (ict_trade.trading_signals).

Reads connection from project root .env (BACKTESTING_DB_CONNECTION_STRING +
BACKTESTING_DB_TABLE). Defaults: BTCUSDT + ETHUSDT, 60 days, 5m.

WARNING: --clear truncates the destination table. The user must explicitly
authorise this before running with --clear.
"""

from __future__ import annotations
import os
import re
import sys
from pathlib import Path
from typing import Iterable

import click
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from ict.data import fetch_klines
from engine import run_engine
from ict.strategies import strategy_b, strategy_c, strategy_d, strategy_e
from backtester import simulate_signals, TradeStatus, TradeResult

# Production set (no Strategy A) — matches dag/dag.py and live_runner.
PRODUCTION_STRATEGIES = [strategy_b, strategy_c, strategy_d, strategy_e]

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

DSN = os.getenv("BACKTESTING_DB_CONNECTION_STRING")
TABLE_FQ = os.getenv("BACKTESTING_DB_TABLE", "ict_trade.trading_signals")


def parse_dsn(dsn: str) -> dict:
    """Parse postgresql://user:pass@host:port/db tolerating special chars in pass."""
    dsn = dsn.strip().strip('"').strip("'")
    m = re.match(r'^postgres(?:ql)?://([^:@]+):(.+)@([^:/?]+):(\d+)/([^?]+)(\?.*)?$', dsn)
    if not m:
        raise ValueError("Could not parse DSN")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": int(m.group(4)),
        "dbname": m.group(5),
    }


def split_schema_table(fq: str) -> tuple[str, str]:
    fq = fq.strip().strip('"').strip("'")
    if "." in fq:
        a, b = fq.split(".", 1)
        return a, b
    return "public", fq


def ensure_table(conn, schema: str, table: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f'create schema if not exists "{schema}"')
        cur.execute(f"""
            create table if not exists "{schema}"."{table}" (
                id bigserial primary key,
                symbol text not null,
                trade_type text not null,
                direction text,
                signal_time timestamptz not null,
                real_entry_time timestamptz,
                exit_time timestamptz,
                entry_price double precision not null,
                tp_price double precision,
                sl_price double precision,
                exit_price double precision,
                status text not null,
                pnl_r double precision,
                strategy text,
                quality text,
                confluence_score int,
                version text default 'v1',
                created_at timestamptz default now()
            )
        """)
        # add columns if upgrading from older schema
        for col, ddl in (
            ("direction", "text"),
            ("strategy", "text"),
            ("quality", "text"),
            ("confluence_score", "int"),
            ("version", "text"),
            ("real_entry_time", "timestamptz"),
            ("exit_time", "timestamptz"),
            ("exit_price", "double precision"),
            ("pnl_r", "double precision"),
        ):
            cur.execute(f"""
                alter table "{schema}"."{table}"
                add column if not exists "{col}" {ddl}
            """)
        cur.execute(f'create index if not exists "{table}_signal_time_idx" on "{schema}"."{table}" (signal_time desc)')
        cur.execute(f'create index if not exists "{table}_symbol_idx" on "{schema}"."{table}" (symbol)')
        cur.execute(f'create index if not exists "{table}_version_idx" on "{schema}"."{table}" (version)')
    conn.commit()


def truncate_table(conn, schema: str, table: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f'truncate table "{schema}"."{table}" restart identity')
    conn.commit()


def status_to_db(status: TradeStatus) -> str:
    return {
        TradeStatus.TP_HIT:      "closed_tp",
        TradeStatus.SL_HIT:      "closed_sl",
        TradeStatus.EXPIRED:     "cancelled",
        TradeStatus.INVALIDATED: "cancelled",
        TradeStatus.ACTIVE:      "open",
        TradeStatus.PENDING:     "pending",
    }[status]


def trades_to_rows(trades: Iterable[TradeResult], df: pd.DataFrame) -> list[tuple]:
    rows: list[tuple] = []
    for tr in trades:
        sig = tr.signal
        signal_time = sig.timestamp.to_pydatetime()
        entry_time = df.index[tr.entry_index].to_pydatetime() if tr.entry_index is not None else None
        exit_time = df.index[tr.exit_index].to_pydatetime() if tr.exit_index is not None else None
        rows.append((
            sig.symbol,
            "BUY" if sig.direction == "long" else "SELL",
            sig.direction.upper(),
            signal_time,
            entry_time,
            exit_time,
            float(sig.entry),
            float(sig.take_profit_1) if sig.take_profit_1 is not None else None,
            float(sig.stop_loss),
            float(tr.exit_price) if tr.exit_price is not None else None,
            status_to_db(tr.status),
            float(tr.pnl_r) if tr.pnl_r is not None else None,
            sig.strategy,
            sig.quality,
            int(sig.confluence_score),
            "v1",
        ))
    return rows


INSERT_SQL = """
insert into "{schema}"."{table}"
(symbol, trade_type, direction, signal_time, real_entry_time, exit_time,
 entry_price, tp_price, sl_price, exit_price, status, pnl_r,
 strategy, quality, confluence_score, version)
values %s
"""


def bulk_insert(conn, schema: str, table: str, rows: list[tuple]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, INSERT_SQL.format(schema=schema, table=table), rows)
    conn.commit()
    return len(rows)


def count_rows(conn, schema: str, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f'select count(*) from "{schema}"."{table}"')
        return cur.fetchone()[0]


@click.command()
@click.option("--symbols", default="BTCUSDT,ETHUSDT", help="Comma-separated symbols.")
@click.option("--days", default=60, type=int, help="Look-back window in days. Ignored if --start provided.")
@click.option("--start", default=None, help="ISO start date/time UTC (e.g. 2025-01-01). Overrides --days.")
@click.option("--end", default=None, help="ISO end date/time UTC. Defaults to now.")
@click.option("--interval", default="5m", help="Kline interval.")
@click.option("--clear/--no-clear", default=False,
              help="Truncate destination table before inserting. Destructive.")
@click.option("--dry-run", is_flag=True, help="Run engine + simulate but don't write.")
@click.option("--exclude-a", is_flag=True,
              help="Use production strategies (B/C/D/E) only. Mirrors live filter.")
def main(symbols: str, days: int, start: str | None, end: str | None,
         interval: str, clear: bool, dry_run: bool, exclude_a: bool) -> None:
    if not DSN:
        raise SystemExit("BACKTESTING_DB_CONNECTION_STRING missing in .env")

    schema, table = split_schema_table(TABLE_FQ)
    cfg = parse_dsn(DSN)
    click.echo(f"connecting to {cfg['host']}:{cfg['port']}/{cfg['dbname']} as {cfg['user']}")
    conn = psycopg2.connect(**cfg)

    try:
        ensure_table(conn, schema, table)
        before = count_rows(conn, schema, table)
        click.echo(f'rows in "{schema}"."{table}" before: {before}')

        if clear:
            if dry_run:
                click.echo(f"DRY-RUN: would truncate {schema}.{table}")
            else:
                click.echo(f'truncating "{schema}"."{table}"...')
                truncate_table(conn, schema, table)

        end_ts = pd.Timestamp(end, tz="UTC") if end else pd.Timestamp.now(tz="UTC")
        if start:
            start_ts = pd.Timestamp(start, tz="UTC")
            actual_days = (end_ts - start_ts).days
        else:
            start_ts = end_ts - pd.Timedelta(days=days)
            actual_days = days
        click.echo(f"period: {start_ts.isoformat()} -> {end_ts.isoformat()}  ({actual_days} days)")
        strategies = PRODUCTION_STRATEGIES if exclude_a else None
        click.echo(f"interval: {interval}  strategies: "
                   f"{'B/C/D/E (production)' if exclude_a else 'A/B/C/D/E (default)'}\n")

        total_signals = 0
        total_inserted = 0
        for sym in [s.strip() for s in symbols.split(",") if s.strip()]:
            click.echo(f"=== {sym} ===")
            df = fetch_klines(sym, interval,
                              int(start_ts.timestamp() * 1000),
                              int(end_ts.timestamp() * 1000))
            click.echo(f"  bars: {len(df)}")
            if df.empty:
                click.echo("  no data, skipping")
                continue
            sigs = run_engine(sym, df, strategies=strategies)
            click.echo(f"  signals (post-confluence): {len(sigs)}")
            trades = simulate_signals(sigs, df)
            tp = sum(1 for t in trades if t.status == TradeStatus.TP_HIT)
            sl = sum(1 for t in trades if t.status == TradeStatus.SL_HIT)
            inv = sum(1 for t in trades if t.status == TradeStatus.INVALIDATED)
            exp = sum(1 for t in trades if t.status == TradeStatus.EXPIRED)
            act = sum(1 for t in trades if t.status == TradeStatus.ACTIVE)
            click.echo(f"  outcomes: TP={tp} SL={sl} invalidated={inv} expired={exp} active={act}")
            total_signals += len(trades)

            if not dry_run:
                rows = trades_to_rows(trades, df)
                n = bulk_insert(conn, schema, table, rows)
                click.echo(f"  inserted: {n}\n")
                total_inserted += n
            else:
                click.echo("  DRY-RUN, no insert\n")

        after = count_rows(conn, schema, table)
        click.echo("─" * 50)
        click.echo(f"total trades simulated: {total_signals}")
        click.echo(f"total inserted:         {total_inserted}")
        click.echo(f'rows in "{schema}"."{table}" after: {after}')
    finally:
        conn.close()


if __name__ == "__main__":
    main()
