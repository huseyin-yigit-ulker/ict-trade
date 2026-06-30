import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts';

// Standalone LIVE chart for MIDAS (XAUUSDT 1m) — NOT tied to a trade. Draws the exact metrics the
// signal logic (sync/midas/strategy.signals) keys off, recomputed live every 30s:
//   • anchored VWAP (reset 18:00 ET / FX-day)  — the trend reference  (validated == backend)
//   • ±0.25·ATR(15m) pullback band around VWAP  — the "touched VWAP" trigger zone
//   • LONG/SHORT markers where the core rule fires (close vs VWAP + VWAP-slope + pullback + bar dir,
//     London 07-13 UTC skipped) — same conditions as the backend (market-hours filter approximate).
const SYMBOL = 'XAUUSDT';
const SLOPE_N = 60, ATR_N = 14, TOUCH_TOL = 0.25, ATR_INIT = 1.5, SKIP_START = 7, SKIP_END = 13;

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
  const vwapData = []; const bandU = []; const bandL = []; const markers = [];
  for (let i = 0; i < candles.length; i += 1) {
    const c = candles[i]; const v = vw[i];
    vwapData.push({ time: c.time, value: v });
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
  const last = { price: candles[i].close, vwap: vw[i], slope: slope[i], atr: a[i], time: candles[i].time };
  return { vwapData, bandU, bandL, markers, last };
};

export default function MidasLiveChart() {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const markersRef = useRef(null);
  const framedRef = useRef(false);
  const [status, setStatus] = useState('Yükleniyor…');
  const [last, setLast] = useState(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: 'solid', color: '#0B0E11' }, textColor: '#EAECEF',
        fontFamily: "'JetBrains Mono', 'SF Mono', Consolas, monospace" },
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
    const vwap = chart.addSeries(LineSeries, { color: '#3B82F6', lineWidth: 2, title: 'VWAP', lastValueVisible: true,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 }, crosshairMarkerVisible: false });
    const bandOpts = { color: 'rgba(59,130,246,0.35)', lineWidth: 1, lineStyle: 2, lastValueVisible: false,
      priceLineVisible: false, crosshairMarkerVisible: false, priceFormat: { type: 'price', precision: 2, minMove: 0.01 } };
    const bandU = chart.addSeries(LineSeries, bandOpts);
    const bandL = chart.addSeries(LineSeries, bandOpts);
    seriesRef.current = { candle, vwap, bandU, bandL };

    let cancelled = false;
    const load = async () => {
      try {
        const now = Date.now();
        const start = fxAnchorMs(now);
        const base = `symbol=${SYMBOL}&interval=1m&startTime=${start}&endTime=${now}&limit=1500`;
        let raw = await (await fetch(`https://fapi.binance.com/fapi/v1/klines?${base}`)).json();
        if (!Array.isArray(raw)) raw = await (await fetch(`https://api.binance.com/api/v3/klines?${base}`)).json();
        if (!Array.isArray(raw) || !raw.length) { if (!cancelled) setStatus('Veri yok'); return; }
        const candles = raw.map((d) => ({ time: d[0] / 1000, open: +d[1], high: +d[2], low: +d[3], close: +d[4], volume: +d[5] }));
        const { vwapData, bandU: bu, bandL: bl, markers, last: lm } = compute(candles);
        if (cancelled || !chartRef.current) return;
        candle.setData(candles); vwap.setData(vwapData); bandU.setData(bu); bandL.setData(bl);
        markers.sort((a, b) => a.time - b.time);
        if (!markersRef.current) markersRef.current = createSeriesMarkers(candle, markers);
        else markersRef.current.setMarkers(markers);
        if (!framedRef.current && candles.length) {
          const n = candles.length;
          try { chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 240), to: n + 3 }); } catch { chart.timeScale().fitContent(); }
          framedRef.current = true;
        }
        setLast(lm); setStatus('');
      } catch { if (!cancelled) setStatus('Veri alınamadı (tekrar denenecek)'); }
    };
    load();
    const id = setInterval(load, 30000);
    const ro = new ResizeObserver(() => {
      if (chartRef.current && containerRef.current) chartRef.current.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    });
    ro.observe(containerRef.current);
    return () => { cancelled = true; clearInterval(id); ro.disconnect(); chart.remove(); chartRef.current = null; };
  }, []);

  const fmt = (x, d = 2) => (Number.isFinite(x) ? x.toFixed(d) : '—');
  const sigState = last && Number.isFinite(last.slope)
    ? (last.price > last.vwap && last.slope > 0 ? 'YUKARI trend (AL tarafı)'
      : last.price < last.vwap && last.slope < 0 ? 'AŞAĞI trend (SAT tarafı)' : 'trend yok / VWAP yakını')
    : '—';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0B0E11', color: '#EAECEF' }}>
      <div style={{ display: 'flex', gap: 18, alignItems: 'baseline', flexWrap: 'wrap', padding: '10px 14px',
        borderBottom: '1px solid #1E2329', fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}>
        <strong style={{ color: '#F0B90B' }}>MIDAS · XAUUSDT 1m · CANLI</strong>
        <span>Fiyat <b>{fmt(last?.price)}</b></span>
        <span style={{ color: '#3B82F6' }}>VWAP <b>{fmt(last?.vwap)}</b></span>
        <span>fiyat−VWAP <b>{last ? fmt(last.price - last.vwap) : '—'}</b></span>
        <span>eğim(60) <b>{fmt(last?.slope, 2)}</b></span>
        <span>ATR15 <b>{fmt(last?.atr)}</b> · bant ±{last ? fmt(TOUCH_TOL * last.atr) : '—'}</span>
        <span>durum: <b>{sigState}</b></span>
        {status && <span style={{ color: '#F6465D' }}>{status}</span>}
      </div>
      <div ref={containerRef} style={{ flex: 1, minHeight: 0 }} />
    </div>
  );
}
