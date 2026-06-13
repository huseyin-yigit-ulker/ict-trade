import { useEffect, useRef, useState } from 'react';
import { createChart, LineSeries, HistogramSeries } from 'lightweight-charts';
import { useLang } from '../context/LanguageContext';
import { REGIME_BANDS, regimeOf, efficiencyRatio } from '../utils/symbolMeta';

// TREND DETAIL — interactive (lightweight-charts, like the app's other charts).
// The price is a single-colour LINE; the REGIME is painted as full-height background
// bands behind it (choppy=red … strong trend=green) so chop vs trend history reads
// right off the chart. A second pane plots the Efficiency Ratio against the
// 0.20/0.35/0.50 band lines. Crosshair hover reads out the bar's date / ER / regime.

const ER_N = 10;
// hex -> rgba with alpha (for the translucent background bands)
const hexA = (hex, a) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

// Official TradingView embed for a symbol (BINANCE perp, 4h). Same widget the app
// uses elsewhere; note its iframe can't carry our regime overlay — that's why the
// regime view stays a separate tab.
const tvEmbedUrl = (sym, locale) => {
  let base = (sym || '').toUpperCase().replace(/[^A-Z0-9.]/g, '');
  if (base.endsWith('PERP')) base = base.replace(/PERP$/, '');
  const tvSym = base.endsWith('.P') ? `BINANCE:${base}` : `BINANCE:${base}.P`;
  const p = new URLSearchParams({
    symbol: tvSym, interval: '240', theme: 'dark', style: '1', toolbarbg: '1a2333',
    hide_side_toolbar: 'false', allow_symbol_change: 'true', studies: '["Volume@tv-basicstudies"]',
    locale: locale === 'en' ? 'en' : 'tr', withdateranges: 'true', hideideas: 'true', autosize: 'true',
  });
  return `https://s.tradingview.com/widgetembed/?${p.toString()}`;
};

const TrendDetail = ({ symbol, onClose }) => {
  const { t, locale } = useLang();
  const wrapRef = useRef(null);
  const chartRef = useRef(null);
  const [meta, setMeta] = useState(null);     // { curER, curRegime, mix, n }
  const [hover, setHover] = useState(null);    // { date, er, regime } under crosshair
  const [err, setErr] = useState(false);
  const [tab, setTab] = useState('regime');    // 'regime' (our overlay) | 'tv' (TradingView embed)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    let alive = true, chart = null, ro = null;

    (async () => {
      let d;
      try {
        const b = symbol.replace(/[^A-Za-z0-9]/g, '');
        const res = await fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${b}&interval=4h&limit=300`);
        d = await res.json();
      } catch { if (alive) setErr(true); return; }
      if (!alive) return;
      if (!Array.isArray(d) || d.length < ER_N + 20 || !wrapRef.current) { setErr(true); return; }

      const now = Date.now();
      const bars = d.filter((k) => Number(k[6]) <= now);
      const closes = bars.map((k) => Number(k[4]));
      const er = efficiencyRatio(closes, ER_N);
      const regAt = (i) => (Number.isFinite(er[i]) ? regimeOf(er[i]) : null);

      const priceData = bars.map((k) => ({ time: Math.floor(Number(k[0]) / 1000), value: Number(k[4]) }));
      // full-height regime background band per bar (translucent column behind the line)
      const bgData = bars.map((k, i) => {
        const reg = regAt(i);
        return { time: Math.floor(Number(k[0]) / 1000), value: 1,
          color: reg ? hexA(reg.color, 0.16) : 'rgba(91,100,114,0.05)' };
      });
      const erData = bars.map((k, i) => ({ time: Math.floor(Number(k[0]) / 1000), value: er[i] }))
        .filter((p) => Number.isFinite(p.value));
      const timeToER = new Map(erData.map((p) => [p.time, p.value]));

      // window regime mix
      const valid = er.filter(Number.isFinite);
      const mix = {}; REGIME_BANDS.forEach((bd) => { mix[bd.key] = 0; });
      valid.forEach((v) => { mix[regimeOf(v).key] += 1; });
      const curER = valid[valid.length - 1];
      setMeta({ curER, curRegime: regimeOf(curER), mix, n: valid.length });

      const W = wrapRef.current.clientWidth || 760;
      chart = createChart(wrapRef.current, {
        width: W, height: 380,
        layout: { background: { type: 'solid', color: '#0B0E11' }, textColor: '#EAECEF',
          fontFamily: "'JetBrains Mono', 'SF Mono', Consolas, monospace", panes: { separatorColor: '#2B3139' } },
        grid: { vertLines: { visible: false }, horzLines: { visible: false } },
        rightPriceScale: { borderColor: '#2B3139' },
        timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2B3139' },
        localization: {
          locale,
          timeFormatter: (ts) => new Date(ts * 1000).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }),
        },
        crosshair: { mode: 1, vertLine: { color: '#848E9C', style: 2, labelBackgroundColor: '#1E2329' },
          horzLine: { color: '#848E9C', style: 2, labelBackgroundColor: '#1E2329' } },
      });
      chartRef.current = chart;

      // regime background bands (add first = behind), on an isolated overlay scale
      // forced to [0,1] full-height so the value=1 columns fill the pane.
      const bg = chart.addSeries(HistogramSeries, {
        priceScaleId: 'bg', base: 0, priceLineVisible: false, lastValueVisible: false,
      });
      bg.setData(bgData);
      chart.priceScale('bg').applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
      // single-colour price line on top
      const price = chart.addSeries(LineSeries, { color: '#EAECEF', lineWidth: 2, priceLineVisible: false });
      price.setData(priceData);

      // ER score in a second pane, with the regime-band threshold lines
      const erLine = chart.addSeries(LineSeries, { color: '#C9CDD4', lineWidth: 1, priceLineVisible: false,
        lastValueVisible: true, priceFormat: { type: 'price', precision: 2, minMove: 0.01 } }, 1);
      erLine.setData(erData);
      [[0.50, '#0ECB81'], [0.35, '#5C93FF'], [0.20, '#F5B942']].forEach(([p, c]) =>
        erLine.createPriceLine({ price: p, color: c, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `${p}` }));
      try { chart.panes()[1]?.setHeight(110); } catch { /* older api */ }

      chart.timeScale().fitContent();
      chart.subscribeCrosshairMove((param) => {
        if (!param || !param.time || !timeToER.has(param.time)) { setHover(null); return; }
        const v = timeToER.get(param.time);
        setHover({ date: new Date(param.time * 1000).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }),
          er: v, regime: regimeOf(v) });
      });

      ro = new ResizeObserver(() => {
        const w = wrapRef.current?.clientWidth || 0;   // skip while hidden (TV tab) -> width 0
        if (w > 0 && chartRef.current) chartRef.current.applyOptions({ width: w });
      });
      ro.observe(wrapRef.current);
    })();

    return () => {
      alive = false;
      window.removeEventListener('keydown', onKey);
      if (ro) ro.disconnect();
      if (chart) { chart.remove(); chartRef.current = null; }
    };
  }, [symbol, onClose, locale]);

  const head = hover || (meta && { er: meta.curER, regime: meta.curRegime, date: t('Güncel') });

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 'min(880px, 96vw)', maxHeight: '92vh', overflowY: 'auto',
        background: 'var(--panel-2, #14161c)', border: '1px solid var(--border, #2a2f3a)', borderRadius: 12, padding: '16px 18px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ fontWeight: 800, fontSize: 18 }}>{symbol.replace('USDT', '')}</span>
          {tab === 'regime' && head && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
              <span style={{ fontWeight: 700, padding: '2px 9px', borderRadius: 6, background: `${head.regime.color}22`, color: head.regime.color }}>
                {t(head.regime.label)}
              </span>
              <span style={{ opacity: 0.7 }}>ER {head.er.toFixed(2)}</span>
              {hover && <span style={{ opacity: 0.5 }}>· {hover.date}</span>}
            </span>
          )}
          {/* Rejim (overlay) ↔ TradingView (official embed) tabs */}
          <div style={{ marginLeft: 'auto', display: 'inline-flex', gap: 4 }}>
            {[['regime', t('Rejim')], ['tv', 'TradingView']].map(([k, lbl]) => (
              <button key={k} onClick={() => setTab(k)} style={{
                padding: '4px 11px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                border: `1px solid ${tab === k ? 'var(--accent, #F5B942)' : 'var(--border, #2a2f3a)'}`,
                background: tab === k ? 'rgba(245,185,66,0.14)' : 'transparent',
                color: tab === k ? 'var(--accent, #F5B942)' : 'var(--muted, #848E9C)',
              }}>{lbl}</button>
            ))}
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: '1px solid var(--border, #2a2f3a)',
            color: 'inherit', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12,
          }}>{t('KAPAT')}</button>
        </div>

        {/* REGIME view — kept mounted (display-toggled) so the chart survives tab switches */}
        <div style={{ display: tab === 'regime' ? 'block' : 'none' }}>
          {err
            ? <div style={{ padding: 40, textAlign: 'center', opacity: 0.6 }}>{t('Veri alınamadı.')}</div>
            : <div ref={wrapRef} style={{ width: '100%', minHeight: 380 }} />}
          {meta && (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 10, fontSize: 11, opacity: 0.8 }}>
              {REGIME_BANDS.map((bd) => (
                <span key={bd.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 10, height: 10, borderRadius: 2, background: bd.color, display: 'inline-block' }} />
                  {t(bd.label)} <b style={{ opacity: 0.7 }}>%{Math.round(meta.mix[bd.key] / meta.n * 100)}</b>
                </span>
              ))}
            </div>
          )}
          <div style={{ fontSize: 11, opacity: 0.55, marginTop: 8 }}>
            {t('Arka plan rengi o 4h barın rejimidir — kırmızı choppy, yeşil güçlü trend. Alt panel ER skoru.')}
          </div>
        </div>

        {/* TRADINGVIEW view — official embed (no regime overlay; iframe) */}
        {tab === 'tv' && (
          <iframe title="TradingView" src={tvEmbedUrl(symbol, locale)} loading="lazy"
                  style={{ width: '100%', height: 460, border: 'none', borderRadius: 8, background: '#0B0E11' }} />
        )}
      </div>
    </div>
  );
};

export default TrendDetail;
