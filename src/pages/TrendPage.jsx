import { useEffect, useMemo, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { BACKTEST_ALLOWED_SYMBOLS } from '../context/TradeContext';
import { REGIME_BANDS, regimeOf, efficiencyRatio, marketLabel } from '../utils/symbolMeta';
import Sparkline from '../components/viz/Sparkline';

// REGIME / TREND MAP — pure price-data classification, NO signals/backtest.
// For each symbol it pulls 4h klines, computes Kaufman's Efficiency Ratio, and
// labels the current regime (Choppy / Light / Mid / Strong trend) so you can eyeball
// whether the price actually looks trending vs chopping. The point: "can we tell
// trend from chop on the raw price?" — grouped by regime, with a price sparkline.

const ER_N = 10;        // 4h bars (~1.7 days)
const DIST_BARS = 60;   // ~10 days for the regime-distribution strip

const TrendPage = () => {
  const { t, locale } = useLang();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    let alive = true;
    (async () => {
      const out = await Promise.all(BACKTEST_ALLOWED_SYMBOLS.map(async (sym) => {
        try {
          const b = sym.replace(/[^A-Za-z0-9]/g, '');
          const res = await fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${b}&interval=4h&limit=180`);
          const d = await res.json();
          if (!Array.isArray(d) || d.length < ER_N + 5) return null;
          const now = Date.now();
          const bars = d.filter((k) => Number(k[6]) <= now);   // completed 4h bars only
          const closes = bars.map((k) => Number(k[4]));
          const er = efficiencyRatio(closes, ER_N);
          const cur = er[er.length - 1];
          if (!Number.isFinite(cur)) return null;
          const recent = er.slice(-DIST_BARS).filter(Number.isFinite);
          const dist = {};
          REGIME_BANDS.forEach((bd) => { dist[bd.key] = 0; });
          recent.forEach((v) => { dist[regimeOf(v).key] += 1; });
          const tot = recent.length || 1;
          REGIME_BANDS.forEach((bd) => { dist[bd.key] /= tot; });
          return { sym, er: cur, regime: regimeOf(cur), closes: closes.slice(-DIST_BARS), dist };
        } catch { return null; }
      }));
      if (alive) { setRows(out.filter(Boolean)); setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  const counts = useMemo(() => {
    const c = { all: rows.length };
    REGIME_BANDS.forEach((b) => { c[b.key] = rows.filter((r) => r.regime.key === b.key).length; });
    return c;
  }, [rows]);

  const visible = useMemo(() => {
    const f = filter === 'all' ? rows : rows.filter((r) => r.regime.key === filter);
    return [...f].sort((a, b) => b.er - a.er);
  }, [rows, filter]);

  const CHIPS = [{ key: 'all', label: t('Tümü'), color: 'var(--accent, #F5B942)' },
    ...REGIME_BANDS.map((b) => ({ key: b.key, label: t(b.label), color: b.color }))];

  const wrap = { maxWidth: 1180, margin: '0 auto', padding: '20px 22px 60px' };
  return (
    <div style={{ overflowY: 'auto', height: '100%' }}>
      <div style={wrap}>
        <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: 0.3, margin: '4px 0 4px' }}>
          {t('Rejim Haritası')}
        </h1>
        <p style={{ opacity: 0.7, fontSize: 13, lineHeight: 1.55, margin: '0 0 16px', maxWidth: 760 }}>
          {t('Her sembolün 4 saatlik fiyatından Efficiency Ratio hesaplanır ve anlık rejim sınıflanır (trend mi, yatay mı). Salt fiyat verisi — sinyal/backtest değil.')}
        </p>

        {/* regime filter chips with live counts */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
          {CHIPS.map((c) => (
            <button
              key={c.key}
              onClick={() => setFilter(c.key)}
              style={{
                padding: '5px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                border: `1px solid ${filter === c.key ? c.color : 'var(--border, #2a2f3a)'}`,
                background: filter === c.key ? `${c.color}22` : 'transparent',
                color: filter === c.key ? c.color : 'var(--muted, #848E9C)',
              }}
            >
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 8, background: c.color, marginRight: 6 }} />
              {c.label} {rows.length > 0 && <b style={{ opacity: 0.8 }}>{counts[c.key] ?? 0}</b>}
            </button>
          ))}
        </div>

        {loading && <div style={{ opacity: 0.6, fontSize: 14, padding: 40, textAlign: 'center' }}>{t('Veriler yükleniyor...')}</div>}
        {!loading && visible.length === 0 && <div style={{ opacity: 0.6, padding: 40, textAlign: 'center' }}>{t('Sonuç yok')}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
          {visible.map((r) => (
            <div key={r.sym} style={{
              border: '1px solid var(--border, #2a2f3a)', borderLeft: `3px solid ${r.regime.color}`,
              borderRadius: 10, padding: '12px 14px', background: 'var(--panel, rgba(255,255,255,0.02))',
            }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>{r.sym.replace('USDT', '')}</span>
                <span style={{ fontSize: 10, opacity: 0.55 }}>{t(marketLabel(r.sym))}</span>
                <span style={{ marginLeft: 'auto', fontSize: 11, opacity: 0.7 }}>ER {r.er.toFixed(2)}</span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '8px 0' }}>
                <span style={{
                  fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
                  background: `${r.regime.color}22`, color: r.regime.color,
                }}>{t(r.regime.label)}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Sparkline values={r.closes} width={120} height={26} variant="line"
                             zeroBaseline={false} colorBySign={false} color={r.regime.color} showEndDot={false} />
                </div>
              </div>

              {/* regime distribution over the last ~10 days */}
              <div style={{ display: 'flex', height: 6, borderRadius: 4, overflow: 'hidden', marginTop: 6 }}
                   title={t('Son 10 günün rejim dağılımı')}>
                {REGIME_BANDS.map((bd) => (
                  r.dist[bd.key] > 0 && (
                    <span key={bd.key} style={{ width: `${r.dist[bd.key] * 100}%`, background: bd.color }} />
                  )
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default TrendPage;
