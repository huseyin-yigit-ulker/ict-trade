"""donchian_ict geometry validation — A (baseline ATR2/RR4) vs C (swing SL/RR4).

Same Donchian-55 + ER>=0.35 trigger and MARKET entry for both arms; only the STOP differs:
  A (current 'donchian')  SL = ATR(14)x2          TP = entry +/- 4*risk
  C ('donchian_ict')      SL = last structural    TP = entry +/- 4*risk
                               swing (floored)
(Arm B, liquidity TP, was dropped — it strangles the momentum edge: ~0.6 avgRR.)

Full 40-symbol universe, run over TWO windows — 2026 (in-sample) and 2025 (OOS) — so the
swing-stop edge is judged out-of-sample and across the whole book, not just the 4 it was
spotted on. Resolved on 1h bars (tie -> SL), 0.1% round-trip fee. This is a RELATIVE A/C
comparison (1h resolution is identical for both arms); absolute R for shipping is confirmed
later on the 1m pipeline. Note: XAU/XAG and the stock-perps have little/no 2025 history on
Binance, so 2025 OOS is effectively the crypto majors.

    python backtest/donchian_ict_bt.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1] / "sync" / "donchian"))
from ict.data import fetch_klines                        # noqa: E402
from ict import config as C                              # noqa: E402
from ict.indicators import atr as ict_atr                # noqa: E402
from ict import detectors as D                           # noqa: E402
from ict.strategies import _floor_stop                   # noqa: E402
import strategy as strat                                 # noqa: E402

FEE = 0.0005
SYMBOLS = strat.SYMBOLS                                   # full 40-symbol universe
CRYPTO = set(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "1000PEPEUSDT", "WIFUSDT",
              "SUIUSDT", "NEARUSDT", "FETUSDT", "ADAUSDT", "SUSDT", "ARBUSDT", "ORDIUSDT",
              "ONDOUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT"])
METAL = set(["XAUUSDT", "XAGUSDT"])
WINDOWS = [("2026", "2026-01-01", "2026-06-16"), ("2025", "2025-01-01", "2026-01-01")]
WARMUP = pd.Timedelta(days=15)


def cls_of(s):
    return "crypto" if s in CRYPTO else ("metal" if s in METAL else "stock")


def swing_sl(swings, i, entry, direction):
    want = "swing_low" if direction == "long" else "swing_high"
    best = None
    for s in swings:
        if s.confirmed_at > i or s.index >= i or s.type != want:
            continue
        if (direction == "long" and s.price < entry) or (direction == "short" and s.price > entry):
            if best is None or s.index > best.index:
                best = s
    return best.price if best else None


def resolve_1h(H, L, i, entry, sl, tp, direction):
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    for j in range(i + 1, len(H)):
        if direction == "long":
            if L[j] <= sl:
                return (sl - entry - FEE * (entry + sl)) / risk
            if H[j] >= tp:
                return (tp - entry - FEE * (entry + tp)) / risk
        else:
            if H[j] >= sl:
                return (entry - sl - FEE * (entry + sl)) / risk
            if L[j] <= tp:
                return (entry - tp - FEE * (entry + tp)) / risk
    return None


def run_window(sym, start, end):
    s_ms = int((pd.Timestamp(start, tz="UTC") - WARMUP).timestamp() * 1000)
    e_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    df = fetch_klines(sym, "1h", s_ms, e_ms)
    if df.empty or len(df) < 200:
        return [], []
    w0 = pd.Timestamp(start, tz="UTC")
    w1 = pd.Timestamp(end, tz="UTC")
    sigs = [s for s in strat.generate_signals(df, sym) if w0 <= s.timestamp < w1]
    if not sigs:
        return [], []
    a = ict_atr(df, C.ATR_PERIOD)
    swings = D.detect_swings(df, C.SWING_N_ITF)
    pos = df.index.get_indexer([s.timestamp for s in sigs])
    H, L = df["high"].values, df["low"].values
    A, Cc = [], []
    for s, i in zip(sigs, pos):
        if i < 0:
            continue
        entry = s.entry
        av = float(a.iloc[i]) if not np.isnan(a.iloc[i]) else 0.0
        if av <= 0:
            continue
        # A: ATR2 stop
        risk_a = 2.0 * av
        sl_a = entry - risk_a if s.direction == "long" else entry + risk_a
        tp_a = entry + 4 * risk_a if s.direction == "long" else entry - 4 * risk_a
        r = resolve_1h(H, L, i, entry, sl_a, tp_a, s.direction)
        if r is not None:
            A.append(r)
        # C: swing stop (floored), same 4*risk target
        raw = swing_sl(swings, i, entry, s.direction)
        if raw is None:
            raw = sl_a
        sl_c = _floor_stop(entry, raw, s.direction, av)
        risk_c = abs(entry - sl_c)
        tp_c = entry + 4 * risk_c if s.direction == "long" else entry - 4 * risk_c
        r = resolve_1h(H, L, i, entry, sl_c, tp_c, s.direction)
        if r is not None:
            Cc.append(r)
    return A, Cc


def agg(rs):
    if not rs:
        return (0, 0.0, 0.0)
    return (len(rs), sum(rs), 100 * sum(1 for x in rs if x > 0) / len(rs))


def main():
    print("donchian_ict validation | A=ATR2/RR4  C=swingSL/RR4 | 40 symbols | 1h-resolved\n")
    for label, start, end in WINDOWS:
        print(f"================  {label}  ({start} .. {end})  ================")
        by_cls = {"crypto": ([], []), "metal": ([], []), "stock": ([], [])}
        gA, gC = [], []
        rows = []
        for sym in SYMBOLS:
            A, Cc = run_window(sym, start, end)
            if not A and not Cc:
                continue
            nA, rA, wA = agg(A)
            nC, rC, wC = agg(Cc)
            rows.append((sym, nA, rA, rC, rC - rA))
            gA += A
            gC += Cc
            k = cls_of(sym)
            by_cls[k][0].extend(A)
            by_cls[k][1].extend(Cc)
        rows.sort(key=lambda x: x[4], reverse=True)
        print(f"  {'symbol':<10}{'n':>4}{'A_R':>9}{'C_R':>9}{'C-A':>8}")
        for sym, n, rA, rC, d in rows:
            print(f"  {sym:<10}{n:>4}{rA:>+9.1f}{rC:>+9.1f}{d:>+8.1f}")
        print("  " + "-" * 39)
        for k in ("crypto", "metal", "stock"):
            _, rA, wA = agg(by_cls[k][0])
            _, rC, wC = agg(by_cls[k][1])
            print(f"  {k:<10}{'':>4}{rA:>+9.1f}{rC:>+9.1f}{rC - rA:>+8.1f}")
        nA, rA, wA = agg(gA)
        nC, rC, wC = agg(gC)
        print(f"  {'ALL':<10}{nA:>4}{rA:>+9.1f}{rC:>+9.1f}{rC - rA:>+8.1f}   "
              f"(WR  A {wA:.0f}%  C {wC:.0f}%)\n")


if __name__ == "__main__":
    main()
