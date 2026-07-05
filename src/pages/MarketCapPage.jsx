import { useEffect, useMemo, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { useStreamDisplay } from '../utils/useStreamDisplay';
import { fetchGlobal, buildBreadth, fmtUsd, BREADTH_REGIMES } from '../utils/marketCap';
import { REGIME_BANDS } from '../utils/symbolMeta';
import analysis from '../assets/data/marketcap_analysis.json';

// TOTAL — crypto market-cap breadth page. Live TOTAL/TOTAL2/TOTAL3 (CoinGecko),
// proxy history charts + breadth regime (Binance), and the backtest analysis:
// does the breadth regime split our R *within* an ER band? (marketcap_analysis.py)

const REGS = ['risk_on', 'neutral', 'risk_off'];
const band = (k) => REGIME_BANDS.find((b) => b.key === k) || { label: k, color: '#848E9C' };
const avgColor = (v) => (v == null ? 'var(--muted, #848E9C)'
  : v > 0.1 ? '#0ECB81' : v < -0.1 ? '#F6465D' : 'var(--muted, #848E9C)');

const card = {
  border: '1px solid var(--border, #2a2f3a)', borderRadius: 10, padding: '14px 16px',
  background: 'var(--panel, rgba(255,255,255,0.02))',
};

// Single auto-scaled line chart (its own min/max), with axis labels.
const LineChart = ({ values, color = '#5C93FF', height = 110, fmt = (v) => v }) => {
  const v = (values || []).filter(Number.isFinite);
  if (v.length < 3) return <div style={{ height, opacity: 0.4, fontSize: 12, display: 'grid', placeItems: 'center' }}>—</div>;
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const W = 1000, H = height, pad = 4;
  const x = (i) => (i / (v.length - 1)) * W;
  const y = (val) => pad + (1 - (val - lo) / span) * (H - 2 * pad);
  const d = v.map((val, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(val).toFixed(1)}`).join(' ');
  const up = v[v.length - 1] >= v[0];
  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height, display: 'block' }}>
        <defs>
          <linearGradient id={`g-${color.slice(1)}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={`${d} L${W} ${H} L0 ${H} Z`} fill={`url(#g-${color.slice(1)})`} stroke="none" />
        <path d={d} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div style={{ position: 'absolute', top: 2, right: 4, fontSize: 10, opacity: 0.5, fontFamily: 'var(--mono)' }}>{fmt(hi)}</div>
      <div style={{ position: 'absolute', bottom: 2, right: 4, fontSize: 10, opacity: 0.5, fontFamily: 'var(--mono)' }}>{fmt(lo)}</div>
      <div style={{ position: 'absolute', bottom: 2, left: 4, fontSize: 10, fontFamily: 'var(--mono)', color: up ? '#0ECB81' : '#F6465D' }}>
        {up ? '▲' : '▼'} {fmt(v[v.length - 1])}
      </div>
    </div>
  );
};

const Tile = ({ label, value, sub, color }) => (
  <div style={{ border: '1px solid var(--border, #2a2f3a)', borderRadius: 8, padding: '10px 12px' }}>
    <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, opacity: 0.6 }}>{label}</div>
    <div style={{ fontSize: 21, fontWeight: 800, color: color || 'inherit', lineHeight: 1.25 }}>{value}</div>
    {sub && <div style={{ fontSize: 10, opacity: 0.5 }}>{sub}</div>}
  </div>
);

const MarketCapPage = () => {
  const { t } = useLang();
  const sd = useStreamDisplay();   // research note names streams — admin-only
  const [live, setLive] = useState(null);
  const [breadth, setBreadth] = useState(null);
  const [loading, setLoading] = useState(true);
  const years = Object.keys(analysis.years || {}).sort().reverse();
  const [year, setYear] = useState(years[0] || '2026');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([fetchGlobal(), buildBreadth()]).then(([g, b]) => {
      if (!alive) return;
      setLive(g); setBreadth(b); setLoading(false);
    });
    return () => { alive = false; };
  }, []);

  const ydata = analysis.years?.[year];
  const reg = breadth?.regime || BREADTH_REGIMES.unknown;
  const pctD = useMemo(() => (breadth?.btcDSeries || []).map((x) => x * 100), [breadth]);

  const CHARTS = [
    { key: 'total', label: 'TOTAL', color: '#F5B942', series: breadth?.total, fmt: fmtUsd },
    { key: 'total2', label: 'TOTAL2 (− BTC)', color: '#5C93FF', series: breadth?.total2, fmt: fmtUsd },
    { key: 'total3', label: 'TOTAL3 (− BTC − ETH)', color: reg.color, series: breadth?.total3, fmt: fmtUsd },
    { key: 'btcd', label: 'BTC.D', color: '#848E9C', series: pctD, fmt: (x) => `%${x.toFixed(1)}` },
  ];

  const wrap = { maxWidth: 1180, margin: '0 auto', padding: '20px 22px 60px' };
  return (
    <div style={{ overflowY: 'auto', height: '100%' }}>
      <div style={wrap}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, margin: '4px 0 4px', flexWrap: 'wrap' }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: 0.3, margin: 0 }}>{t('TOTAL · Piyasa Genişliği')}</h1>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, opacity: 0.6 }}>{t('Genişlik rejimi')}</span>
            <span style={{ fontSize: 13, fontWeight: 800, padding: '3px 11px', borderRadius: 7,
              background: `${reg.color}22`, color: reg.color }}>{t(reg.label)}</span>
            <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: reg.color }}>
              {breadth?.slope != null ? `${breadth.slope >= 0 ? '+' : ''}${(breadth.slope * 100).toFixed(2)}%` : '—'}
            </span>
          </span>
        </div>
        <p style={{ opacity: 0.7, fontSize: 13, lineHeight: 1.55, margin: '0 0 16px', maxWidth: 860 }}>
          {t('Kripto toplam market cap’i üç katmanda: TOTAL (tüm piyasa), TOTAL2 (BTC hariç), TOTAL3 (BTC+ETH hariç = saf altcoin iştahı). Canlı değerler CoinGecko /global’den kesin; geçmiş grafikler ve genişlik rejimi Binance fiyat × arz proxy’sinden (stable hariç). Salt piyasa verisi — sinyal/backtest değil.')}
        </p>

        {/* LIVE numbers */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, marginBottom: 16 }}>
          <Tile label="TOTAL" value={loading ? '…' : fmtUsd(live?.total)} sub={t('tüm market cap')} color="#F5B942" />
          <Tile label="TOTAL2" value={loading ? '…' : fmtUsd(live?.total2)} sub="TOTAL − BTC" color="#5C93FF" />
          <Tile label="TOTAL3" value={loading ? '…' : fmtUsd(live?.total3)} sub="TOTAL − BTC − ETH" color={reg.color} />
          <Tile label="BTC.D" value={loading ? '…' : (live ? `%${(live.btcD * 100).toFixed(1)}` : '—')} sub={t('dominasyon')} />
          <Tile label={t('Altseason')} value={loading || !live ? '…' : (live.total3 / live.total2).toFixed(3)} sub="TOTAL3 / TOTAL2" />
        </div>

        {/* CHARTS — proxy history (~90d, 4h) */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))', gap: 12, marginBottom: 18 }}>
          {CHARTS.map((c) => (
            <div key={c.key} style={card}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: c.color }}>{c.label}</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.5 }}>{t('proxy · 4h · ~90g')}</span>
              </div>
              {loading ? <div style={{ height: 110, opacity: 0.4, display: 'grid', placeItems: 'center', fontSize: 12 }}>{t('yükleniyor…')}</div>
                : <LineChart values={c.series} color={c.color} fmt={c.fmt} />}
            </div>
          ))}
        </div>

        {/* ANALYSIS */}
        <div style={{ ...card, borderLeft: `3px solid ${reg.color}` }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 800, fontSize: 15 }}>{t('Analiz · Genişlik rejimi işe yarıyor mu?')}</span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', border: '1px solid var(--border, #2a2f3a)', borderRadius: 7, overflow: 'hidden' }}>
              {years.map((y) => (
                <button key={y} onClick={() => setYear(y)}
                  style={{ padding: '4px 11px', fontSize: 11, fontWeight: 700, cursor: 'pointer', border: 'none',
                    background: year === y ? 'var(--accent, #F5B942)' : 'transparent',
                    color: year === y ? '#0b0e11' : 'var(--muted, #848E9C)' }}>
                  {y}{analysis.years[y]?.in_sample ? ` (${t('örneklem-içi')})` : ' (OOS)'}
                </button>
              ))}
            </span>
          </div>
          <p style={{ fontSize: 12, opacity: 0.6, margin: '0 0 12px' }}>
            {t('Backtest R’ı, sinyal anındaki ER bandı × TOTAL3 genişlik rejimine göre gruplanır. Rejim ER’den bağımsız bilgi taşıyorsa, aynı bant içinde sütunlar farklılaşmalı.')}
          </p>

          {!ydata && <div style={{ fontSize: 12, opacity: 0.55, padding: '6px 0' }}>{t('Analiz verisi hesaplanıyor…')}</div>}

          {ydata && (
            <>
              {/* orthogonality: avgR by ER band x breadth regime */}
              <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.7, textTransform: 'uppercase', letterSpacing: 0.5, margin: '0 0 6px' }}>
                {t('ER bandı × genişlik rejimi — ortalama R')}
              </div>
              <div style={{ overflowX: 'auto', marginBottom: 16 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontFamily: 'var(--mono)' }}>
                  <thead>
                    <tr style={{ opacity: 0.6 }}>
                      <th style={{ textAlign: 'left', padding: '4px 8px', fontWeight: 600 }}>{t('ER bandı')}</th>
                      {REGS.map((g) => (
                        <th key={g} style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 600, color: BREADTH_REGIMES[g].color }}>
                          {t(BREADTH_REGIMES[g].label)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ydata.orthogonality.map((row) => (
                      <tr key={row.band} style={{ borderTop: '1px solid var(--border, #2a2f3a)' }}>
                        <td style={{ padding: '6px 8px', color: band(row.band).color, fontWeight: 700 }}>{t(band(row.band).label)}</td>
                        {REGS.map((g) => {
                          const c = row.cells[g];
                          return (
                            <td key={g} style={{ textAlign: 'right', padding: '6px 8px', color: avgColor(c?.avgR) }}>
                              {c && c.n ? <><b>{c.avgR >= 0 ? '+' : ''}{c.avgR.toFixed(2)}</b>
                                <span style={{ opacity: 0.45, fontSize: 10 }}> n{c.n}</span></> : '·'}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* separation: total R by stream x breadth regime */}
              <div style={{ fontSize: 11, fontWeight: 700, opacity: 0.7, textTransform: 'uppercase', letterSpacing: 0.5, margin: '0 0 6px' }}>
                {t('Akış × genişlik rejimi — toplam R')}
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontFamily: 'var(--mono)' }}>
                  <thead>
                    <tr style={{ opacity: 0.6 }}>
                      <th style={{ textAlign: 'left', padding: '4px 8px', fontWeight: 600 }}>{t('Akış')}</th>
                      {REGS.map((g) => (
                        <th key={g} style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 600, color: BREADTH_REGIMES[g].color }}>
                          {t(BREADTH_REGIMES[g].label)}
                        </th>
                      ))}
                      <th style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 600 }}>{t('Toplam')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ydata.separation).map(([name, row]) => (
                      <tr key={name} style={{ borderTop: '1px solid var(--border, #2a2f3a)' }}>
                        <td style={{ padding: '6px 8px', fontWeight: 700 }}>{name}</td>
                        {REGS.map((g) => {
                          const c = row[g];
                          return (
                            <td key={g} style={{ textAlign: 'right', padding: '6px 8px', color: avgColor(c?.totR / Math.max(1, c?.n)) }}>
                              {c && c.n ? <>{c.totR >= 0 ? '+' : ''}{c.totR.toFixed(1)}
                                <span style={{ opacity: 0.45, fontSize: 10 }}> n{c.n}</span></> : '·'}
                            </td>
                          );
                        })}
                        <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 700, color: avgColor(row.total?.totR) }}>
                          {row.total ? `${row.total.totR >= 0 ? '+' : ''}${row.total.totR.toFixed(1)}` : '·'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <p style={{ fontSize: 12, lineHeight: 1.55, opacity: 0.8, margin: '14px 0 4px' }}>
            {t('Bulgu: genişlik (TOTAL3) rejimi ER bandından bağımsız bilgi taşıyor. En çok R kazandığımız HAFİF bantta, hızlı yükselen TOTAL3 (risk-on coşkusu) hem 2026 hem 2025’te tutarlı biçimde ZARARLI; nötr/risk-off ise kârlı — “risk-on’da al” sezgisinin tersi.')}
          </p>
          {sd.isAdmin && (
            <p style={{ fontSize: 10.5, lineHeight: 1.5, opacity: 0.5, margin: 0 }}>
              {t('Tek başına temiz bir gate çıkmıyor: etkinin en güçlü olduğu MAIN/OPUS örneklem-dışı (2025) zaten net-negatif, tek istikrarlı kârlı akış RANGE’de dayanıklı bir kazanım yok. Bu yüzden bir lookup + monitör olarak kullanılır; bir akışa bağlamadan önce OOS kazanım göster. Kaynak: sync/marketcap.py + marketcap_analysis.py.')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default MarketCapPage;
