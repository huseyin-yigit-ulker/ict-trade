// Intelligence (İstihbarat) — pure comparative analytics for the backtest streams.
// No React, no env, no fetch: feed it raw Supabase rows (ict_trade.trading_signals)
// and it returns everything the comparison surface renders. Kept framework-free so
// the metric math is unit-testable in isolation and reused across panels.
//
// The board compares the strategy VERSIONS that actually exist in the backtest DB.
// Today that is donchian (1h) and dch30_4h (30m breakout + 4h trend-direction confirm):
// shared 55-bar fresh-breakout + Kaufman ER>=0.35 core, ATR2 stop, RR4 full-TP. So every
// angle below is a like-for-like timeframe
// A/B, which is exactly what makes the head-to-head fair.

import { marketOf } from './symbolMeta';

// ---- Status classification (mirror of TradeContext.normalizeStatus, + OPEN) ----
// closed_tp/closed_sl -> realised R ; cancelled -> 0R no-fill ; active/pending -> OPEN
// (not yet resolved, excluded from every R metric).
export const classifyStatus = (status) => {
  const s = (status || '').toString().toLowerCase();
  if (s.includes('cancel')) return 'NOFILL';
  if (s.includes('tp')) return 'TP';
  if (s.includes('sl')) return 'SL';
  if (s.includes('active') || s.includes('pending') || s.includes('wait')) return 'OPEN';
  return 'OPEN';
};

const toMs = (v) => {
  if (!v) return null;
  const t = new Date(v).getTime();
  return Number.isNaN(t) ? null : t;
};
const toNum = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

// Raw row -> normalised trade. `version` is passed so a merged set stays labelled.
export const normalizeRows = (rows, version) => {
  if (!Array.isArray(rows)) return [];
  return rows
    .map((r) => {
      const signalTs = toMs(r.signal_time);
      if (signalTs == null) return null;
      const status = classifyStatus(r.status);
      const dirRaw = (r.direction || r.trade_type || '').toString().toUpperCase();
      const dir = dirRaw === 'BUY' || dirRaw === 'LONG' ? 'LONG' : 'SHORT';
      const entryTs = toMs(r.real_entry_time);
      const exitTs = toMs(r.exit_time);
      const r_ = toNum(r.pnl_r);
      const entry = toNum(r.entry_price);
      const sl = toNum(r.sl_price);
      // Per-trade risk as a fraction of entry — used by the cost/tempo lens.
      const riskFrac = entry && sl ? Math.abs(entry - sl) / entry : null;
      const closed = status === 'TP' || status === 'SL';
      const holdHrs = closed && entryTs && exitTs ? (exitTs - entryTs) / 3.6e6 : null;
      return {
        version: version ?? r.version ?? null,
        symbol: r.symbol,
        market: marketOf(r.symbol),
        dir,
        status,
        closed,
        r: closed ? (r_ ?? 0) : null,
        signalTs,
        entryTs,
        exitTs,
        // realisation timestamp for ordering the equity curve (fall back to signal)
        sortTs: exitTs ?? signalTs,
        riskFrac,
        holdHrs,
      };
    })
    .filter(Boolean);
};

const sum = (a) => a.reduce((x, y) => x + y, 0);
const closedOf = (trades) => trades.filter((t) => t.closed);

// Pearson correlation of two equal-length arrays.
const pearson = (xs, ys) => {
  const n = xs.length;
  if (n < 2) return null;
  const mx = sum(xs) / n;
  const my = sum(ys) / n;
  let sxy = 0;
  let sxx = 0;
  let syy = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    sxy += dx * dy;
    sxx += dx * dx;
    syy += dy * dy;
  }
  const den = Math.sqrt(sxx * syy);
  return den > 0 ? sxy / den : null;
};

// Cumulative-R path + drawdown over a list ordered ASC by realisation time.
// Equity starts at 0 (flat book), so the running peak is anchored at 0 — a path
// that opens below zero correctly counts its opening drawdown. maxDDDays is the
// longest peak-to-recovery underwater stretch (the recovery trade closes it).
const equityModel = (closed) => {
  const ordered = [...closed].sort((a, b) => a.sortTs - b.sortTs);
  const points = [];
  let cum = 0;
  let peak = 0;                          // starting equity = 0 (no position)
  let peakTs = ordered[0]?.sortTs ?? 0;
  let maxDD = 0;
  let maxDDDays = 0;
  let underwater = false;
  ordered.forEach((t) => {
    cum += t.r;
    if (cum >= peak) {
      // back at/above the high-water mark — close any open underwater stretch
      if (underwater) {
        const dur = (t.sortTs - peakTs) / 8.64e7;
        if (dur > maxDDDays) maxDDDays = dur;
        underwater = false;
      }
      peak = cum;
      peakTs = t.sortTs;
    } else {
      underwater = true;
      const dur = (t.sortTs - peakTs) / 8.64e7;   // days since the last high
      if (dur > maxDDDays) maxDDDays = dur;
    }
    const dd = peak - cum;
    if (dd > maxDD) maxDD = dd;
    points.push({ ts: t.sortTs, cum, peak });
  });
  return { points, total: cum, peak, maxDD, maxDDDays };
};

// Longest run of wins / losses, ordered by realisation time.
const streaks = (closed) => {
  const ordered = [...closed].sort((a, b) => a.sortTs - b.sortTs);
  let win = 0;
  let loss = 0;
  let maxWin = 0;
  let maxLoss = 0;
  ordered.forEach((t) => {
    if (t.r > 0) {
      win += 1;
      loss = 0;
    } else {
      loss += 1;
      win = 0;
    }
    if (win > maxWin) maxWin = win;
    if (loss > maxLoss) maxLoss = loss;
  });
  return { maxWin, maxLoss };
};

// Map 'YYYY-MM-DD' (UTC) -> net R that day (closed trades only).
export const dailyNetR = (trades) => {
  const m = new Map();
  closedOf(trades).forEach((t) => {
    const d = new Date(t.sortTs);
    const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(
      d.getUTCDate(),
    ).padStart(2, '0')}`;
    m.set(key, (m.get(key) || 0) + t.r);
  });
  return m;
};

// Group closed trades by a key function -> { key, n, tp, sl, wr, r, avgR }.
const groupBy = (closed, keyFn) => {
  const m = new Map();
  closed.forEach((t) => {
    const k = keyFn(t);
    const e = m.get(k) || { key: k, n: 0, tp: 0, sl: 0, r: 0 };
    e.n += 1;
    if (t.r > 0) e.tp += 1;
    else e.sl += 1;
    e.r += t.r;
    m.set(k, e);
  });
  return [...m.values()].map((e) => ({ ...e, wr: e.n ? (e.tp / e.n) * 100 : 0, avgR: e.n ? e.r / e.n : 0 }));
};

// The full single-stream metric bundle.
export const bundle = (trades) => {
  const closed = closedOf(trades);
  const n = trades.length;
  const nofill = trades.filter((t) => t.status === 'NOFILL').length;
  const open = trades.filter((t) => t.status === 'OPEN').length;
  const wins = closed.filter((t) => t.r > 0);
  const losses = closed.filter((t) => t.r <= 0);
  const grossWin = sum(wins.map((t) => t.r));
  const grossLoss = Math.abs(sum(losses.map((t) => t.r)));
  const totalR = grossWin - grossLoss;
  const closedN = closed.length;
  const avgR = closedN ? totalR / closedN : 0;
  const rs = closed.map((t) => t.r);
  const mean = avgR;
  const variance = closedN > 1 ? sum(rs.map((r) => (r - mean) ** 2)) / (closedN - 1) : 0;
  const stdR = Math.sqrt(variance);
  const eq = equityModel(closed);
  const st = streaks(closed);
  // top-5 winners' share of gross profit — the fragility / tail-dependence read.
  const topWins = [...wins].sort((a, b) => b.r - a.r);
  const top5 = topWins.slice(0, 5);
  const top5Share = grossWin > 0 ? (sum(top5.map((t) => t.r)) / grossWin) * 100 : 0;
  // hold time
  const holds = closed.map((t) => t.holdHrs).filter((h) => h != null);
  const winHolds = wins.map((t) => t.holdHrs).filter((h) => h != null);
  const lossHolds = losses.map((t) => t.holdHrs).filter((h) => h != null);
  const avg = (a) => (a.length ? sum(a) / a.length : null);
  // signal tempo: trades per 30 days over the realised span
  const span = closed.length
    ? (Math.max(...closed.map((t) => t.sortTs)) - Math.min(...closed.map((t) => t.sortTs))) / 8.64e7
    : 0;
  const perMonth = span > 0 ? (closedN / span) * 30 : 0;
  const avgRiskFrac = avg(trades.map((t) => t.riskFrac).filter((x) => x != null));
  // capital-time in market (days) → R per day-in-market = capital efficiency
  const exposureDays = sum(holds) / 24;
  // Σ(1/riskFrac) over closed trades: an extra slippage of `s` (price-fraction, per
  // side) costs (2·s)·invRiskSum total R — the cost-sensitivity stress lever.
  const invRiskSum = sum(closed.map((t) => (t.riskFrac ? 1 / t.riskFrac : 0)));

  return {
    n,
    closedN,
    open,
    nofill,
    tp: wins.length,
    sl: losses.length,
    winRate: closedN ? (wins.length / closedN) * 100 : 0,
    totalR,
    avgR,
    grossWin,
    grossLoss,
    profitFactor: grossLoss > 0 ? grossWin / grossLoss : null,
    avgWin: wins.length ? grossWin / wins.length : 0,
    avgLoss: losses.length ? grossLoss / losses.length : 0,
    payoff: losses.length && wins.length ? grossWin / wins.length / (grossLoss / losses.length) : null,
    stdR,
    // per-trade reward/variability ratio — a Sharpe-like read on consistency
    rPerStd: stdR > 0 ? avgR / stdR : null,
    maxDD: eq.maxDD,
    maxDDDays: eq.maxDDDays,
    peak: eq.peak,
    recovery: eq.maxDD > 0 ? totalR / eq.maxDD : null,
    bestR: rs.length ? Math.max(...rs) : 0,
    worstR: rs.length ? Math.min(...rs) : 0,
    maxWinStreak: st.maxWin,
    maxLossStreak: st.maxLoss,
    top5Share,
    cancelRate: n ? (nofill / n) * 100 : 0,
    avgHoldHrs: avg(holds),
    avgWinHoldHrs: avg(winHolds),
    avgLossHoldHrs: avg(lossHolds),
    perMonth,
    avgRiskFrac,
    exposureDays,
    rPerExposureDay: exposureDays > 0 ? totalR / exposureDays : null,
    invRiskSum,
    equity: eq.points,
    spanDays: span,
  };
};

// Per-symbol R for both streams, joined and sorted by combined |R| (the head-to-head).
export const symbolCompare = (aTrades, bTrades) => {
  const ga = new Map(groupBy(closedOf(aTrades), (t) => t.symbol).map((e) => [e.key, e]));
  const gb = new Map(groupBy(closedOf(bTrades), (t) => t.symbol).map((e) => [e.key, e]));
  const syms = new Set([...ga.keys(), ...gb.keys()]);
  return [...syms]
    .map((sym) => {
      const a = ga.get(sym);
      const b = gb.get(sym);
      return {
        symbol: sym,
        market: marketOf(sym),
        aR: a?.r ?? 0,
        bR: b?.r ?? 0,
        aN: a?.n ?? 0,
        bN: b?.n ?? 0,
        aWr: a?.wr ?? 0,
        bWr: b?.wr ?? 0,
      };
    })
    .sort((x, y) => Math.max(Math.abs(y.aR), Math.abs(y.bR)) - Math.max(Math.abs(x.aR), Math.abs(x.bR)));
};

// Generic A/B breakdown over a categorical key (market / direction / weekday / hour / month).
export const categoryCompare = (aTrades, bTrades, keyFn, order) => {
  const ga = new Map(groupBy(closedOf(aTrades), keyFn).map((e) => [e.key, e]));
  const gb = new Map(groupBy(closedOf(bTrades), keyFn).map((e) => [e.key, e]));
  const keys = order || [...new Set([...ga.keys(), ...gb.keys()])].sort();
  return keys.map((k) => {
    const a = ga.get(k);
    const b = gb.get(k);
    return {
      key: k,
      aR: a?.r ?? 0,
      bR: b?.r ?? 0,
      aN: a?.n ?? 0,
      bN: b?.n ?? 0,
      aWr: a?.wr ?? 0,
      bWr: b?.wr ?? 0,
    };
  });
};

export const WEEKDAYS = ['Pazartesi', 'Sali', 'Carsamba', 'Persembe', 'Cuma', 'Cumartesi', 'Pazar'];
// ISO weekday (1=Mon..7=Sun) from a UTC ts.
const isoWeekday = (ts) => {
  const d = new Date(ts).getUTCDay(); // 0=Sun..6=Sat
  return d === 0 ? 7 : d;
};
export const weekdayKey = (t) => WEEKDAYS[isoWeekday(t.signalTs) - 1];
export const hourKey = (t) => new Date(t.signalTs).getUTCHours();
// Calendar attribution keys off the SIGNAL date (matches yearKey, the signal-time
// window filter, and the app's per-period DB aggregates). The equity/blend curves
// stay on realisation (sortTs) for correct drawdown ordering.
export const monthKey = (t) => {
  const d = new Date(t.signalTs);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};
export const yearKey = (t) => String(new Date(t.signalTs).getUTCFullYear());

// Daily-R cumulative recovery (total / maxDD) over a date->R map, peak anchored at
// the 0 starting equity. Used so the per-stream recovery compared against the blend
// is computed on the SAME daily granularity (apples-to-apples).
const dailyRecovery = (map) => {
  const ks = [...map.keys()].sort();
  let cum = 0;
  let peak = 0;
  let maxDD = 0;
  ks.forEach((k) => {
    cum += map.get(k);
    if (cum > peak) peak = cum;
    if (peak - cum > maxDD) maxDD = peak - cum;
  });
  return { total: cum, maxDD, recovery: maxDD > 0 ? cum / maxDD : null };
};

// Cross-stream diversification: daily-R correlation + the "run BOTH books" blend.
// Low correlation + a blend whose recovery factor beats either alone == the streams
// complement rather than substitute (the whole point of a timeframe ensemble).
export const diversification = (aTrades, bTrades) => {
  const da = dailyNetR(aTrades);
  const db = dailyNetR(bTrades);
  const days = [...new Set([...da.keys(), ...db.keys()])].sort();
  const xs = days.map((d) => da.get(d) || 0);
  const ys = days.map((d) => db.get(d) || 0);
  const corr = pearson(xs, ys);
  // Both books run together: per-day combined R, accumulated over the shared calendar.
  let cum = 0;
  let peak = 0;                          // starting equity = 0
  let maxDD = 0;
  const blendEq = days.map((d) => {
    cum += (da.get(d) || 0) + (db.get(d) || 0);
    if (cum > peak) peak = cum;
    if (peak - cum > maxDD) maxDD = peak - cum;
    const [yy, mm, dd] = d.split('-').map(Number);
    return { ts: Date.UTC(yy, mm - 1, dd), cum, peak };
  });
  const total = cum;
  // overlap: days where BOTH books traded (concurrency of the two timeframes)
  const bothDays = days.filter((d) => da.has(d) && db.has(d)).length;
  const ar = dailyRecovery(da);
  const br = dailyRecovery(db);
  return {
    corr,
    days: days.length,
    bothDays,
    blendEq,
    blendTotal: total,
    blendMaxDD: maxDD,
    blendRecovery: maxDD > 0 ? total / maxDD : null,
    // per-stream daily recovery (same granularity as the blend, for a fair verdict)
    aRecovery: ar.recovery,
    bRecovery: br.recovery,
  };
};

// ---- window / market filters (UI controls) ----
export const COMMON_FROM = Date.UTC(2026, 0, 1); // both streams overlap from 2026-01-01
export const filterWindow = (trades, fromTs, toTs) =>
  trades.filter((t) => (fromTs == null || t.signalTs >= fromTs) && (toTs == null || t.signalTs <= toTs));
export const filterMarket = (trades, market) =>
  market === 'all' ? trades : trades.filter((t) => t.market === market);
