"""TALOS backtest backfill -> version='talos' (gold-only, 2026).

Runs the full Keltner-trend walk on XAUUSDT 1m for 2026 and writes one closed-trade row per trade to
ict_trade.trading_signals (version='talos'), idempotently (DELETE version + upsert) — the exact
sibling of sync/midas/backfill.py. Meant to run NIGHTLY so the 2026 book extends as the year accrues.
Standalone — does NOT depend on live mode='talos' signal resolution.

    python sync/talos/backfill.py --dry-run
    python sync/talos/backfill.py --apply
"""
from __future__ import annotations
import sys
import argparse
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values, Json

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))                 # sync/talos -> strategy
sys.path.insert(0, str(_HERE.parents[1]))             # sync/      -> trade_sync_common
import strategy as T                                  # noqa: E402
import trade_sync_common as tsc                       # noqa: E402

VERSION = "talos"

# Upsert that also writes the `context` jsonb (the trailing-stop path) — tsc.upsert_rows omits it.
_CTX_COLS = tsc._COLS + ["context"]
_CTX_UPSERT = f"""
INSERT INTO {tsc.TABLE} ({", ".join(_CTX_COLS)}) VALUES %s
ON CONFLICT (symbol, signal_time, trade_type, version) DO UPDATE SET
  status=EXCLUDED.status, real_entry_time=EXCLUDED.real_entry_time, exit_time=EXCLUDED.exit_time,
  exit_price=EXCLUDED.exit_price, pnl_r=EXCLUDED.pnl_r, signal_price=EXCLUDED.signal_price,
  entry_price=EXCLUDED.entry_price, sl_price=EXCLUDED.sl_price, tp_price=EXCLUDED.tp_price,
  strategy=EXCLUDED.strategy, quality=EXCLUDED.quality, confluence_score=EXCLUDED.confluence_score,
  context=EXCLUDED.context
"""


def _upsert_with_context(conn, rows: list[dict]) -> int:
    vals = [tuple(Json(r[c]) if c == "context" else r[c] for c in _CTX_COLS) for r in rows]
    cur = conn.cursor()
    execute_values(cur, _CTX_UPSERT, vals, page_size=500)
    conn.commit(); cur.close()
    return len(rows)


STRATEGY_LABEL = "TALOS Keltner-Trend (XAU 1m, ECN-FX cost)"
YEAR_START = pd.Timestamp("2026-01-01", tz="UTC")
YEAR_END = pd.Timestamp("2027-01-01", tz="UTC")


def build_rows(trades) -> list[dict]:
    rows = []
    for t in trades:
        status = "closed_tp" if t.pnl_r >= 0 else "closed_sl"
        direction = "long" if t.side > 0 else "short"
        outcome = {
            "status": status,
            "real_entry_time": t.entry_time.to_pydatetime(),
            "exit_time": t.exit_time.to_pydatetime(),
            "exit_price": float(t.exit_px),
            "pnl_r": float(t.pnl_r),
        }
        r = tsc.build_row(T.SYMBOL, t.signal_time, direction,
                          float(t.entry), float(t.stop), float(t.tp_ref), outcome,
                          strategy=STRATEGY_LABEL, quality=None, confluence_score=None)
        r["version"] = VERSION
        # trailing-stop path for the UI: the fixed initial SL (1R) + the ratcheting stop levels.
        r["context"] = {"kind": "trailing", "init_sl": float(t.stop),
                        "trail_mult": T.TRAIL_MULT, "atr_mult": T.ATR_INIT_MULT, "trail": t.trail}
        rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC")
    end = min(now, YEAR_END)
    print(f"=== [{VERSION}] TALOS XAU Keltner-trend | {YEAR_START.date()}..{end.date()} | "
          f"cost ${T.COST_RT:g}/oz rt ===", flush=True)
    all_trades = T.generate_trades(YEAR_START, end)
    # BACKTEST = SETTLED trades only; a still-open trade stays LIVE and lands here once closed.
    open_now = [t for t in all_trades if t.reason == "open"]
    trades = [t for t in all_trades if t.reason != "open"]
    rows = build_rows(trades)
    if not rows:
        print("  no settled trades."); return
    totR = sum(t.pnl_r for t in trades)
    wins = sum(1 for t in trades if t.pnl_r > 0)
    pf_num = sum(t.pnl_r for t in trades if t.pnl_r > 0)
    pf_den = -sum(t.pnl_r for t in trades if t.pnl_r < 0)
    pf = (pf_num / pf_den) if pf_den > 0 else float("inf")
    print(f"  {len(trades)} SETTLED trades | totR={totR:+.1f} | WR={wins/len(trades):.0%} | PF={pf:.2f}"
          + (f"  | {len(open_now)} still-open -> LIVE (excluded)" if open_now else ""), flush=True)
    for t in open_now:
        d = "long" if t.side > 0 else "short"
        print(f"    ⏳ OPEN {d} from {t.entry_time:%m-%d %H:%M} entry={t.entry:.2f} "
              f"(floating {t.pnl_r:+.2f}R) -> stays live", flush=True)

    if args.dry_run:
        print(f"  [dry-run] {len(rows)} rows would upsert (version='{VERSION}').")
        for t in trades[:5]:
            d = "long" if t.side > 0 else "short"
            print(f"    {t.entry_time:%m-%d %H:%M} {d:<5} entry={t.entry:.2f} "
                  f"sl={t.stop:.2f} exit={t.exit_px:.2f} R={t.pnl_r:+.2f} ({t.reason})")
        return

    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (VERSION,))
    deleted = cur.rowcount
    conn.commit()
    n = _upsert_with_context(conn, rows)
    conn.close()
    print(f"  [DB] deleted {deleted} old, upserted {n} rows for version='{VERSION}'", flush=True)


if __name__ == "__main__":
    main()
