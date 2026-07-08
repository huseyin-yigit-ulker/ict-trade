import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts';
import { useStreamDisplay } from '../utils/useStreamDisplay';

// Standalone LIVE chart for MIDAS (XAUUSDT 1m) — NOT tied to a trade. Draws the exact metrics the
// signal logic (sync/midas/strategy.signals) keys off, recomputed live every 30s:
//   • anchored VWAP (reset 18:00 ET / FX-day)  — the trend reference  (validated == backend)
//   • ±0.25·ATR(15m) pullback band around VWAP  — the "touched VWAP" trigger zone
//   • LONG/SHORT markers where the core rule fires (close vs VWAP + VWAP-slope + pullback + bar dir,
//     London 07-13 UTC skipped) — same conditions as the backend (market-hours filter approximate).
// variant='talos': same shell, but the reference metric is the 15m Keltner channel
// (EMA20 midline, ±0.75x ATR(20,15m) bands; trend = 4-bar EMA slope) — mirrors sync/talos/strategy.
const SYMBOL = 'XAUUSDT';
const SLOPE_N = 60, ATR_N = 14, TOUCH_TOL = 0.25, ATR_INIT = 1.5, SKIP_START = 7, SKIP_END = 13;
const K_EMA_N = 20, K_MULT = 0.75, K_SLOPE_BARS = 4;   // TALOS Keltner params (15m)

// UTC ms of the most recent 18:00 America/New_York at/before ms — the FX session open / VWAP anchor.
// Scans back hour-by-hour so it's DST-correct.
const fxAnchorMs = (ms) => {
  const etHour = (t) => parseInt(new Intl.DateTimeFormat('en-US',
    { timeZone: 'America/New_York', hour12: false, hour: '2-digit' }).format(new Date(t)), 10) % 24;
  let t = ms - (ms % 3600000);
  for (let i = 0; i < 26; i += 1) { if (etHour(t) === 18) return t; t -= 3600000; }
  return ms - 24 * 3600000;
};
const fxDayKey = (timeSec) => new Intl.DateTimeFormat('en-CA',
  { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' })
  .format(new Date(timeSec * 1000 - 18 * 3600000));

// ATR(14) on 15m buckets (EWM alpha=1/14), mapped back to each 1m bar. Approximate (left-labelled
// buckets) — a visual band, not the exact resampled backend value.
const atr15 = (candles) => {
  const buckets = []; let cur = null;
  for (const c of candles) {
    const b = Math.floor(c.time / 900) * 900;
    if (!cur || cur.t !== b) { if (cur) buckets.push(cur); cur = { t: b, h: c.high, l: c.low, c: c.close }; }
    else { cur.h = Math.max(cur.h, c.high); cur.l = Math.min(cur.l, c.low); cur.c = c.close; }
  }
  if (cur) buckets.push(cur);
  const alpha = 1 / ATR_N; let atr = null; const byBucket = new Map();
  for (let i = 0; i < buckets.length; i += 1) {
    const b = buckets[i]; const pc = i > 0 ? buckets[i - 1].c : b.c;
    const tr = Math.max(b.h - b.l, Math.abs(b.h - pc), Math.abs(b.l - pc));
    atr = atr == null ? tr : atr + alpha * (tr - atr);
    byBucket.set(b.t, atr);
  }
  return candles.map((c) => byBucket.get(Math.floor(c.time / 900) * 900));
};

// 15m Keltner (EMA20 midline, ATR20 band, 4-bar slope) mapped back to each 1m bar — the TALOS
// reference metric. Left-labelled buckets like atr15 (visual; backend uses right-closed resample).
const keltner15 = (candles) => {
  const buckets = []; let cur = null;
  for (const c of candles) {
    const b = Math.floor(c.time / 900) * 900;
    if (!cur || cur.t !== b) { if (cur) buckets.push(cur); cur = { t: b, h: c.high, l: c.low, c: c.close }; }
    else { cur.h = Math.max(cur.h, c.high); cur.l = Math.min(cur.l, c.low); cur.c = c.close; }
  }
  if (cur) buckets.push(cur);
  const aE = 2 / (K_EMA_N + 1); const aA = 1 / K_EMA_N;
  let ema = null; let katr = null;
  const emaArr = []; const byBucket = new Map();
  for (let i = 0; i < buckets.length; i += 1) {
    const b = buckets[i]; const pc = i > 0 ? buckets[i - 1].c : b.c;
    const tr = Math.max(b.h - b.l, Math.abs(b.h - pc), Math.abs(b.l - pc));
    ema = ema == null ? b.c : ema + aE * (b.c - ema);
    katr = katr == null ? tr : katr + aA * (tr - katr);
    emaArr.push(ema);
    const slope = i >= K_SLOPE_BARS ? ema - emaArr[i - K_SLOPE_BARS] : NaN;
    byBucket.set(b.t, { ema, katr, slope });
  }
  return candles.map((c) => byBucket.get(Math.floor(c.time / 900) * 900));
};

// TALOS: midline = 15m EMA20 (ref line), band = EMA ± 0.75·ATR(20,15m); LONG fires on a deep dip
// to the LOWER band (low ≤ band+0.25·ATR15) reclaimed with a bullish close (sync/talos/strategy).
const computeTalos = (candles) => {
  const k = keltner15(candles);
  const a = atr15(candles);
  const refData = []; const bandU = []; const bandL = []; const markers = [];
  for (let i = 0; i < candles.length; i += 1) {
    const c = candles[i]; const kk = k[i];
    if (!kk || !Number.isFinite(kk.ema)) continue;
    const bLo = kk.ema - K_MULT * kk.katr; const bHi = kk.ema + K_MULT * kk.katr;
    refData.push({ time: c.time, value: kk.ema });
    bandU.push({ time: c.time, value: bHi }); bandL.push({ time: c.time, value: bLo });
    const utch = new Date(c.time * 1000).getUTCHours();
    const sessOk = !(utch >= SKIP_START && utch < SKIP_END);
    if (Number.isFinite(a[i]) && a[i] > 0 && Number.isFinite(kk.slope) && sessOk) {
      const tol = TOUCH_TOL * a[i];
      if (kk.slope > 0 && c.close > bLo && c.low <= bLo + tol && c.close > c.open) {
        markers.push({ time: c.time, position: 'belowBar', shape: 'arrowUp', color: '#0ECB81', text: 'AL', size: 1 });
      } else if (kk.slope < 0 && c.close < bHi && c.high >= bHi - tol && c.close < c.open) {
        markers.push({ time: c.time, position: 'aboveBar', shape: 'arrowDown', color: '#F6465D', text: 'SAT', size: 1 });
      }
    }
  }
  const i = candles.length - 1;
  const lb = candles[i]; const kk = k[i] || {}; const aa = a[i];
  const bLo = kk.ema - K_MULT * kk.katr; const bHi = kk.ema + K_MULT * kk.katr;
  const tol = Number.isFinite(aa) ? TOUCH_TOL * aa : NaN;
  const utch = new Date(lb.time * 1000).getUTCHours();
  const cond = {
    sessOk: !(utch >= SKIP_START && utch < SKIP_END),
    above: lb.close > bLo, below: lb.close < bHi,
    slopeUp: kk.slope > 0, slopeDn: kk.slope < 0,
    pullLong: lb.low <= bLo + tol, pullShort: lb.high >= bHi - tol,
    bull: lb.close > lb.open, bear: lb.close < lb.open,
  };
  const last = { price: lb.close, ref: kk.ema, slope: kk.slope, atr: aa, tol, cond, time: lb.time };
  return { refData, bandU, bandL, markers, last };
};

const compute = (candles) => {
  let curDay = null; let cumPV = 0; let cumV = 0;
  const vw = candles.map((c) => {
    const day = fxDayKey(c.time);
    if (day !== curDay) { curDay = day; cumPV = 0; cumV = 0; }
    const tp = (c.high + c.low + c.close) / 3; const v = c.volume > 0 ? c.volume : 1;
    cumPV += tp * v; cumV += v; return cumPV / cumV;
  });
  const a = atr15(candles);
  const slope = candles.map((c, i) => (i >= SLOPE_N ? vw[i] - vw[i - SLOPE_N] : NaN));
  const refData = []; const bandU = []; const bandL = []; const markers = [];
  for (let i = 0; i < candles.length; i += 1) {
    const c = candles[i]; const v = vw[i];
    refData.push({ time: c.time, value: v });
    if (Number.isFinite(a[i])) { const tol = TOUCH_TOL * a[i]; bandU.push({ time: c.time, value: v + tol }); bandL.push({ time: c.time, value: v - tol }); }
    const utch = new Date(c.time * 1000).getUTCHours();
    const sessOk = !(utch >= SKIP_START && utch < SKIP_END);
    if (i > SLOPE_N && Number.isFinite(a[i]) && a[i] > 0 && sessOk) {
      const tol = TOUCH_TOL * a[i];
      if (c.close > v && slope[i] > 0 && c.low <= v + tol && c.close > c.open) {
        markers.push({ time: c.time, position: 'belowBar', shape: 'arrowUp', color: '#0ECB81', text: 'AL', size: 1 });
      } else if (c.close < v && slope[i] < 0 && c.high >= v - tol && c.close < c.open) {
        markers.push({ time: c.time, position: 'aboveBar', shape: 'arrowDown', color: '#F6465D', text: 'SAT', size: 1 });
      }
    }
  }
  const i = candles.length - 1;
  const lb = candles[i]; const v = vw[i]; const aa = a[i]; const slp = slope[i];
  const tol = Number.isFinite(aa) ? TOUCH_TOL * aa : NaN;
  const utch = new Date(lb.time * 1000).getUTCHours();
  const cond = {
    sessOk: !(utch >= SKIP_START && utch < SKIP_END),
    above: lb.close > v, below: lb.close < v,
    slopeUp: slp > 0, slopeDn: slp < 0,
    pullLong: lb.low <= v + tol, pullShort: lb.high >= v - tol,
    bull: lb.close > lb.open, bear: lb.close < lb.open,
  };
  const last = { price: lb.close, ref: v, slope: slp, atr: aa, tol, cond, time: lb.time };
  return { refData, bandU, bandL, markers, last };
};

// When a `trades` list is given (backtest day): HIGHLIGHT the signals that actually OPENED a trade —
// bright arrow + "AL/SAT ±R" at the trade's signal bar — while the other clustered signal-formation
// markers are dimmed (still visible, but muted). Without trades, returns the core markers unchanged.
const highlightMarkers = (coreMarkers, trades, candles) => {
  if (!trades || !trades.length || !candles.length) return coreMarkers;
  const times = candles.map((c) => c.time);
  const t0 = times[0]; const t1 = times[times.length - 1];
  const inWin = (ms) => Number.isFinite(ms) && ms / 1000 >= t0 - 60 && ms / 1000 <= t1 + 60;
  const snap = (ms) => {                                   // nearest candle bar at/before a timestamp
    const target = Math.floor(ms / 60000) * 60;
    let best = times[0];
    for (const tt of times) { if (tt <= target) best = tt; else break; }
    return best;
  };
  const entryBars = new Set();
  const hi = [];
  for (const tr of trades) {
    const r = Number(tr.r); const long = tr.direction === 'long';
    if (inWin(tr.signalMs)) {                              // ENTRY: amber arrow "AL"/"SAT" at the signal bar
      const bar = snap(tr.signalMs); entryBars.add(bar);
      hi.push({ time: bar, position: long ? 'belowBar' : 'aboveBar', shape: long ? 'arrowUp' : 'arrowDown',
        size: 2, color: '#F0B90B', text: long ? 'AL' : 'SAT' });
    }
    if (inWin(tr.exitMs)) {                                // EXIT: result-coloured circle "Çıkış ±R"
      hi.push({ time: snap(tr.exitMs), position: long ? 'aboveBar' : 'belowBar', shape: 'circle', size: 1,
        color: Number.isFinite(r) && r < 0 ? '#F6465D' : '#0ECB81',
        text: `Çıkış${Number.isFinite(r) ? ` ${r >= 0 ? '+' : ''}${r.toFixed(2)}R` : ''}` });
    }
  }
  const dim = coreMarkers.filter((m) => !entryBars.has(m.time)).map((m) => ({
    ...m, size: 1, text: undefined,
    color: m.color === '#0ECB81' ? 'rgba(14,203,129,0.28)' : 'rgba(246,70,93,0.26)',
  }));
  return [...dim, ...hi];
};

// Live (default): anchor→now, polls every 30s. Static (startMs+endMs given): a fixed historical day
// window (e.g. a backtest day), no polling — same VWAP/band/markers, fit to the whole window.
export default function MidasLiveChart({ variant = 'midas', startMs = null, endMs = null, trades = null }) {
  const isStatic = Number.isFinite(startMs) && Number.isFinite(endMs);
  // PRIVACY: the anchor line + the rule checklist render under neutral tags for
  // everyone except the admin (whose real labels lazy-load from adminStreamInfo).
  const sd = useStreamDisplay();
  const isTalos = variant === 'talos' || variant === 'talos_ichi';   // talos_ichi reuses Keltner visuals; Kumo gate is applied backend-side
  const REF = isTalos ? (sd.isAdmin ? 'K-EMA20' : 'T-REF') : sd.refline();
  const CONDS = isTalos ? sd.talosConds() : sd.midasConds();
  const tradesRef = useRef(trades);
  tradesRef.current = trades;                              // latest trades without re-running the effect
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const markersRef = useRef(null);
  const framedRef = useRef(false);
  const [status, setStatus] = useState('Yükleniyor…');
  const [last, setLast] = useState(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    framedRef.current = false; markersRef.current = null;   // fresh per (re)mount / window change
    const chart = createChart(containerRef.current, {
      layout: { background: { type: 'solid', color: '#0B0E11' }, textColor: '#EAECEF',
        fontFamily: "'JetBrains Mono', 'SF Mono', Consolas, monospace" },
      // crosshair (hover) time label in UTC — same as the axis labels + the cards (never local time)
      localization: { timeFormatter: (ts) => new Date(ts * 1000)
        .toLocaleString('tr-TR', { timeZone: 'UTC', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) + ' UTC' },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      width: containerRef.current.clientWidth, height: containerRef.current.clientHeight,
      rightPriceScale: { borderColor: '#2B3139', scaleMargins: { top: 0.15, bottom: 0.15 } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2B3139',
        tickMarkFormatter: (time, type) => {
          const d = new Date(time * 1000);
          return type < 3 ? d.toLocaleDateString('tr-TR', { timeZone: 'UTC', day: 'numeric', month: 'short' })
            : d.toLocaleTimeString('tr-TR', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit' });
        } },
      crosshair: { mode: 1 },
    });
    chartRef.current = chart;
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: '#0ECB81', downColor: '#F6465D', borderVisible: false, wickUpColor: '#0ECB81', wickDownColor: '#F6465D',
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 } });
    const refSeries = chart.addSeries(LineSeries, { color: '#3B82F6', lineWidth: 2, title: REF, lastValueVisible: true,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 }, crosshairMarkerVisible: false });
    const bandOpts = { color: 'rgba(59,130,246,0.35)', lineWidth: 1, lineStyle: 2, lastValueVisible: false,
      priceLineVisible: false, crosshairMarkerVisible: false, priceFormat: { type: 'price', precision: 2, minMove: 0.01 } };
    const bandU = chart.addSeries(LineSeries, bandOpts);
    const bandL = chart.addSeries(LineSeries, bandOpts);
    seriesRef.current = { candle, refSeries, bandU, bandL };

    let cancelled = false;
    const load = async () => {
      try {
        const end = isStatic ? endMs : Date.now();
        // Anchor the VWAP at the FX session that contains the window start. A MIDAS UTC "day" can hold
        // TWO FX-sessions (~26h apart) — too wide for a single 1500-bar 1m fetch — so PAGINATE the 1m
        // fetch (up to ~4 pages ≈ 4 days). Staying at 1m keeps ALL signal-formation markers accurate
        // (the non-traded ones only exist client-side, computed on 1m bars).
        const anchor = fxAnchorMs(isStatic ? startMs : end);
        const page = async (from) => {
          const q = `symbol=${SYMBOL}&interval=1m&startTime=${from}&endTime=${end}&limit=1500`;
          let r = await (await fetch(`https://fapi.binance.com/fapi/v1/klines?${q}`)).json();
          if (!Array.isArray(r)) r = await (await fetch(`https://api.binance.com/api/v3/klines?${q}`)).json();
          return Array.isArray(r) ? r : [];
        };
        let raw = [];
        let cursor = anchor;
        for (let p = 0; p < 4 && cursor < end; p += 1) {
          const pg = await page(cursor);
          if (!pg.length) break;
          raw = raw.concat(pg);
          if (pg.length < 1500) break;
          cursor = pg[pg.length - 1][0] + 60000;            // next page starts after the last bar (no overlap)
        }
        if (cancelled || !chartRef.current) return;
        if (!raw.length) { setStatus('Veri yok'); return; }
        const candles = raw.map((d) => ({ time: d[0] / 1000, open: +d[1], high: +d[2], low: +d[3], close: +d[4], volume: +d[5] }));
        const { refData, bandU: bu, bandL: bl, markers, last: lm } = (isTalos ? computeTalos : compute)(candles);
        candle.setData(candles); refSeries.setData(refData); bandU.setData(bu); bandL.setData(bl);
        // markers = ALL signal-formation moments (dimmed) + the trades that opened (entry arrow + exit)
        const finalMarkers = highlightMarkers(markers, tradesRef.current, candles);
        finalMarkers.sort((a, b) => a.time - b.time);
        if (!markersRef.current) markersRef.current = createSeriesMarkers(candle, finalMarkers);
        else markersRef.current.setMarkers(finalMarkers);
        lm.interval = '1m';
        if (!framedRef.current && candles.length) {
          const n = candles.length;
          try {
            if (isStatic) chart.timeScale().fitContent();                                  // whole day
            else chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 240), to: n + 3 });  // live: last ~4h
          } catch { chart.timeScale().fitContent(); }
          framedRef.current = true;
        }
        setLast(lm); setStatus('');
      } catch { if (!cancelled) setStatus('Veri alınamadı (tekrar denenecek)'); }
    };
    load();
    const id = isStatic ? null : setInterval(load, 30000);
    const ro = new ResizeObserver(() => {
      if (chartRef.current && containerRef.current) chartRef.current.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    });
    ro.observe(containerRef.current);
    return () => { cancelled = true; if (id) clearInterval(id); ro.disconnect(); chart.remove(); chartRef.current = null; };
  }, [startMs, endMs, REF, variant]);

  const fmt = (x, d = 2) => (Number.isFinite(x) ? x.toFixed(d) : '—');
  const c = last?.cond;
  const longReady = c && c.sessOk && c.above && c.slopeUp && c.pullLong && c.bull;
  const shortReady = c && c.sessOk && c.below && c.slopeDn && c.pullShort && c.bear;

  const Pill = ({ ok, label }) => (
    <span style={{ padding: '2px 7px', borderRadius: 6, fontSize: 11, whiteSpace: 'nowrap',
      background: ok ? 'rgba(14,203,129,0.14)' : 'rgba(246,70,93,0.10)',
      color: ok ? '#0ECB81' : '#9AA4AD',
      border: `1px solid ${ok ? 'rgba(14,203,129,0.45)' : 'rgba(122,132,141,0.25)'}` }}>
      {ok ? '✓' : '✗'} {label}
    </span>
  );
  const Row = ({ side, ready, color, items }) => (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      <b style={{ color, minWidth: 78 }}>{side} {ready ? (color === '#0ECB81' ? '🟢 HAZIR' : '🔴 HAZIR') : ''}</b>
      {items.map((it) => <Pill key={it.label} ok={it.ok} label={it.label} />)}
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0B0E11', color: '#EAECEF' }}>
      <div style={{ display: 'flex', gap: 18, alignItems: 'baseline', flexWrap: 'wrap', padding: '10px 14px',
        borderBottom: '1px solid #1E2329', fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}>
        <strong style={{ color: '#F0B90B' }}>{sd.name(variant)} · XAUUSDT {last?.interval || '1m'} · {isStatic
          ? new Date(endMs).toLocaleDateString('tr-TR', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric' })
          : 'CANLI'}</strong>
        <span>Fiyat <b>{fmt(last?.price)}</b></span>
        <span style={{ color: '#3B82F6' }}>{REF} <b>{fmt(last?.ref)}</b></span>
        <span>fiyat−{REF} <b>{last ? fmt(last.price - last.ref) : '—'}</b></span>
        <span>eğim({isTalos ? '4×15m' : '60'}) <b>{fmt(last?.slope, 2)}</b></span>
        <span>ATR15 <b>{fmt(last?.atr)}</b> · bant ±{last ? fmt(TOUCH_TOL * last.atr) : '—'}</span>
        {status && <span style={{ color: '#F6465D' }}>{status}</span>}
      </div>
      {!isStatic && c && (
        <div style={{ padding: '8px 14px', borderBottom: '1px solid #1E2329', display: 'flex', flexDirection: 'column',
          gap: 6, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
          <span style={{ color: '#848E9C', fontSize: 10, letterSpacing: '0.04em' }}>SİNYAL KOŞULLARI (anlık · hepsi ✓ olunca sinyal oluşur)</span>
          <Row side="AL" ready={longReady} color="#0ECB81" items={[
            { ok: c.slopeUp, label: CONDS.slopeUp },
            { ok: c.above, label: CONDS.above },
            { ok: c.pullLong, label: CONDS.pullLong },
            { ok: c.bull, label: CONDS.bull },
            { ok: c.sessOk, label: CONDS.sess },
          ]} />
          <Row side="SAT" ready={shortReady} color="#F6465D" items={[
            { ok: c.slopeDn, label: CONDS.slopeDn },
            { ok: c.below, label: CONDS.below },
            { ok: c.pullShort, label: CONDS.pullShort },
            { ok: c.bear, label: CONDS.bear },
            { ok: c.sessOk, label: CONDS.sess },
          ]} />
        </div>
      )}
      <div ref={containerRef} style={{ flex: 1, minHeight: 0 }} />
    </div>
  );
}
