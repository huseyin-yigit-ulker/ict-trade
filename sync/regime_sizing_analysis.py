"""Risk-normalised A/B of regime-based position SIZING — Python port of
sync/regime_overlay.mjs (src/utils/regimeDetectors.js + regimeSizing.js), extended to
run BOTH 2026 (in-sample) and 2025 (out-of-sample).

Each strategy's resolved trades are mapped to the CAUSAL 6-detector ensemble score of
the last 4h bar closed before the signal fired (no look-ahead). Each sizing scheme
multiplies pnl_r by a regime-dependent risk size; we report the RISK-NORMALISED result
(scaling size inflates raw R for free, so compare R/risk and total-R re-scaled to the
baseline's total risk). 'bucket' (2x trend / 1x transition / 0.5x range) on KARMA is
exactly the wired 'karma_regime' stream.

Question: does regime-sizing lift risk-adjusted return — and does it SURVIVE 2025?
"""
import json
import math
import urllib.request
import sys

sys.path.insert(0, "sync")
import trade_sync_common as tsc

FOURH = 14_400_000
HOUR = 3_600_000
DETECTOR_WINDOW = 150
MINBARS = 60
VERSIONS = [("MAIN", "v1"), ("IMPULSE", "v2"), ("KARMA", "karma"), ("OPUS", "opus")]
SCHEMES = ["flat", "drop_range", "soft", "tilt", "bucket", "trend_only"]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def mean(a):
    return sum(a) / len(a) if a else 0.0


def ols_slope(xs, ys):
    mx, my = mean(xs), mean(ys)
    num = den = 0.0
    for x, y in zip(xs, ys):
        num += (x - mx) * (y - my)
        den += (x - mx) ** 2
    return num / den if den > 0 else float("nan")


def log_returns(c):
    return [math.log(c[i] / c[i - 1]) if c[i] > 0 and c[i - 1] > 0 else 0.0 for i in range(1, len(c))]


# ---- detectors (each -> score in [-1,1] or nan) ----
def det_er(closes, **_):
    n = 20
    if len(closes) < n + 1:
        return float("nan")
    i = len(closes) - 1
    change = abs(closes[i] - closes[i - n])
    vol = sum(abs(closes[j] - closes[j - 1]) for j in range(i - n + 1, i + 1))
    er = change / vol if vol > 0 else 0.0
    return clamp((er - 0.31) / 0.18, -1, 1)


def det_adx(highs, lows, closes, **_):
    n = 14
    L = len(closes)
    if L < 3 * n:
        return float("nan")
    tr, pDM, mDM = [], [], []
    for i in range(1, L):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        pDM.append(up if (up > dn and up > 0) else 0.0)
        mDM.append(dn if (dn > up and dn > 0) else 0.0)
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    def smooth(arr):
        out = [float("nan")] * len(arr)
        s = sum(arr[:n])
        out[n - 1] = s
        for i in range(n, len(arr)):
            s = s - s / n + arr[i]
            out[i] = s
        return out

    trS, pS, mS = smooth(tr), smooth(pDM), smooth(mDM)
    dx = []
    for i in range(n - 1, len(tr)):
        if not trS[i] or math.isnan(trS[i]):
            continue
        pdi = 100 * pS[i] / trS[i]
        mdi = 100 * mS[i] / trS[i]
        ssum = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / ssum if ssum > 0 else 0.0)
    if len(dx) < n:
        return float("nan")
    adx = mean(dx[:n])
    for i in range(n, len(dx)):
        adx = (adx * (n - 1) + dx[i]) / n
    return clamp((adx - 22.5) / 17.5, -1, 1)


def det_chop(highs, lows, closes, **_):
    n = 14
    L = len(closes)
    if L < n + 1:
        return float("nan")
    trSum = 0.0
    hi, lo = -math.inf, math.inf
    for i in range(L - n, L):
        trSum += max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        hi = max(hi, highs[i]); lo = min(lo, lows[i])
    rng = hi - lo
    ci = 100 * math.log10(trSum / rng) / math.log10(n) if rng > 0 else 100.0
    return clamp((50 - ci) / 15, -1, 1)


def det_hurst(returns, **_):
    N = len(returns)
    if N < 40:
        return float("nan")
    sizes = []
    n = 8
    while n <= N // 2:
        sizes.append(n)
        n = int(n * 1.7)
    if len(sizes) < 3:
        return float("nan")
    xs, ys = [], []
    for n in sizes:
        chunks = N // n
        rsSum = 0.0; cnt = 0
        for c in range(chunks):
            seg = returns[c * n:(c + 1) * n]
            m = mean(seg)
            dev = [v - m for v in seg]
            cum = 0.0; mn = math.inf; mx = -math.inf
            for dd in dev:
                cum += dd; mn = min(mn, cum); mx = max(mx, cum)
            R = mx - mn
            sd = math.sqrt(mean([dd * dd for dd in dev]))
            if sd > 0 and R > 0:
                rsSum += R / sd; cnt += 1
        if cnt > 0:
            xs.append(math.log(n)); ys.append(math.log(rsSum / cnt))
    if len(xs) < 3:
        return float("nan")
    h = ols_slope(xs, ys)
    return clamp((h - 0.5) / 0.18, -1, 1) if math.isfinite(h) else float("nan")


def det_vr(returns, **_):
    q = 4; N = len(returns)
    if N < q * 6:
        return float("nan")
    m = mean(returns)
    v1 = sum((r - m) ** 2 for r in returns) / (N - 1)
    if v1 <= 0:
        return float("nan")
    s = 0.0
    for i in range(0, N - q + 1):
        ssum = sum(returns[i + j] for j in range(q))
        s += (ssum - q * m) ** 2
    mDen = q * (N - q + 1) * (1 - q / N)
    vr = (s / mDen) / v1
    return clamp((vr - 1) / 0.35, -1, 1)


def det_acf(returns, **_):
    N = len(returns)
    if N < 12:
        return float("nan")
    m = mean(returns)
    num = den = 0.0
    for i in range(N):
        den += (returns[i] - m) ** 2
        if i > 0:
            num += (returns[i] - m) * (returns[i - 1] - m)
    rho = num / den if den > 0 else 0.0
    return clamp(rho / 0.20, -1, 1)


DETECTORS = [det_er, det_adx, det_chop, det_hurst, det_vr, det_acf]


def compute_score(kl_slice):
    if len(kl_slice) < 40:
        return float("nan")
    s = kl_slice[-max(DETECTOR_WINDOW, 60):]
    highs = [float(k[2]) for k in s]
    lows = [float(k[3]) for k in s]
    closes = [float(k[4]) for k in s]
    returns = log_returns(closes)
    ctx = dict(highs=highs, lows=lows, closes=closes, returns=returns)
    scores = []
    for d in DETECTORS:
        try:
            v = d(**ctx)
        except Exception:
            v = float("nan")
        if isinstance(v, float) and math.isfinite(v):
            scores.append(v)
    return mean(scores) if scores else float("nan")


def rolling_regime(klines, window=DETECTOR_WINDOW):
    out = []  # (openMs, score)
    for i in range(len(klines)):
        if i + 1 < MINBARS:
            out.append((int(klines[i][0]), float("nan")))
            continue
        sc = compute_score(klines[max(0, i - window + 1):i + 1])
        out.append((int(klines[i][0]), sc))
    return out


def size_of(score, scheme):
    if not (isinstance(score, float) and math.isfinite(score)):
        return 1.0
    if scheme == "flat":
        return 1.0
    if scheme == "drop_range":
        return 0.0 if score <= -0.15 else 1.0
    if scheme == "soft":
        return clamp(1 + 0.6 * score, 0.5, 1.6)
    if scheme == "tilt":
        return clamp(1 + score, 0.3, 2)
    if scheme == "bucket":
        return 2.0 if score >= 0.15 else (0.5 if score <= -0.15 else 1.0)
    if scheme == "trend_only":
        return 1.0 if score >= 0.15 else 0.0
    return 1.0


def max_dd(seq):
    peak = cum = dd = 0.0
    for r in seq:
        cum += r; peak = max(peak, cum); dd = max(dd, peak - cum)
    return dd


def fetch_klines(sym, start_ms):
    b = "".join(ch for ch in sym if ch.isalnum())
    now = tsc.pd.Timestamp.now(tz="UTC").value // 1_000_000 if hasattr(tsc, "pd") else None
    import time
    now = int(time.time() * 1000)
    all_k = []
    frm = start_ms
    for _ in range(12):
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={b}&interval=4h&startTime={frm}&limit=1500"
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.load(r)
        if not isinstance(d, list) or not d:
            break
        for k in d:
            if not all_k or int(k[0]) > int(all_k[-1][0]):
                all_k.append(k)
        last = int(d[-1][0])
        if len(d) < 1500 or last >= now - FOURH:
            break
        frm = last + 1
    return all_k


def score_at(roll, open_ms_list, fire_ms):
    lo, hi, idx = 0, len(open_ms_list) - 1, -1
    while lo <= hi:
        m = (lo + hi) >> 1
        if open_ms_list[m] + FOURH <= fire_ms:
            idx = m; lo = m + 1
        else:
            hi = m - 1
    return roll[idx][1] if idx >= 0 else float("nan")


def fetch_trades(conn, version, y0, y1):
    cur = conn.cursor()
    cur.execute(
        """SELECT symbol, signal_time, pnl_r, status FROM ict_trade.trading_signals
           WHERE version=%s AND signal_time>=%s AND signal_time<%s
             AND status IN ('closed_tp','closed_sl') AND pnl_r IS NOT NULL""",
        (version, y0, y1))
    rows = [{"symbol": s, "fire": int(t.timestamp() * 1000) + HOUR, "pnl_r": float(p), "status": st}
            for s, t, p, st in cur.fetchall()]
    cur.close()
    return rows


def eval_scheme(trades, regime_cache, scheme):
    totalR = risk = pos = neg = 0.0
    seq = []
    trend_risk = 0.0
    for tr in trades:
        rc = regime_cache.get(tr["symbol"])
        score = score_at(rc[0], rc[1], tr["fire"]) if rc else float("nan")
        size = size_of(score, scheme)
        r = tr["pnl_r"] * size
        totalR += r; risk += size; seq.append(r)
        if isinstance(score, float) and math.isfinite(score) and score >= 0.15:
            trend_risk += size
        if r > 0:
            pos += r
        else:
            neg += -r
    N = len(trades)
    rPerRisk = totalR / risk if risk > 0 else 0.0
    normTotalR = rPerRisk * N
    k = N / risk if risk > 0 else 0.0
    normDD = max_dd([r * k for r in seq])
    return dict(N=N, totalR=totalR, risk=risk, rPerRisk=rPerRisk, normTotalR=normTotalR,
                pf=(pos / neg if neg > 0 else float("inf")), normDD=normDD,
                trendRiskPct=100 * trend_risk / (risk or 1))


def run_year(conn, y0, y1, warm_ms, label):
    trades_by = {}
    symbols = set()
    for name, ver in VERSIONS:
        tr = fetch_trades(conn, ver, y0, y1)
        trades_by[name] = tr
        symbols.update(t["symbol"] for t in tr)
    cache = {}
    for sym in sorted(symbols):
        try:
            kl = fetch_klines(sym, warm_ms)
        except Exception:
            kl = []
        if len(kl) < 80:
            cache[sym] = None
            continue
        roll = rolling_regime(kl)
        cache[sym] = (roll, [int(k[0]) for k in kl])
    print(f"\n================  REGIME-SIZING A/B — {label}  ================")
    print("normR = total R re-scaled to baseline risk · R/risk = size-invariant edge\n")
    summary = {}
    for name, _ in VERSIONS:
        trades = trades_by[name]
        base = eval_scheme(trades, cache, "flat")
        print(f"### {name:<8} baseline: totalR={base['totalR']:+7.1f}  R/risk={base['rPerRisk']:+.3f}  "
              f"PF={base['pf']:.2f}  maxDD={base['normDD']:.1f}  (N={base['N']})")
        print(f"    {'scheme':<14}{'normR':>9}{'ΔnormR':>9}{'R/risk':>8}{'PF':>6}{'maxDD':>8}{'trendRisk%':>11}")
        rows = {}
        for sc in SCHEMES:
            e = eval_scheme(trades, cache, sc)
            rows[sc] = e
            d = e["normTotalR"] - base["totalR"]
            print(f"    {sc:<14}{e['normTotalR']:>9.1f}{('+' if d>=0 else '')+format(d,'.1f'):>9}"
                  f"{e['rPerRisk']:>+8.3f}{e['pf']:>6.2f}{e['normDD']:>8.1f}{e['trendRiskPct']:>10.0f}%")
        summary[name] = {"baseline": base, "schemes": rows}
    return summary


def main():
    conn = tsc.backtest_conn()
    s26 = run_year(conn, "2026-01-01", "2027-01-01", int(tsc.pd.Timestamp("2025-09-01", tz="UTC").timestamp() * 1000), "2026 (in-sample)")
    s25 = run_year(conn, "2025-01-01", "2026-01-01", int(tsc.pd.Timestamp("2024-09-01", tz="UTC").timestamp() * 1000), "2025 (OUT-OF-SAMPLE)")
    conn.close()
    # headline: KARMA bucket (= karma_regime) both years
    print("\n=== karma_regime (KARMA + bucket 2/1/0.5) : in-sample vs OOS ===")
    for lab, s in [("2026", s26), ("2025", s25)]:
        b = s["KARMA"]["baseline"]; k = s["KARMA"]["schemes"]["bucket"]
        print(f"  {lab}: KARMA flat normR={b['totalR']:+.1f} (R/risk {b['rPerRisk']:+.3f}) "
              f"-> bucket normR={k['normTotalR']:+.1f} (R/risk {k['rPerRisk']:+.3f})  ΔR/risk={k['rPerRisk']-b['rPerRisk']:+.3f}")


if __name__ == "__main__":
    main()
