"""6-detector regime ensemble — Python port of src/utils/regimeDetectors.js.

Each detector scores trend(+1)↔range(−1) from a different angle; the ensemble score
is the mean of the finite detector scores over the trailing DETECTOR_WINDOW (150) 4h
bars. verdict(): score>=0.15 trend, <=-0.15 range, else transition.

Used to gate/size strategies by regime CAUSALLY (the last 4h bar closed before a
signal fires — no look-ahead). build_rolling() + score_at() give a per-symbol causal
lookup. Mirrors regimeDetectors.js exactly (same constants/formulas).
"""
import math

FOURH_MS = 14_400_000
DETECTOR_WINDOW = 150
MINBARS = 60


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _mean(a):
    return sum(a) / len(a) if a else 0.0


def _ols_slope(xs, ys):
    mx, my = _mean(xs), _mean(ys)
    num = den = 0.0
    for x, y in zip(xs, ys):
        num += (x - mx) * (y - my)
        den += (x - mx) ** 2
    return num / den if den > 0 else float("nan")


def _log_returns(c):
    return [math.log(c[i] / c[i - 1]) if c[i] > 0 and c[i - 1] > 0 else 0.0 for i in range(1, len(c))]


def _er(closes, **_):
    n = 20
    if len(closes) < n + 1:
        return float("nan")
    i = len(closes) - 1
    change = abs(closes[i] - closes[i - n])
    vol = sum(abs(closes[j] - closes[j - 1]) for j in range(i - n + 1, i + 1))
    er = change / vol if vol > 0 else 0.0
    return _clamp((er - 0.31) / 0.18, -1, 1)


def _adx(highs, lows, closes, **_):
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
        s = sum(arr[:n]); out[n - 1] = s
        for i in range(n, len(arr)):
            s = s - s / n + arr[i]; out[i] = s
        return out

    trS, pS, mS = smooth(tr), smooth(pDM), smooth(mDM)
    dx = []
    for i in range(n - 1, len(tr)):
        if not trS[i] or math.isnan(trS[i]):
            continue
        pdi = 100 * pS[i] / trS[i]; mdi = 100 * mS[i] / trS[i]
        ssum = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / ssum if ssum > 0 else 0.0)
    if len(dx) < n:
        return float("nan")
    adx = _mean(dx[:n])
    for i in range(n, len(dx)):
        adx = (adx * (n - 1) + dx[i]) / n
    return _clamp((adx - 22.5) / 17.5, -1, 1)


def _chop(highs, lows, closes, **_):
    n = 14
    L = len(closes)
    if L < n + 1:
        return float("nan")
    trSum = 0.0; hi, lo = -math.inf, math.inf
    for i in range(L - n, L):
        trSum += max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        hi = max(hi, highs[i]); lo = min(lo, lows[i])
    rng = hi - lo
    ci = 100 * math.log10(trSum / rng) / math.log10(n) if rng > 0 else 100.0
    return _clamp((50 - ci) / 15, -1, 1)


def _hurst(returns, **_):
    N = len(returns)
    if N < 40:
        return float("nan")
    sizes = []
    n = 8
    while n <= N // 2:
        sizes.append(n); n = int(n * 1.7)
    if len(sizes) < 3:
        return float("nan")
    xs, ys = [], []
    for n in sizes:
        chunks = N // n
        rsSum = 0.0; cnt = 0
        for c in range(chunks):
            seg = returns[c * n:(c + 1) * n]
            m = _mean(seg)
            dev = [v - m for v in seg]
            cum = 0.0; mn = math.inf; mx = -math.inf
            for dd in dev:
                cum += dd; mn = min(mn, cum); mx = max(mx, cum)
            R = mx - mn
            sd = math.sqrt(_mean([dd * dd for dd in dev]))
            if sd > 0 and R > 0:
                rsSum += R / sd; cnt += 1
        if cnt > 0:
            xs.append(math.log(n)); ys.append(math.log(rsSum / cnt))
    if len(xs) < 3:
        return float("nan")
    h = _ols_slope(xs, ys)
    return _clamp((h - 0.5) / 0.18, -1, 1) if math.isfinite(h) else float("nan")


def _vr(returns, **_):
    q = 4; N = len(returns)
    if N < q * 6:
        return float("nan")
    m = _mean(returns)
    v1 = sum((r - m) ** 2 for r in returns) / (N - 1)
    if v1 <= 0:
        return float("nan")
    s = 0.0
    for i in range(0, N - q + 1):
        ssum = sum(returns[i + j] for j in range(q))
        s += (ssum - q * m) ** 2
    mDen = q * (N - q + 1) * (1 - q / N)
    return _clamp(((s / mDen) / v1 - 1) / 0.35, -1, 1)


def _acf(returns, **_):
    N = len(returns)
    if N < 12:
        return float("nan")
    m = _mean(returns)
    num = den = 0.0
    for i in range(N):
        den += (returns[i] - m) ** 2
        if i > 0:
            num += (returns[i] - m) * (returns[i - 1] - m)
    rho = num / den if den > 0 else 0.0
    return _clamp(rho / 0.20, -1, 1)


_DETECTORS = [_er, _adx, _chop, _hurst, _vr, _acf]


def compute_score(kl_slice):
    """Ensemble score over a kline slice (Binance rows). nan if too short."""
    if len(kl_slice) < 40:
        return float("nan")
    s = kl_slice[-max(DETECTOR_WINDOW, 60):]
    highs = [float(k[2]) for k in s]
    lows = [float(k[3]) for k in s]
    closes = [float(k[4]) for k in s]
    ctx = dict(highs=highs, lows=lows, closes=closes, returns=_log_returns(closes))
    scores = []
    for d in _DETECTORS:
        try:
            v = d(**ctx)
        except Exception:
            v = float("nan")
        if isinstance(v, float) and math.isfinite(v):
            scores.append(v)
    return _mean(scores) if scores else float("nan")


def verdict(score):
    if not (isinstance(score, float) and math.isfinite(score)):
        return "transition"
    return "trend" if score >= 0.15 else ("range" if score <= -0.15 else "transition")


def build_rolling(klines, window=DETECTOR_WINDOW):
    """(openMs, score) per bar over its trailing window. Warm-up bars -> nan."""
    out = []
    for i in range(len(klines)):
        if i + 1 < MINBARS:
            out.append((int(klines[i][0]), float("nan")))
        else:
            out.append((int(klines[i][0]), compute_score(klines[max(0, i - window + 1):i + 1])))
    return out


def score_at(roll, fire_ms):
    """Causal score: the rolling score of the last 4h bar CLOSED at/before fire_ms."""
    lo, hi, idx = 0, len(roll) - 1, -1
    while lo <= hi:
        m = (lo + hi) >> 1
        if roll[m][0] + FOURH_MS <= fire_ms:
            idx = m; lo = m + 1
        else:
            hi = m - 1
    return roll[idx][1] if idx >= 0 else float("nan")
