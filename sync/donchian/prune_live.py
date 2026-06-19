"""Donchian LIVE-table pruner — delete signals that FAILED directional confirmation.

The emit-time pre-filter (canli.py) already stops *new* unconfirmed breakouts from ever
reaching ict_trade.signals, and the dashboard re-checks each signal at display time
(TradeContext ENTRY_CONFIRM_BUF gate). This module is the third leg: it sweeps the live
table and physically DELETES rows that are *conclusively* invalid — a breakout that moved
adversely (toward the stop) by buf*risk before favourably by buf*risk, OR whose fill
window has fully elapsed without ever confirming. It is conservative: a signal whose fill
window is still open (and hasn't gone adverse yet) is PENDING and is kept — it may still
confirm, exactly as the emit-time late-confirm path expects.

Classification per signal (mirror of trade_sync_common.entry_confirmed + the UI deadline):
  confirmed : favourable buf*risk reached before adverse buf*risk within the window  -> keep
  invalid   : adverse buf*risk first, OR window elapsed with full 1m coverage & no
              confirmation                                                            -> DELETE
  pending   : window still open and not yet adverse/confirmed (or 1m data missing)    -> keep

Run standalone:
    python sync/donchian/prune_live.py --dry-run          # classify, report, no delete
    python sync/donchian/prune_live.py --apply            # delete the invalid rows
    python sync/donchian/prune_live.py --apply --modes donchian dch30_4h

Or import and call prune(live_conn, now=..., apply=True) from the nightly sync.
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path
from collections import defaultdict

import pandas as pd

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))   # sync/        -> trade_sync_common
sys.path.insert(0, str(_HERE.parent))        # sync/donchian
import trade_sync_common as tsc              # noqa: E402
from ict import config as C                  # noqa: E402  (path added by tsc)

# Donchian live modes. d30_4h_so has NO own live mode — it reuses dch30_4h signals — so it
# is covered by pruning dch30_4h.
MODES = ("donchian", "dch30_4h", "dch30_4h6")
LTF_MIN = {"15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240}
EXPIRY_MINUTES = 180        # entry-fill window (matches strategy.EXPIRY_MINUTES)
_BAR = pd.Timedelta(minutes=1)

_SELECT = """SELECT id, symbol, direction, entry, sl, signal_time, mode, ltf_timeframe
             FROM ict_trade.signals WHERE mode = ANY(%s) ORDER BY symbol, signal_time"""
_DELETE = "DELETE FROM ict_trade.signals WHERE id = ANY(%s)"


def classify(df1m: pd.DataFrame, cts: pd.Timestamp, direction: str, entry: float, sl: float,
             now: pd.Timestamp, *, expiry_minutes: int = EXPIRY_MINUTES,
             buf: float | None = None) -> str:
    """Return 'confirmed' | 'pending' | 'invalid' for one breakout (window from bar-close cts)."""
    b = (getattr(C, "ENTRY_CONFIRM_BUF", 0.0) if buf is None else buf)
    risk = abs(float(entry) - float(sl))
    if b <= 0 or risk <= 0:
        return "confirmed"                          # gate disabled -> never prune
    if df1m is None or df1m.empty:
        return "pending"                            # no data to judge -> keep, re-check later
    idx = df1m.index
    if idx.tz is None:
        df1m = df1m.copy(); df1m.index = idx = idx.tz_localize("UTC")
    cts = pd.Timestamp(cts)
    cts = cts.tz_localize("UTC") if cts.tz is None else cts.tz_convert("UTC")
    win_end = cts + pd.Timedelta(minutes=expiry_minutes)
    p0 = int(idx.searchsorted(cts))
    p1 = int(idx.searchsorted(win_end))
    long = str(direction).lower() == "long"
    fav_lvl = entry + b * risk if long else entry - b * risk
    adv_lvl = entry - b * risk if long else entry + b * risk
    H = df1m["high"].values; L = df1m["low"].values
    for i in range(p0, p1):                          # walk bars inside [cts, win_end)
        if long:
            adv, fav = L[i] <= adv_lvl, H[i] >= fav_lvl
        else:
            adv, fav = H[i] >= adv_lvl, L[i] <= fav_lvl
        if adv:
            return "invalid"                         # adverse buffer first -> conclusively dead
        if fav:
            return "confirmed"                       # favourable buffer first -> taken
    # Neither buffer hit in the data we have. Only call it invalid if the window has fully
    # elapsed AND our 1m series actually covers it (last bar at/after win_end); otherwise the
    # window is still open or data is missing -> keep as pending.
    have_full = len(idx) > 0 and (idx[-1] + _BAR) >= win_end
    if now >= win_end and have_full:
        return "invalid"                             # 180m passed, never confirmed -> not taken
    return "pending"


def prune(live, *, now: pd.Timestamp | None = None, modes=MODES,
          apply: bool = False, verbose: bool = True) -> dict:
    """Classify every live Donchian signal; delete the conclusively-invalid ones if apply.

    Returns counts dict: {confirmed, pending, invalid, deleted, scanned}."""
    now = now or pd.Timestamp.now(tz="UTC")
    cur = live.cursor()
    cur.execute(_SELECT, (list(modes),))
    rows = cur.fetchall()
    by_sym: dict[str, list] = defaultdict(list)
    for r in rows:
        by_sym[r[1]].append(r)

    counts = {"confirmed": 0, "pending": 0, "invalid": 0, "deleted": 0, "scanned": len(rows)}
    invalid_ids: list[int] = []
    for sym, items in by_sym.items():
        # one 1m fetch per symbol, from the earliest bar-close (minus slack) to now
        earliest = min(items, key=lambda r: r[5])
        e_ltf = LTF_MIN.get(earliest[7] or "", 60)
        start = pd.Timestamp(earliest[5]) + pd.Timedelta(minutes=e_ltf) - pd.Timedelta(minutes=2)
        try:
            df1m = tsc.fetch_1m(sym, start, now)
        except Exception as ex:  # noqa: BLE001 — a fetch failure must never delete blind
            if verbose:
                print(f"  {sym:<10} fetch error ({ex}); {len(items)} kept as pending")
            counts["pending"] += len(items)
            continue
        for r in items:
            rid, _, direction, entry, sl, st, mode, ltf = r
            ltf_min = LTF_MIN.get(ltf or "", 60)
            cts = pd.Timestamp(st) + pd.Timedelta(minutes=ltf_min)
            verdict = classify(df1m, cts, direction, float(entry), float(sl), now)
            counts[verdict] += 1
            if verdict == "invalid":
                invalid_ids.append(rid)
                if verbose:
                    print(f"  INVALID  {sym:<10} {str(direction).upper():<5} "
                          f"{pd.Timestamp(st):%m-%d %H:%M} mode={mode}")

    if apply and invalid_ids:
        cur.execute(_DELETE, (invalid_ids,))
        live.commit()
        counts["deleted"] = cur.rowcount
    cur.close()
    if verbose:
        action = f"deleted {counts['deleted']}" if apply else "DRY-RUN (no delete)"
        print(f"  prune: scanned={counts['scanned']} confirmed={counts['confirmed']} "
              f"pending={counts['pending']} invalid={counts['invalid']} -> {action}")
    return counts


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="classify + report, no delete")
    g.add_argument("--apply", action="store_true", help="DELETE the conclusively-invalid rows")
    ap.add_argument("--modes", nargs="*", default=list(MODES),
                    help=f"live modes to scan (default {list(MODES)})")
    args = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    print(f"=== prune_live @ {now:%Y-%m-%d %H:%M}Z | modes={args.modes} | "
          f"buf={getattr(C, 'ENTRY_CONFIRM_BUF', 0.0)} | "
          f"{'APPLY' if args.apply else 'DRY-RUN'} ===", flush=True)
    live = tsc.live_conn()
    try:
        prune(live, now=now, modes=args.modes, apply=args.apply, verbose=True)
    finally:
        live.close()


if __name__ == "__main__":
    main()
