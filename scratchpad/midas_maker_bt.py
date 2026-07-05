"""MIDAS maker-limit-entry backtest — does a post-only LIMIT entry keep the edge net-of-Binance-fee?

Reuses the SHIPPED strategy engine (sync/midas/strategy.py) for df / signals / atr / vwap, then:
  - BASELINE  = M.walk() market entry at next-open (taker), re-priced under 3 cost models.
  - LIMIT     = same signals but enter via a passive maker LIMIT; a trade only counts if price
                comes back to the limit within a validity window (else MISSED = adverse selection).
Exit is always the 3.5xATR chandelier / session / 8h stop (taker on Binance — a stop can't be maker).
No lookahead: the limit is posted at the signal-bar close (effective next bar), fills scanned forward.
"""
import sys, pandas as pd, numpy as np
sys.path.insert(0, "sync/midas")
import strategy as M

START = pd.Timestamp("2026-01-01", tz="UTC")
END   = pd.Timestamp("2026-07-02", tz="UTC")

# Binance USDⓈ-M futures standard fees (before BNB/VIP discounts)
MAKER = 0.0002   # 0.020%
TAKER = 0.0005   # 0.050%
FX_FLAT = M.COST_RT   # $0.50/oz round-trip (the model MIDAS was validated with)

def net_r(entry, exit_px, sd, side, cost_rt):
    return ((exit_px - entry) * side - cost_rt) / sd

def summarize(rs):
    rs = list(rs)
    n = len(rs)
    tot = sum(rs)
    wins = sum(1 for r in rs if r > 0)
    pf_n = sum(r for r in rs if r > 0); pf_d = -sum(r for r in rs if r < 0)
    pf = pf_n / pf_d if pf_d > 0 else float("inf")
    return n, tot, (tot / n if n else 0), (wins / n * 100 if n else 0), pf

# ---- build the engine inputs exactly like generate_trades() ----
print("loading 1m XAUUSDT + building signals ...", flush=True)
df = M.load_1m(START - pd.Timedelta(days=2), END)
df = M.add_market_open(df)
atr = M.atr_tf(df)
side, stop = M.signals(df, atr)
vwap = M.anchored_vwap(df).to_numpy()
o = df["open"].to_numpy(); h = df["high"].to_numpy(); l = df["low"].to_numpy(); c = df["close"].to_numpy()
openmkt = df["open_mkt"].to_numpy(bool); ts = df.index; a = atr.to_numpy(); n = len(df)
in_range = ts >= START

# ================= BASELINE: market entry (the shipped walk) =================
trades = [t for t in M.walk(df, side, stop, a, cost=0.0) if t.entry_time >= START]  # gross (cost=0)
def reprice(t, cost_fn):
    sd = abs(t.entry - t.stop)
    ef, xf = cost_fn(t.entry, t.exit_px)
    return net_r(t.entry, t.exit_px, sd, t.side, ef + xf)
base_fx   = [reprice(t, lambda e, x: (FX_FLAT, 0.0)) for t in trades]
base_tk   = [reprice(t, lambda e, x: (e * TAKER, x * TAKER)) for t in trades]
base_mktk = [reprice(t, lambda e, x: (e * MAKER, x * TAKER)) for t in trades]

print("\n================= BASELINE — MARKET entry at next-open (current behavior) =================")
for name, rs in [("FX flat $0.50 (validated model)", base_fx),
                 ("Binance TAKER+TAKER (real now)", base_tk),
                 ("Binance MAKER+TAKER (if entry were maker, same fills)", base_mktk)]:
    N, tot, avg, wr, pf = summarize(rs)
    print(f"  {name:52s} n={N} totR={tot:+7.1f} avg={avg:+.3f} WR={wr:4.0f}% PF={pf:.2f}")

# ================= LIMIT entry variants =================
def walk_limit(limit_mode, W, entry_fee_bps, exit_fee_bps, flat_cost=None):
    """limit_mode: 'vwap' (L=vw[i]) | 'close' (L=c[i]) | 'open' (L=o[i+1]).
    W: validity window in bars (minutes). flat_cost: if set, charge that $/oz round-trip instead
    of the bps fees. Returns (rs, filled, missed)."""
    out = []; filled = 0; missed = 0
    i = M.SLOPE_N + 1
    while i < n - 1:
        s = side[i]
        if s == 0 or not openmkt[i] or not np.isfinite(stop[i]):
            i += 1; continue
        if ts[i] < START:
            i += 1; continue
        k = i + 1
        L = vwap[i] if limit_mode == "vwap" else (c[i] if limit_mode == "close" else o[k])
        st = stop[i]; sd = abs(L - st)
        if sd <= 0 or not np.isfinite(sd) or not np.isfinite(L):
            i += 1; continue
        # --- passive maker fill scan: price must come to the limit within W bars ---
        fill_bar = None
        for j in range(k, min(k + W, n)):
            if not openmkt[j]:
                break  # session closed before fill -> cancel
            touched = (l[j] <= L) if s > 0 else (h[j] >= L)
            if touched:
                fill_bar = j; break
        if fill_bar is None:
            missed += 1; i += 1; continue
        filled += 1
        entry = L; jbar = fill_bar
        # --- trailing exit: identical geometry to walk() from the fill bar ---
        best = entry; exit_px = np.nan; xi = None; st_tr = st
        j = jbar
        while j < n:
            if not openmkt[j]:
                exit_px = c[j - 1]; xi = j - 1; break
            hit = (l[j] <= st_tr) if s > 0 else (h[j] >= st_tr)
            if hit:
                exit_px = (min(st_tr, o[j]) if s > 0 else max(st_tr, o[j])); xi = j; break
            if M.MAX_HOLD_MIN and (j - jbar) >= M.MAX_HOLD_MIN:
                exit_px = c[j]; xi = j; break
            if j + 1 >= n:
                exit_px = c[j]; xi = j; break            # data edge (unresolved) — count it
            if not openmkt[j + 1]:
                exit_px = c[j]; xi = j; break
            if M.TRAIL_MULT > 0 and np.isfinite(a[j]):
                if s > 0:
                    best = max(best, h[j]); st_tr = max(st_tr, best - M.TRAIL_MULT * a[j])
                else:
                    best = min(best, l[j]); st_tr = min(st_tr, best + M.TRAIL_MULT * a[j])
            j += 1
        cost_rt = flat_cost if flat_cost is not None else (entry * entry_fee_bps + exit_px * exit_fee_bps)
        out.append(net_r(entry, exit_px, sd, s, cost_rt))
        i = xi + 1  # single position: resume after the exit
    return out, filled, missed

print("\n================= LIMIT entry — maker entry (0.02%) + taker exit (0.05%), Binance =================")
print("  (a trade MISSED = price never returned to the limit within the window = adverse selection)")
for mode in ["vwap", "close"]:
    print(f"\n  --- limit @ {mode.upper()}"
          + (" (pullback-to-VWAP, most passive)" if mode == "vwap" else " (signal reclaim close, near market)") + " ---")
    for W in [5, 15, 30, 60]:
        rs, fld, mis = walk_limit(mode, W, MAKER, TAKER)
        N, tot, avg, wr, pf = summarize(rs)
        fillpct = fld / (fld + mis) * 100 if (fld + mis) else 0
        print(f"    W={W:3d}m  fill={fld:4d}/{fld+mis:4d} ({fillpct:4.0f}%)  "
              f"totR={tot:+7.1f}  avg={avg:+.3f}  WR={wr:4.0f}%  PF={pf:.2f}")

# reference: limit @ VWAP with FX flat cost — isolates the FILL effect (missed trades) from the FEE effect
print("\n  --- reference: limit @ VWAP with FX flat $0.50 (fill-effect only, no Binance % fee) ---")
for W in [15, 60]:
    rs, fld, mis = walk_limit("vwap", W, 0, 0, flat_cost=FX_FLAT)
    N, tot, avg, wr, pf = summarize(rs)
    fillpct = fld / (fld + mis) * 100 if (fld + mis) else 0
    print(f"    W={W:3d}m  fill={fld:4d}/{fld+mis:4d} ({fillpct:4.0f}%)  "
          f"totR={tot:+7.1f}  avg={avg:+.3f}  WR={wr:4.0f}%  PF={pf:.2f}")
print("\n(Compare each LIMIT total against BASELINE Binance TAKER+TAKER above — that is the number to beat.)")
