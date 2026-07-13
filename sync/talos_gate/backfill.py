"""TALOS·4H / TALOS-ICHI·4H backtest backfill -> version='talos_dg' + 'talos_kdg' (altın, 2026).

TALOS Keltner motorunu YAVAŞ TREND-YÖNÜ KAPISI ile XAUUSDT 1m üzerinde koşar ve her kapanmış
işlemi ict_trade.trading_signals'a yazar (DELETE version + upsert = idempotent), sync/talos_ichi/
backfill.py'nin birebir kardeşi. GECELİK çalışır. BACKTEST-ONLY (executor YOK, canlı emit YOK).

    python sync/talos_gate/backfill.py --dry-run
    python sync/talos_gate/backfill.py --apply
    python sync/talos_gate/backfill.py --apply --stream talos_kdg
"""
from __future__ import annotations
import sys
import argparse
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values, Json

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))                 # sync/talos_gate -> strategy
sys.path.insert(0, str(_HERE.parents[1]))             # sync/           -> trade_sync_common
import strategy as T                                  # noqa: E402  (TALOS-GATE strategy)
import trade_sync_common as tsc                       # noqa: E402

# version sütunu varchar(10) — 10 karakteri AŞMA (bkz. MIDAS.md 2026-07-08 'talos_ichix' taşması).
STREAMS = {
    "talos_dg": dict(
        mode="dg",
        label="TALOS·4H Keltner + 4h-Donchian yön kapısı (XAU 1m, ECN-FX cost)",
        desc="TALOS + 4h trend kapısı",
    ),
    "talos_kdg": dict(
        mode="kdg",
        label="TALOS-ICHI·4H Keltner + Kumo ∧ 4h-Donchian yön kapısı (XAU 1m, ECN-FX cost)",
        desc="TALOS + Kumo ∧ 4h trend kapısı",
    ),
}

YEAR_START = pd.Timestamp("2026-01-01", tz="UTC")
YEAR_END = pd.Timestamp("2027-01-01", tz="UTC")

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


def build_rows(trades, version: str, cfg: dict) -> list[dict]:
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
                          strategy=cfg["label"], quality=None, confluence_score=None)
        r["version"] = version
        r["context"] = {"kind": "trailing", "init_sl": float(t.stop),
                        "trail_mult": T.TRAIL_MULT, "atr_mult": T.ATR_INIT_MULT, "trail": t.trail,
                        "gate": cfg["mode"], "gate_tf": T.GATE_TF, "gate_n": T.GATE_N}
        rows.append(r)
    return rows


def run(version: str, cfg: dict, end: pd.Timestamp, apply: bool):
    print(f"\n=== [{version}] {cfg['desc']} | {YEAR_START.date()}..{end.date()} | "
          f"kapı {T.GATE_TF}/Donchian({T.GATE_N}) | cost ${T.COST_RT:g}/oz rt ===", flush=True)
    allt = T.generate_trades(YEAR_START, end, mode=cfg["mode"])
    open_now = [t for t in allt if t.reason == "open"]
    trades = [t for t in allt if t.reason != "open"]
    if not trades:
        print("  no settled trades."); return
    rows = build_rows(trades, version, cfg)
    totR = sum(t.pnl_r for t in trades)
    wins = sum(1 for t in trades if t.pnl_r > 0)
    pos = sum(t.pnl_r for t in trades if t.pnl_r > 0)
    neg = -sum(t.pnl_r for t in trades if t.pnl_r < 0)
    pf = (pos / neg) if neg > 0 else float("inf")
    print(f"  {len(trades)} SETTLED | totR={totR:+.1f} | avgR={totR/len(trades):+.3f} | "
          f"WR={wins/len(trades):.0%} | PF={pf:.2f}"
          + (f"  | {len(open_now)} açık -> hariç" if open_now else ""), flush=True)
    if not apply:
        print(f"  [dry-run] {len(rows)} satır yazılacaktı (version='{version}').")
        return
    conn = tsc.backtest_conn(); cur = conn.cursor()
    cur.execute(f"DELETE FROM {tsc.TABLE} WHERE version = %s", (version,))
    deleted = cur.rowcount
    conn.commit()
    n = _upsert_with_context(conn, rows)
    conn.close()
    print(f"  [DB] {deleted} eski satır silindi, {n} satır yazıldı (version='{version}')", flush=True)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--stream", default="all", choices=["all", *STREAMS])
    args = ap.parse_args()

    end = min(pd.Timestamp.now(tz="UTC"), YEAR_END)
    names = list(STREAMS) if args.stream == "all" else [args.stream]
    for nm in names:
        run(nm, STREAMS[nm], end, args.apply)


if __name__ == "__main__":
    main()
