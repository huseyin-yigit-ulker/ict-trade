"""Live ICT signal runner.

Designed to be invoked by a scheduled job (GitHub Actions cron, Airflow, etc.)
once per primary-TF bar close. Default cron: every hour at HH:05 UTC, after
the previous 1h bar has closed.

For each symbol:
  1. Fetch enough recent klines from Binance for the engine warmup.
  2. Drop the still-forming bar (real-time safety).
  3. Run the engine ONLY at the last closed bar — no look-ahead.
  4. For each new signal:
     - INSERT into ict_trade.signals (live table the React dashboard reads).
     - Send a Telegram message.

Required env (.env or CI secrets):
  DB_CONNECTION_STRING        live Postgres DSN
  DB_TABLE                    "ict_trade.signals" (default)
  TELEGRAM_BOT_TOKEN          (optional — if missing, Telegram is skipped)
  TELEGRAM_CHAT_ID            (optional — channel/group id)

Look-ahead safety: see backtest/test_no_lookahead.py — engine is verified
to produce identical signals on full vs truncated data.
"""

from __future__ import annotations
import os
import re
import sys
from pathlib import Path

import pandas as pd
import psycopg2
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from ict.data import fetch_klines
from engine import run_engine
from ict.strategies import Signal


# ---------------- config ----------------

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)  # silent if missing (CI passes via env)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT",
    "1000PEPEUSDT", "1000SHIBUSDT", "WIFUSDT", "TONUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "LINKUSDT", "SUSDT",
    "ARBUSDT", "OPUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
]

INTERVAL = "1h"          # primary timeframe (matches backtest "winner" config)
HTF_RULE = "4h"          # HTF bias source
# 6000h ≈ 250 days. HTF structure walk accumulates state from past swings;
# a longer warmup keeps the DAG ~99% bit-parity with a long-history backtest.
# Verified by test_dag_parity.py — DAG never emits EXTRA signals vs backtest,
# only occasionally suppresses one whose bias depends on very deep history.
WARMUP_HOURS = 6000

DSN = os.getenv("DB_CONNECTION_STRING")
DB_TABLE = os.getenv("DB_TABLE", "ict_trade.signals")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ---------------- helpers ----------------

def _parse_dsn(dsn: str) -> dict:
    dsn = dsn.strip().strip('"').strip("'")
    m = re.match(r'^postgres(?:ql)?://([^:@]+):(.+)@([^:/?]+):(\d+)/([^?]+)(\?.*)?$', dsn)
    if not m:
        raise ValueError("Could not parse DB_CONNECTION_STRING")
    return {
        "user": m.group(1), "password": m.group(2),
        "host": m.group(3), "port": int(m.group(4)),
        "dbname": m.group(5),
    }


def _split_table(fq: str) -> tuple[str, str]:
    fq = fq.strip().strip('"').strip("'")
    if "." in fq:
        a, b = fq.split(".", 1)
        return a, b
    return "public", fq


def _signal_row_exists(conn, schema: str, table: str, sig: Signal) -> bool:
    """Existence check by (symbol, signal_time, direction) tuple."""
    with conn.cursor() as cur:
        cur.execute(
            f'select 1 from "{schema}"."{table}" '
            f'where symbol = %s and signal_time = %s and direction = %s limit 1',
            (sig.symbol, sig.timestamp.to_pydatetime(), sig.direction.upper())
        )
        return cur.fetchone() is not None


def _insert_signal(conn, schema: str, table: str, sig: Signal) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f'''insert into "{schema}"."{table}"
                (symbol, direction, entry, sl, tp, signal_time, mode, ltf_timeframe, htf_timeframe, created_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())''',
            (
                sig.symbol,
                sig.direction.upper(),
                float(sig.entry),
                float(sig.stop_loss),
                float(sig.take_profit_1) if sig.take_profit_1 is not None else None,
                sig.timestamp.to_pydatetime(),
                "live",
                INTERVAL,
                HTF_RULE,
            )
        )
    conn.commit()


def _send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if not r.ok:
            print(f"  telegram error {r.status_code}: {r.text[:200]}")
        return r.ok
    except Exception as e:
        print(f"  telegram exception: {e}")
        return False


def _format_message(sig: Signal) -> str:
    arrow = "🟢 LONG" if sig.direction == "long" else "🔴 SHORT"
    rr = sig.risk_reward_1 if sig.risk_reward_1 else 0
    risk_pct = abs(sig.entry - sig.stop_loss) / sig.entry * 100
    target_pct = abs(sig.take_profit_1 - sig.entry) / sig.entry * 100 if sig.take_profit_1 else 0
    quality_emoji = "⭐" if sig.quality == "high" else "✓"
    return (
        f"<b>{arrow} {sig.symbol}</b>\n"
        f"📋 {sig.strategy}\n"
        f"⏰ {sig.timestamp.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"🎯 Entry: <code>{sig.entry:.6g}</code>\n"
        f"✅ TP: <code>{sig.take_profit_1:.6g}</code>  (+{target_pct:.2f}%)\n"
        f"🛑 SL: <code>{sig.stop_loss:.6g}</code>  (-{risk_pct:.2f}%)\n\n"
        f"📊 RR <b>1:{rr:.2f}</b>  |  {quality_emoji} {sig.quality}  |  score {sig.confluence_score}"
    )


def _fetch_recent(symbol: str) -> pd.DataFrame:
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(hours=WARMUP_HOURS)
    return fetch_klines(symbol, INTERVAL,
                        int(start.timestamp() * 1000),
                        int(end.timestamp() * 1000))


def _trim_open_bar(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the most recent bar if it hasn't fully closed yet."""
    if df.empty:
        return df
    bar_minutes = (df.index[1] - df.index[0]).total_seconds() / 60 if len(df) > 1 else 60
    last_bar_open = df.index[-1]
    expected_close = last_bar_open + pd.Timedelta(minutes=bar_minutes)
    if pd.Timestamp.now(tz="UTC") < expected_close:
        return df.iloc[:-1]
    return df


# ---------------- main ----------------

def process_symbol(conn, schema: str, table: str, symbol: str) -> int:
    df = _fetch_recent(symbol)
    if df.empty:
        print(f"  {symbol}: no data")
        return 0

    df = _trim_open_bar(df)
    if len(df) < 60:
        print(f"  {symbol}: only {len(df)} bars after trim, skipping")
        return 0

    last_idx = len(df) - 1
    signals = run_engine(symbol, df, start_index=last_idx, end_index=last_idx)

    new_count = 0
    for sig in signals:
        if _signal_row_exists(conn, schema, table, sig):
            print(f"  {symbol}: dup {sig.direction.upper()} @ {sig.timestamp} (skipped)")
            continue
        _insert_signal(conn, schema, table, sig)
        sent = _send_telegram(_format_message(sig))
        suffix = "tg ok" if sent else "tg skipped"
        print(f"  {symbol}: NEW {sig.direction.upper()} entry={sig.entry:.6g} "
              f"tp={sig.take_profit_1:.6g} sl={sig.stop_loss:.6g} ({suffix})")
        new_count += 1
    if new_count == 0 and not signals:
        print(f"  {symbol}: no signal at last closed bar ({df.index[-1]})")
    return new_count


def main() -> None:
    if not DSN:
        raise SystemExit("DB_CONNECTION_STRING missing")

    cfg = _parse_dsn(DSN)
    schema, table = _split_table(DB_TABLE)
    print(f"connecting to {cfg['host']}:{cfg['port']}/{cfg['dbname']} as {cfg['user']}")
    print(f"target table: {schema}.{table}")
    print(f"telegram: {'enabled' if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else 'disabled'}")
    print(f"interval: {INTERVAL}  warmup: {WARMUP_HOURS}h\n")

    conn = psycopg2.connect(**cfg)
    try:
        total_new = 0
        for sym in SYMBOLS:
            print(f"=== {sym} ===")
            try:
                total_new += process_symbol(conn, schema, table, sym)
            except Exception as e:
                print(f"  ERROR: {e}")
                conn.rollback()
        print(f"\nDone. {total_new} new signal(s) emitted.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
