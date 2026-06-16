// REGIME DETECTORS — independent "trend vs range" classifiers, each grounded in a
// different strand of the literature, combined into one ensemble verdict.
//
// The core statistical question is the autocorrelation structure of returns:
//   positive autocorrelation → momentum / TREND      (persistent)
//   ~zero autocorrelation    → random walk           (unpredictable)
//   negative autocorrelation → mean-reversion / RANGE (anti-persistent)
//
// Each detector measures this from a different angle and reports a result on a
// unified TREND(+1) ↔ RANGE(−1) axis (≈0 = random). They are deliberately kept
// as separate sub-modules so the UI can show them side-by-side AND aggregate them
// — no single method is "the" answer (regime is scale-dependent and only clear
// in-sample; real-time reads lag). Pure module: no React, no network.

export const DETECTOR_WINDOW = 150;   // ~25 days of 4h bars for the "current" snapshot

// Unified trend↔range states (shared colours across the whole regime module).
export const TREND_RANGE = {
  trend:      { key: 'trend',      label: 'Trend', color: '#0ECB81' },
  range:      { key: 'range',      label: 'Range', color: '#5C93FF' },
  transition: { key: 'transition', label: 'Geçiş', color: '#848E9C' },
};
export const TREND_RANGE_LIST = [TREND_RANGE.trend, TREND_RANGE.transition, TREND_RANGE.range];

// Ensemble mean-score → verdict (±0.15 dead-zone around random walk).
export const verdictOf = (score) =>
  !Number.isFinite(score) ? TREND_RANGE.transition
    : score >= 0.15 ? TREND_RANGE.trend
      : score <= -0.15 ? TREND_RANGE.range
        : TREND_RANGE.transition;

// ---------------------------------------------------------------- small math --
const mean = (a) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const olsSlope = (xs, ys) => {
  const mx = mean(xs); const my = mean(ys);
  let num = 0; let den = 0;
  for (let i = 0; i < xs.length; i += 1) { num += (xs[i] - mx) * (ys[i] - my); den += (xs[i] - mx) ** 2; }
  return den > 0 ? num / den : NaN;
};
const logReturns = (c) => {
  const r = [];
  for (let i = 1; i < c.length; i += 1) r.push(c[i] > 0 && c[i - 1] > 0 ? Math.log(c[i] / c[i - 1]) : 0);
  return r;
};

// ----------------------------------------------------------------- detectors --
// Each compute(ctx) returns { value, score(−1..1), state, display } or null.
// ctx = { highs, lows, closes, returns } over the snapshot window.

// 1) Kaufman Efficiency Ratio — net move / total path. 1 = clean trend, 0 = noise.
const erDetector = {
  key: 'er', cat: 'technical', label: 'Efficiency Ratio',
  note: 'Net hareket / toplam yol — 1’e yakın temiz trend, 0’a yakın gürültü/range.',
  compute({ closes }) {
    const n = 20;
    if (closes.length < n + 1) return null;
    const i = closes.length - 1;
    const change = Math.abs(closes[i] - closes[i - n]);
    let vol = 0; for (let j = i - n + 1; j <= i; j += 1) vol += Math.abs(closes[j] - closes[j - 1]);
    const er = vol > 0 ? change / vol : 0;
    return { value: er, score: clamp((er - 0.31) / 0.18, -1, 1),
      state: er >= 0.40 ? 'trend' : er <= 0.22 ? 'range' : 'transition', display: er.toFixed(2) };
  },
};

// 2) ADX (Wilder) — directional-movement strength, regardless of direction.
const adxDetector = {
  key: 'adx', cat: 'technical', label: 'ADX',
  note: 'Wilder yönsel hareket endeksi. ≥25 trend, <20 yatay/range.',
  compute({ highs, lows, closes }) {
    const n = 14; const len = closes.length;
    if (len < 3 * n) return null;
    const tr = []; const pDM = []; const mDM = [];
    for (let i = 1; i < len; i += 1) {
      const up = highs[i] - highs[i - 1];
      const dn = lows[i - 1] - lows[i];
      pDM.push(up > dn && up > 0 ? up : 0);
      mDM.push(dn > up && dn > 0 ? dn : 0);
      tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
    }
    // Wilder running sum (seeded with the first n-sum)
    const smooth = (arr) => {
      const out = new Array(arr.length).fill(NaN);
      let s = 0; for (let i = 0; i < n; i += 1) s += arr[i];
      out[n - 1] = s;
      for (let i = n; i < arr.length; i += 1) { s = s - s / n + arr[i]; out[i] = s; }
      return out;
    };
    const trS = smooth(tr); const pS = smooth(pDM); const mS = smooth(mDM);
    const dx = [];
    for (let i = n - 1; i < tr.length; i += 1) {
      if (!trS[i]) { continue; }
      const pdi = 100 * pS[i] / trS[i]; const mdi = 100 * mS[i] / trS[i];
      const sum = pdi + mdi;
      dx.push(sum > 0 ? 100 * Math.abs(pdi - mdi) / sum : 0);
    }
    if (dx.length < n) return null;
    let adx = mean(dx.slice(0, n));
    for (let i = n; i < dx.length; i += 1) adx = (adx * (n - 1) + dx[i]) / n;
    return { value: adx, score: clamp((adx - 22.5) / 17.5, -1, 1),
      state: adx >= 25 ? 'trend' : adx < 20 ? 'range' : 'transition', display: adx.toFixed(0) };
  },
};

// 3) Choppiness Index — high = sideways/range, low = trend.
const chopDetector = {
  key: 'chop', cat: 'technical', label: 'Choppiness',
  note: 'Choppiness Index. ≥61.8 yatay/range, ≤38.2 trend.',
  compute({ highs, lows, closes }) {
    const n = 14; const len = closes.length;
    if (len < n + 1) return null;
    let trSum = 0; let hi = -Infinity; let lo = Infinity;
    for (let i = len - n; i < len; i += 1) {
      trSum += Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1]));
      hi = Math.max(hi, highs[i]); lo = Math.min(lo, lows[i]);
    }
    const range = hi - lo;
    const ci = range > 0 ? 100 * Math.log10(trSum / range) / Math.log10(n) : 100;
    return { value: ci, score: clamp((50 - ci) / 15, -1, 1),
      state: ci <= 38.2 ? 'trend' : ci >= 61.8 ? 'range' : 'transition', display: ci.toFixed(0) };
  },
};

// 4) Hurst exponent (R/S analysis) on returns — H>0.5 persistent/trend, H<0.5
//    anti-persistent/mean-reverting, H≈0.5 random walk.
const hurstDetector = {
  key: 'hurst', cat: 'statistical', label: 'Hurst Üsteli',
  note: 'R/S analizi (getiriler). H>0.5 kalıcı/trend, H<0.5 ortalamaya dönüş, ≈0.5 rastgele.',
  compute({ returns }) {
    const N = returns.length;
    if (N < 40) return null;
    const sizes = [];
    for (let n = 8; n <= Math.floor(N / 2); n = Math.floor(n * 1.7)) sizes.push(n);
    if (sizes.length < 3) return null;
    const xs = []; const ys = [];
    for (const n of sizes) {
      const chunks = Math.floor(N / n);
      let rsSum = 0; let cnt = 0;
      for (let c = 0; c < chunks; c += 1) {
        const seg = returns.slice(c * n, (c + 1) * n);
        const m = mean(seg);
        const dev = seg.map((v) => v - m);
        let cum = 0; let mn = Infinity; let mx = -Infinity;
        for (const dd of dev) { cum += dd; mn = Math.min(mn, cum); mx = Math.max(mx, cum); }
        const R = mx - mn;
        const sd = Math.sqrt(mean(dev.map((dd) => dd * dd)));
        if (sd > 0 && R > 0) { rsSum += R / sd; cnt += 1; }
      }
      if (cnt > 0) { xs.push(Math.log(n)); ys.push(Math.log(rsSum / cnt)); }
    }
    if (xs.length < 3) return null;
    const h = olsSlope(xs, ys);
    if (!Number.isFinite(h)) return null;
    return { value: h, score: clamp((h - 0.5) / 0.18, -1, 1),
      state: h >= 0.55 ? 'trend' : h <= 0.45 ? 'range' : 'transition', display: h.toFixed(2) };
  },
};

// 5) Variance Ratio (Lo & MacKinlay 1988), q=4, overlapping + bias-corrected.
//    VR>1 → positive autocorrelation (trend), VR<1 → mean-reversion (range).
const vrDetector = {
  key: 'vr', cat: 'statistical', label: 'Varyans Oranı',
  note: 'Lo–MacKinlay VR(4). >1 momentum/trend, <1 ortalamaya dönüş, =1 rastgele yürüyüş.',
  compute({ returns }) {
    const q = 4; const N = returns.length;
    if (N < q * 6) return null;
    const m = mean(returns);
    let v1 = 0; for (const r of returns) v1 += (r - m) ** 2; v1 /= (N - 1);
    if (v1 <= 0) return null;
    let s = 0;
    for (let i = 0; i <= N - q; i += 1) {
      let sum = 0; for (let j = 0; j < q; j += 1) sum += returns[i + j];
      s += (sum - q * m) ** 2;
    }
    const mDen = q * (N - q + 1) * (1 - q / N);   // bias-corrected, q-normalised
    const vr = (s / mDen) / v1;
    return { value: vr, score: clamp((vr - 1) / 0.35, -1, 1),
      state: vr >= 1.15 ? 'trend' : vr <= 0.85 ? 'range' : 'transition', display: vr.toFixed(2) };
  },
};

// 6) Lag-1 autocorrelation of returns — the foundational read: + momentum, − mean-reversion.
const acfDetector = {
  key: 'acf', cat: 'statistical', label: 'Otokorelasyon (lag-1)',
  note: 'Getiri lag-1 otokorelasyonu. Pozitif → momentum/trend, negatif → ortalamaya dönüş/range.',
  compute({ returns }) {
    const N = returns.length;
    if (N < 12) return null;
    const m = mean(returns);
    let num = 0; let den = 0;
    for (let i = 0; i < N; i += 1) { den += (returns[i] - m) ** 2; if (i > 0) num += (returns[i] - m) * (returns[i - 1] - m); }
    const rho = den > 0 ? num / den : 0;
    return { value: rho, score: clamp(rho / 0.20, -1, 1),
      state: rho >= 0.08 ? 'trend' : rho <= -0.08 ? 'range' : 'transition', display: rho.toFixed(2) };
  },
};

export const DETECTORS = [erDetector, adxDetector, chopDetector, hurstDetector, vrDetector, acfDetector];
export const DETECTOR_CATS = [
  { key: 'technical', label: 'Teknik Göstergeler' },
  { key: 'statistical', label: 'İstatistiksel' },
];

// Run every detector over the snapshot window of a kline array (Binance rows:
// [openTime, o, h, l, c, …]) and aggregate to an ensemble trend↔range verdict.
export const computeRegime = (klines, window = DETECTOR_WINDOW) => {
  if (!Array.isArray(klines) || klines.length < 40) return null;
  const slice = klines.slice(-Math.max(window, 60));
  const highs = slice.map((k) => Number(k[2]));
  const lows = slice.map((k) => Number(k[3]));
  const closes = slice.map((k) => Number(k[4]));
  const returns = logReturns(closes);
  const ctx = { highs, lows, closes, returns };
  const detectors = DETECTORS.map((d) => {
    let r = null;
    try { r = d.compute(ctx); } catch { r = null; }
    return r
      ? { key: d.key, cat: d.cat, label: d.label, note: d.note, ...r }
      : { key: d.key, cat: d.cat, label: d.label, note: d.note, value: NaN, score: NaN, state: 'transition', display: '—' };
  });
  const scores = detectors.map((d) => d.score).filter(Number.isFinite);
  const score = scores.length ? mean(scores) : NaN;
  const votes = { trend: 0, range: 0, transition: 0 };
  detectors.forEach((d) => { if (Number.isFinite(d.score)) votes[d.state] += 1; });
  return { detectors, score, votes, verdict: verdictOf(score), n: closes.length };
};

// ROLLING regime over a whole kline history — the ensemble score/verdict computed
// at EVERY bar over its trailing window, so the chart can paint how trend↔range
// evolved across 2026 (a "regime backtest"). Returns one entry per bar aligned to
// klines[i]; the first ~minBars are warm-up (NaN score, transition). step>1 thins
// the heavy recompute and forward-fills the gaps.
export const rollingRegime = (klines, window = DETECTOR_WINDOW, step = 1) => {
  const out = [];
  if (!Array.isArray(klines)) return out;
  const minBars = 60;
  for (let i = 0; i < klines.length; i += 1) {
    const time = Math.floor(Number(klines[i][0]) / 1000);
    if (i + 1 < minBars) { out.push({ time, score: NaN, verdict: TREND_RANGE.transition }); continue; }
    if (step > 1 && i % step !== 0 && out.length) {
      const prev = out[out.length - 1];
      out.push({ time, score: prev.score, verdict: prev.verdict });
      continue;
    }
    const reg = computeRegime(klines.slice(Math.max(0, i - window + 1), i + 1), window);
    out.push(reg ? { time, score: reg.score, verdict: reg.verdict } : { time, score: NaN, verdict: TREND_RANGE.transition });
  }
  return out;
};
