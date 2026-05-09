"""ICT Live Signal DAG.

Replaces the legacy single-FVG heuristic with the full ICT backtest engine
(5 strategies A-E, MTF 4h-bias, time-aware OB/FVG state). The engine is
verified look-ahead-free by backtest/test_no_lookahead.py — meaning the
signal produced live at bar T is identical to the signal the same engine
produces at bar T in a backtest replay.

Hourly at HH:05 UTC: pulls 30 days of recent 1h klines per symbol from
Binance, runs the engine ONLY on the last fully-closed bar, then for any
new signal:
  - INSERT into ict_trade.signals (live dashboard table)
  - send Telegram alert
Idempotent on (symbol, signal_time, direction).
"""

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago
from airflow.timetables.trigger import CronTriggerTimetable

import sys
import time
import datetime as dt
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine, text

# Make backtest/ package importable from this DAG file (sibling directory).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKTEST_DIR = PROJECT_ROOT / "backtest"
if str(BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(BACKTEST_DIR))

from ict.data import fetch_klines       # noqa: E402
from engine import run_engine            # noqa: E402


# ----------------------------
# Default DAG arguments
# ----------------------------
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': dt.timedelta(minutes=2),
}

# ----------------------------
# Configuration
# ----------------------------
TELEGRAM_BOT_TOKEN = 'your_telegram_bot_token'
TELEGRAM_CHAT_ID = 'your_telegram_chat_id'

DB_CONNECTION_STRING = "postgresql://postgres.xxxx:your_password@aws-1-eu-central-1.pooler.supabase.com:6543/postgres"

# Engine knobs — must match backtest config.py to keep parity.
INTERVAL = "1h"
HTF_RULE = "4h"
# 6000h ≈ 250 days. The HTF structure walk accumulates state from past swings;
# a longer warmup ensures the DAG sees the same structure events a long-history
# backtest would. test_dag_parity.py shows ~99% parity at this size — DAG never
# emits EXTRA signals vs backtest, only occasionally suppresses one whose bias
# depends on structure events older than the warmup.
WARMUP_HOURS = 6000

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT",
    "1000PEPEUSDT", "1000SHIBUSDT", "WIFUSDT", "TONUSDT", "SUIUSDT",
    "NEARUSDT", "FETUSDT", "ADAUSDT", "LINKUSDT", "SUSDT",
    "ARBUSDT", "OPUSDT", "ORDIUSDT", "ONDOUSDT",
    "XAUUSDT", "XAGUSDT",
]


# ----------------------------
# Utility functions
# ----------------------------
def send_telegram_message(text_msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text_msg, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=15)
        if not response.ok:
            print("Telegram error:", response.text[:200])
    except Exception as e:
        print("Telegram exception:", e)


def get_db_engine():
    return create_engine(DB_CONNECTION_STRING)


def signal_already_exists(conn, symbol: str, signal_time, direction: str) -> bool:
    q = text("""
        SELECT 1 FROM ict_trade.signals
        WHERE symbol = :symbol
          AND signal_time = :signal_time
          AND direction = :direction
        LIMIT 1
    """)
    return conn.execute(q, {
        "symbol": symbol,
        "signal_time": signal_time,
        "direction": direction,
    }).fetchone() is not None


def save_signal_to_db(sig) -> bool:
    """Insert into ict_trade.signals if not already present.

    Returns True only if a NEW row was inserted, so the caller knows whether
    to fire the Telegram alert."""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            direction = sig.direction.upper()
            sig_time = sig.timestamp.to_pydatetime()

            if signal_already_exists(conn, sig.symbol, sig_time, direction):
                print(f"  dup {sig.symbol} {direction} @ {sig_time} (skipped)")
                return False

            q = text("""
                INSERT INTO ict_trade.signals
                (symbol, direction, entry, sl, tp, signal_time, mode, ltf_timeframe, htf_timeframe)
                VALUES
                (:symbol, :direction, :entry, :sl, :tp, :signal_time, :mode, :ltf, :htf)
            """)
            conn.execute(q, {
                "symbol": sig.symbol,
                "direction": direction,
                "entry": float(sig.entry),
                "sl": float(sig.stop_loss),
                "tp": float(sig.take_profit_1) if sig.take_profit_1 is not None else None,
                "signal_time": sig_time,
                "mode": "live",
                "ltf": INTERVAL,
                "htf": HTF_RULE,
            })
            conn.commit()
            print(f"  ✅ saved {sig.symbol} {direction} @ {sig_time}")
            return True
    except Exception as e:
        print(f"  ❌ DB save error: {e}")
        return False


def format_telegram_message(sig) -> str:
    arrow = "🟢 LONG" if sig.direction == "long" else "🔴 SHORT"
    rr = sig.risk_reward_1 if sig.risk_reward_1 else 0
    risk_pct = abs(sig.entry - sig.stop_loss) / sig.entry * 100
    target_pct = (abs(sig.take_profit_1 - sig.entry) / sig.entry * 100
                  if sig.take_profit_1 is not None else 0)
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


def trim_open_bar(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the most recent bar if it hasn't fully closed yet — guarantees
    real-time parity with backtest (which only consumes closed bars)."""
    if df.empty or len(df) < 2:
        return df
    bar_minutes = (df.index[1] - df.index[0]).total_seconds() / 60
    last_open = df.index[-1]
    expected_close = last_open + pd.Timedelta(minutes=bar_minutes)
    if pd.Timestamp.now(tz="UTC") < expected_close:
        return df.iloc[:-1]
    return df


def process_symbol(symbol: str) -> int:
    """Fetch → engine on last closed bar → emit any new signal. Returns count."""
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(hours=WARMUP_HOURS)
    df = fetch_klines(
        symbol, INTERVAL,
        int(start.timestamp() * 1000),
        int(end.timestamp() * 1000),
    )
    if df.empty:
        print(f"  {symbol}: no data")
        return 0

    df = trim_open_bar(df)
    if len(df) < 60:
        print(f"  {symbol}: only {len(df)} bars after trim, skipping")
        return 0

    last_idx = len(df) - 1
    signals = run_engine(symbol, df, start_index=last_idx, end_index=last_idx)

    n_emitted = 0
    for sig in signals:
        if save_signal_to_db(sig):
            send_telegram_message(format_telegram_message(sig))
            n_emitted += 1

    if not signals:
        print(f"  {symbol}: no signal at last closed bar ({df.index[-1]})")
    return n_emitted


# ----------------------------
# DAG Definition
# ----------------------------

@dag(
    dag_id="huseyin_llm_hybrid_ict",
    default_args=default_args,
    # Hourly at HH:05 UTC — engine is 1h-based; HH:05 ensures the previous
    # 1h bar is fully closed and finalized at Binance.
    schedule=CronTriggerTimetable("5 * * * *", timezone="UTC"),
    catchup=False,
    tags=['trading', 'ict', 'crypto', 'mtf'],
)
def ict_dag():

    @task()
    def scan_market():
        time.sleep(2)
        print(f"Toplam Taranacak Sembol Sayısı: {len(SYMBOLS)}")
        total = 0
        for sym in SYMBOLS:
            print(f"=== {sym} ===")
            try:
                total += process_symbol(sym)
            except Exception as e:
                print(f"  ERROR analyzing {sym}: {e}")
        print(f"\nDone. {total} new signal(s) emitted.")

    scan_market()


dag = ict_dag()
