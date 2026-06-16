import { useEffect, useRef, useState } from 'react';
import { createChart, LineSeries, HistogramSeries } from 'lightweight-charts';
import { useLang } from '../context/LanguageContext';
import { REGIME_BANDS, regimeOf, efficiencyRatio, regimeAccuracy, fetchRegimeKlines } from '../utils/symbolMeta';
import { computeRegime, rollingRegime, DETECTOR_WINDOW, TREND_RANGE, DETECTOR_CATS } from '../utils/regimeDetectors';

// −1..+1 detector score bar (centred at 0: blue=range ← grey ← → green=trend).
const ScoreBar = ({ score }) => {
  const s = Math.max(-1, Math.min(1, Number.isFinite(score) ? score : 0));
  const col = s >= 0.15 ? TREND_RANGE.trend.color : s <= -0.15 ? TREND_RANGE.range.color : TREND_RANGE.transition.color;
  return (
    <div style={{ position: 'relative', height: 6, borderRadius: 4, background: 'rgba(255,255,255,0.06)' }}>
      <div style={{ position: 'absolute', left: '50%', top: -1, bottom: -1, width: 1, background: 'var(--border, #2a2f3a)' }} />
      <div style={{ position: 'absolute', left: s < 0 ? `${50 + s * 50}%` : '50%', width: `${Math.abs(s) * 50}%`, top: 0, bottom: 0, background: col, borderRadius: 4 }} />
    </div>
  );
};
const Votes = ({ votes }) => (
  <span style={{ display: 'inline-flex', gap: 7, fontSize: 11, fontFamily: 'var(--mono)' }}>
    <span style={{ color: TREND_RANGE.trend.color }}>▲{votes.trend}</span>
    <span style={{ color: TREND_RANGE.transition.color }}>●{votes.transition}</span>
    <span style={{ color: TREND_RANGE.range.color }}>▼{votes.range}</span>
  </span>
);

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

const TrendDetail = ({ symbol, tf = '4h', onClose }) => {
  const { t, locale } = useLang();
  const wrapRef = useRef(null);
  const chartRef = useRef(null);
  const [meta, setMeta] = useState(null);     // { curER, curRegime, mix, n }
  const [hover, setHover] = useState(null);    // { date, er, regime } under crosshair
  const [err, setErr] = useState(false);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    let alive = true, chart = null, ro = null;

    (async () => {
      let d;
      try {
        // Regime history at the selected timeframe (4h: paginated from 2025; 1h: ~last
        // 50 days) so the regime bands span the visible range. Mirrors the map's tf toggle.
        d = await fetchRegimeKlines(symbol, tf);
      } catch { if (alive) setErr(true); return; }
      if (!alive) return;
      if (!Array.isArray(d) || d.length < ER_N + 20 || !wrapRef.current) { setErr(true); return; }

      const now = Date.now();
      const bars = d.filter((k) => Number(k[6]) <= now);
      const closes = bars.map((k) => Number(k[4]));
      const er = efficiencyRatio(closes, ER_N);

      // ROLLING ensemble regime at every bar — the "regime backtest" over 2026.
      // Background bands + the lower-pane consensus score both come from this.
      // step=2 (8h, forward-filled) halves the recompute — invisible on a 6-month span.
      const roll = rollingRegime(bars, DETECTOR_WINDOW, 2);
      const priceData = bars.map((k) => ({ time: Math.floor(Number(k[0]) / 1000), value: Number(k[4]) }));
      const bgData = bars.map((k, i) => {
        const rv = roll[i];
        return { time: Math.floor(Number(k[0]) / 1000), value: 1,
          color: rv && Number.isFinite(rv.score) ? hexA(rv.verdict.color, 0.17) : 'rgba(91,100,114,0.05)' };
      });
      const scoreData = roll.filter((r) => Number.isFinite(r.score)).map((r) => ({ time: r.time, value: r.score }));
      const timeToRoll = new Map(roll.map((r) => [r.time, r]));

      // ER-window mix (for the Efficiency Ratio detail section below the chart)
      const valid = er.filter(Number.isFinite);
      const mix = {}; REGIME_BANDS.forEach((bd) => { mix[bd.key] = 0; });
      valid.forEach((v) => { mix[regimeOf(v).key] += 1; });
      const curER = valid[valid.length - 1];
      const acc = regimeAccuracy(closes, ER_N);
      const from = bars.length ? Number(bars[0][0]) : null;   // first (oldest) bar = history start
      const reg = computeRegime(bars);                          // current ensemble snapshot
      setMeta({ curER, curRegime: regimeOf(curER), mix, n: valid.length, acc, from, reg });

      const W = wrapRef.current.clientWidth || 760;
      const H = Math.max(440, Math.min(Math.round(window.innerHeight * 0.62), 760));
      chart = createChart(wrapRef.current, {
        width: W, height: H,
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

      // regime background bands (add first = behind), full-height [0,1] overlay scale
      const bg = chart.addSeries(HistogramSeries, {
        priceScaleId: 'bg', base: 0, priceLineVisible: false, lastValueVisible: false,
      });
      bg.setData(bgData);
      chart.priceScale('bg').applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
      // single-colour price line on top
      const price = chart.addSeries(LineSeries, { color: '#EAECEF', lineWidth: 2, priceLineVisible: false });
      price.setData(priceData);

      // CONSENSUS SCORE (−1..+1) in a second pane, with trend / 0 / range guide lines
      const scoreLine = chart.addSeries(LineSeries, { color: '#C9CDD4', lineWidth: 2, priceLineVisible: false,
        lastValueVisible: true, priceFormat: { type: 'price', precision: 2, minMove: 0.01 } }, 1);
      scoreLine.setData(scoreData);
      [[0.15, TREND_RANGE.trend.color, '+0.15'], [0, '#848E9C', '0'], [-0.15, TREND_RANGE.range.color, '−0.15']].forEach(([p, c, title]) =>
        scoreLine.createPriceLine({ price: p, color: c, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title }));
      try { chart.panes()[1]?.setHeight(Math.round(H * 0.32)); } catch { /* older api */ }

      chart.timeScale().fitContent();
      chart.subscribeCrosshairMove((param) => {
        if (!param || !param.time || !timeToRoll.has(param.time)) { setHover(null); return; }
        const rv = timeToRoll.get(param.time);
        if (!rv || !Number.isFinite(rv.score)) { setHover(null); return; }
        setHover({ date: new Date(param.time * 1000).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }),
          score: rv.score, verdict: rv.verdict });
      });

      ro = new ResizeObserver(() => { if (wrapRef.current && chartRef.current) chartRef.current.applyOptions({ width: wrapRef.current.clientWidth }); });
      ro.observe(wrapRef.current);
    })();

    return () => {
      alive = false;
      window.removeEventListener('keydown', onKey);
      if (ro) ro.disconnect();
      if (chart) { chart.remove(); chartRef.current = null; }
    };
  }, [symbol, tf, onClose, locale]);

  // Header read-out: the rolling consensus under the crosshair, else the current snapshot.
  const head = hover || (meta?.reg && { verdict: meta.reg.verdict, score: meta.reg.score, date: t('Güncel') });

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.72)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2.5vh 2vw',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 'min(1480px, 97vw)', maxHeight: '95vh', overflowY: 'auto',
        background: 'var(--panel-2, #14161c)', border: '1px solid var(--border, #2a2f3a)', borderRadius: 14, padding: '16px 20px 20px',
        boxShadow: '0 40px 120px rgba(0,0,0,0.6)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ fontWeight: 800, fontSize: 20 }}>{symbol.replace('USDT', '')}</span>
          <span style={{ fontSize: 12, fontWeight: 700, opacity: 0.6 }}>{t('Fiyat & Rejim')} · {tf}</span>
          {meta?.from && (
            <span style={{ fontSize: 11, opacity: 0.5 }}>
              {new Date(meta.from).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })} → {t('Güncel')}
            </span>
          )}
          {head && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
              <span style={{ fontWeight: 700, padding: '2px 9px', borderRadius: 6, background: `${head.verdict.color}22`, color: head.verdict.color }}>
                {t(head.verdict.label)}
              </span>
              <span style={{ opacity: 0.7, fontFamily: 'var(--mono)' }}>{head.score >= 0 ? '+' : ''}{head.score.toFixed(2)}</span>
              {hover && <span style={{ opacity: 0.5 }}>· {hover.date}</span>}
            </span>
          )}
          <button onClick={onClose} style={{
            marginLeft: 'auto', background: 'none', border: '1px solid var(--border, #2a2f3a)',
            color: 'inherit', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: 12,
          }}>{t('KAPAT')}</button>
        </div>

        {err
          ? <div style={{ padding: 40, textAlign: 'center', opacity: 0.6 }}>{t('Veri alınamadı.')}</div>
          : <div ref={wrapRef} style={{ width: '100%', minHeight: 440 }} />}

        {!err && (
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center', marginTop: 8, fontSize: 11, opacity: 0.7 }}>
            {[TREND_RANGE.trend, TREND_RANGE.transition, TREND_RANGE.range].map((s) => (
              <span key={s.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 11, height: 11, borderRadius: 3, background: hexA(s.color, 0.45), display: 'inline-block' }} />
                {t(s.label)}
              </span>
            ))}
            <span style={{ opacity: 0.6 }}>{t('Arka plan = bar bazında rolling rejim · alt pane = konsensüs skoru (−1..+1).')}</span>
          </div>
        )}

        {/* REGIME SUB-MODULES — every detector's independent trend↔range read + consensus */}
        {meta?.reg && (
          <div style={{ marginTop: 14, border: '1px solid var(--border, #2a2f3a)', borderRadius: 10, padding: '12px 14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
              <span style={{ fontWeight: 800, fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.5, opacity: 0.75 }}>{t('Rejim Submodülleri')}</span>
              <span style={{ fontSize: 12, fontWeight: 700, padding: '2px 9px', borderRadius: 6, background: `${meta.reg.verdict.color}22`, color: meta.reg.verdict.color }}>
                {t('Konsensüs')}: {t(meta.reg.verdict.label)}
              </span>
              <span style={{ fontSize: 12, opacity: 0.6, fontFamily: 'var(--mono)' }}>{meta.reg.score >= 0 ? '+' : ''}{meta.reg.score.toFixed(2)}</span>
              <span style={{ marginLeft: 'auto' }}><Votes votes={meta.reg.votes} /></span>
            </div>
            {DETECTOR_CATS.map((cat) => (
              <div key={cat.key} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, opacity: 0.5, margin: '0 0 6px' }}>{t(cat.label)}</div>
                <div style={{ display: 'grid', gap: 7 }}>
                  {meta.reg.detectors.filter((d) => d.cat === cat.key).map((d) => (
                    <div key={d.key} title={t(d.note)}
                      style={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 1.3fr) 44px 1fr 58px', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: 12, fontWeight: 600 }}>{t(d.label)}</span>
                      <span style={{ fontSize: 12, fontFamily: 'var(--mono)', opacity: 0.8, textAlign: 'right' }}>{d.display}</span>
                      <ScoreBar score={d.score} />
                      <span style={{ fontSize: 11, fontWeight: 700, textAlign: 'right', color: TREND_RANGE[d.state].color }}>{t(TREND_RANGE[d.state].label)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <div style={{ fontSize: 10.5, opacity: 0.5, lineHeight: 1.5, marginTop: 2 }}>
              {t('Her submodül trend(+1) ↔ range(−1) ekseninde bağımsız ölçer; ortalamaları konsensüsü verir. Rejim ölçek-bağımlıdır ve gerçek-zamanlı okuma gecikmelidir.')}
            </div>
          </div>
        )}

        <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, opacity: 0.5, margin: '14px 0 2px' }}>{t('Efficiency Ratio detayı')}</div>
        {meta && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 6, fontSize: 11, opacity: 0.8 }}>
            {REGIME_BANDS.map((bd) => (
              <span key={bd.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: bd.color, display: 'inline-block' }} />
                {t(bd.label)} <b style={{ opacity: 0.7 }}>%{Math.round(meta.mix[bd.key] / meta.n * 100)}</b>
              </span>
            ))}
          </div>
        )}
        {meta && meta.acc && (
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 10, fontSize: 11, alignItems: 'center' }}>
            <span style={{ fontWeight: 700, opacity: 0.6, textTransform: 'uppercase', letterSpacing: 0.5, fontSize: 10 }}>{t('Rejim Doğruluğu')}</span>
            <span>{t('Süreklilik')} <b style={{ color: meta.acc.contP >= 0.54 ? '#0ECB81' : meta.acc.contP <= 0.46 ? '#F6465D' : '#C9CDD4' }}>%{Math.round((meta.acc.contP ?? 0) * 100)}</b></span>
            <span>{t('İleriye dönük uyum')} <b style={{ color: meta.acc.overall >= meta.acc.baseline ? '#0ECB81' : '#F6465D' }}>%{Math.round(meta.acc.overall * 100)}</b>
              <span style={{ opacity: 0.5 }}> · {t('Temel oran')} %{Math.round(meta.acc.baseline * 100)}</span></span>
            <span style={{ opacity: 0.5 }}>{t('Örnek')} {meta.acc.n} {t('bar')}</span>
          </div>
        )}
        <div style={{ fontSize: 11, opacity: 0.5, marginTop: 8 }}>
          {t('Yukarıdaki ER karışımı ve doğruluk denetimi yalnız Efficiency Ratio submodülüne aittir; ana grafik 6-yöntemli konsensüsü gösterir.')}
        </div>
      </div>
    </div>
  );
};

export default TrendDetail;
