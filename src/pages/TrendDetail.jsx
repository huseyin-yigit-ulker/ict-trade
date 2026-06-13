import { useEffect, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { REGIME_BANDS, regimeOf, efficiencyRatio } from '../utils/symbolMeta';

// TREND DETAIL — click a symbol on the Regime Map to see its 4h price with the
// HISTORICAL regime painted ON the chart: each bar's background is tinted by its
// regime (choppy=red … strong trend=green), so chop vs trend stretches are obvious
// right on the price. An ER sub-chart below tracks the score against the band lines.
// Pure price data (Binance 4h klines); inline SVG (no chart lib).

const ER_N = 10;
const SHOW = 140;          // ~23 days of 4h bars
const W = 760, PH = 250, EH = 90, PAD = 8;

const TrendDetail = ({ symbol, onClose }) => {
  const { t, locale } = useLang();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    let alive = true;
    (async () => {
      try {
        const b = symbol.replace(/[^A-Za-z0-9]/g, '');
        const res = await fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${b}&interval=4h&limit=300`);
        const d = await res.json();
        if (!Array.isArray(d) || d.length < ER_N + 20) { if (alive) setErr(true); return; }
        const now = Date.now();
        const bars = d.filter((k) => Number(k[6]) <= now);
        const closes = bars.map((k) => Number(k[4]));
        const times = bars.map((k) => Number(k[0]));
        const er = efficiencyRatio(closes, ER_N);
        // window of the last SHOW bars that have a defined ER
        let start = Math.max(ER_N, closes.length - SHOW);
        const idx = [];
        for (let i = start; i < closes.length; i += 1) idx.push(i);
        if (alive) setData({ closes, times, er, idx });
      } catch { if (alive) setErr(true); }
    })();
    return () => { alive = false; window.removeEventListener('keydown', onKey); };
  }, [symbol, onClose]);

  const body = () => {
    if (err) return <div style={{ padding: 40, textAlign: 'center', opacity: 0.6 }}>{t('Veri alınamadı.')}</div>;
    if (!data) return <div style={{ padding: 40, textAlign: 'center', opacity: 0.6 }}>{t('Veriler yükleniyor...')}</div>;
    const { closes, times, er, idx } = data;
    const n = idx.length;
    const px = closes.slice(idx[0], idx[n - 1] + 1);
    const lo = Math.min(...px), hi = Math.max(...px), span = (hi - lo) || 1;
    const x = (j) => PAD + (j / (n - 1)) * (W - 2 * PAD);
    const yP = (v) => PAD + (1 - (v - lo) / span) * (PH - 2 * PAD);
    const yE = (v) => PH + 14 + (1 - Math.min(1, v)) * (EH - PAD);   // ER 0..1 in the sub-chart
    const colAt = (j) => regimeOf(er[idx[j]]).color;
    const curReg = regimeOf(er[idx[n - 1]]);

    // regime mix over the window
    const mix = {};
    REGIME_BANDS.forEach((bd) => { mix[bd.key] = 0; });
    idx.forEach((i) => { mix[regimeOf(er[i]).key] += 1; });

    const colW = (W - 2 * PAD) / n;
    const pricePts = px.map((v, j) => `${x(j).toFixed(1)},${yP(v).toFixed(1)}`).join(' ');
    const erPts = idx.map((i, j) => `${x(j).toFixed(1)},${yE(er[i]).toFixed(1)}`).join(' ');
    const dateAt = (j) => new Date(times[idx[j]]).toLocaleDateString(locale, { month: 'short', day: 'numeric' });

    return (
      <>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
          <span style={{ fontWeight: 800, fontSize: 18 }}>{symbol.replace('USDT', '')}</span>
          <span style={{ fontSize: 12, fontWeight: 700, padding: '2px 9px', borderRadius: 6, background: `${curReg.color}22`, color: curReg.color }}>
            {t(curReg.label)}
          </span>
          <span style={{ fontSize: 12, opacity: 0.7 }}>ER {er[idx[n - 1]].toFixed(2)}</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, opacity: 0.6 }}>
            {REGIME_BANDS.map((bd) => `${t(bd.label)} %${Math.round(mix[bd.key] / n * 100)}`).join(' · ')}
          </span>
        </div>

        <svg viewBox={`0 0 ${W} ${PH + EH + 28}`} width="100%" style={{ display: 'block' }}>
          {/* per-bar regime background on the PRICE chart — the chop/trend history */}
          {idx.map((i, j) => (
            <rect key={j} x={(x(j) - colW / 2).toFixed(1)} y={PAD} width={Math.ceil(colW) + 0.5}
                  height={PH - 2 * PAD} fill={regimeOf(er[i]).color} opacity="0.12" />
          ))}
          {/* price line */}
          <polyline points={pricePts} fill="none" stroke="var(--text, #EAECEF)" strokeWidth="1.6"
                    strokeLinejoin="round" strokeLinecap="round" />
          {/* ER sub-chart band guides */}
          {[[0.50, '#0ECB81'], [0.35, '#5C93FF'], [0.20, '#F5B942']].map(([thr, c]) => (
            <line key={thr} x1={PAD} y1={yE(thr).toFixed(1)} x2={W - PAD} y2={yE(thr).toFixed(1)}
                  stroke={c} strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
          ))}
          <polyline points={erPts} fill="none" stroke="var(--muted, #848E9C)" strokeWidth="1.4" />
          {/* x date labels */}
          {[0, Math.floor(n / 2), n - 1].map((j) => (
            <text key={j} x={Math.min(W - 30, Math.max(2, x(j))).toFixed(1)} y={PH + EH + 24}
                  fontSize="10" fill="var(--muted, #848E9C)" textAnchor={j === 0 ? 'start' : j === n - 1 ? 'end' : 'middle'}>
              {dateAt(j)}
            </text>
          ))}
          <text x={PAD} y={PH + 10} fontSize="10" fill="var(--muted, #848E9C)">ER (0–1) · {t('eşik')} 0.20 / 0.35 / 0.50</text>
        </svg>

        {/* legend */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8, fontSize: 11, opacity: 0.8 }}>
          {REGIME_BANDS.map((bd) => (
            <span key={bd.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: bd.color, display: 'inline-block' }} />
              {t(bd.label)}
            </span>
          ))}
        </div>
        <div style={{ fontSize: 11, opacity: 0.55, marginTop: 8 }}>
          {t('Arka plan rengi her 4h barın rejimidir — kırmızı bölgeler choppy, yeşil bölgeler güçlü trend.')}
        </div>
      </>
    );
  };

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 'min(840px, 96vw)', maxHeight: '90vh', overflowY: 'auto',
        background: 'var(--panel-2, #14161c)', border: '1px solid var(--border, #2a2f3a)',
        borderRadius: 12, padding: '16px 18px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, opacity: 0.7 }}>{t('Fiyat & Rejim')} · 4h</span>
          <button onClick={onClose} style={{
            marginLeft: 'auto', background: 'none', border: '1px solid var(--border, #2a2f3a)',
            color: 'inherit', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12,
          }}>{t('KAPAT')}</button>
        </div>
        {body()}
      </div>
    </div>
  );
};

export default TrendDetail;
