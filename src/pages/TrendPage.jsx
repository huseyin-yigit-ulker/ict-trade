import { useEffect, useMemo, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { BACKTEST_ALLOWED_SYMBOLS } from '../context/TradeContext';
import { REGIME_BANDS, regimeOf, efficiencyRatio, marketOf, MARKETS } from '../utils/symbolMeta';
import Sparkline from '../components/viz/Sparkline';

// REGIME / TREND MAP — pure price-data classification, NO signals/backtest.
// Per symbol: 4h klines -> Kaufman Efficiency Ratio -> current regime
// (Choppy <0.20 / Light 0.20-0.35 / Mid 0.35-0.50 / Strong >=0.50). Plus a
// VOLUME-WEIGHTED group trend (big-cap symbols dominate their market's reading),
// symbol search, and grouping by market.

const ER_N = 10;        // 4h bars (~1.7 days)
const DIST_BARS = 60;   // ~10 days for the regime mix + volume window

const fmtVol = (v) => {
  if (!Number.isFinite(v)) return '—';
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

const TrendPage = () => {
  const { t } = useLang();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [regime, setRegime] = useState('all');   // regime filter
  const [group, setGroup] = useState('all');      // market filter/group
  const [query, setQuery] = useState('');

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
          const bars = d.filter((k) => Number(k[6]) <= now);   // completed 4h bars
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
          // recent USDT quote volume (kline[7]) over the window = group weight
          const vol = bars.slice(-DIST_BARS).reduce((a, k) => a + (Number(k[7]) || 0), 0);
          return { sym, market: marketOf(sym), er: cur, regime: regimeOf(cur),
                   closes: closes.slice(-DIST_BARS), dist, vol };
        } catch { return null; }
      }));
      if (alive) { setRows(out.filter(Boolean)); setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  // VOLUME-WEIGHTED group trend: aggregate ER weighted by each symbol's recent
  // volume, so the market's reading is led by its big caps. One tile per market + ALL.
  const groupAgg = useMemo(() => {
    const mk = (key, label, list) => {
      const vol = list.reduce((a, r) => a + r.vol, 0);
      const er = vol > 0 ? list.reduce((a, r) => a + r.er * r.vol, 0) / vol : 0;
      return { key, label, er, regime: regimeOf(er), vol, n: list.length };
    };
    const tiles = [mk('all', t('Tümü'), rows)];
    MARKETS.forEach((m) => {
      const list = rows.filter((r) => r.market === m.key);
      if (list.length) tiles.push(mk(m.key, t(m.label), list));
    });
    return tiles;
  }, [rows, t]);

  const counts = useMemo(() => {
    const c = { all: rows.length };
    REGIME_BANDS.forEach((b) => { c[b.key] = rows.filter((r) => r.regime.key === b.key).length; });
    return c;
  }, [rows]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows
      .filter((r) => group === 'all' || r.market === group)
      .filter((r) => regime === 'all' || r.regime.key === regime)
      .filter((r) => !q || r.sym.toLowerCase().includes(q))
      .sort((a, b) => b.er - a.er);
  }, [rows, group, regime, query]);

  // group the visible grid into market sections (skip empty)
  const sections = useMemo(() => {
    return MARKETS.map((m) => ({ key: m.key, label: t(m.label), items: visible.filter((r) => r.market === m.key) }))
      .filter((s) => s.items.length);
  }, [visible, t]);

  const REGIME_CHIPS = [{ key: 'all', label: t('Tümü'), color: 'var(--accent, #F5B942)' },
    ...REGIME_BANDS.map((b) => ({ key: b.key, label: t(b.label), color: b.color }))];

  const Card = ({ r }) => (
    <div style={{
      border: '1px solid var(--border, #2a2f3a)', borderLeft: `3px solid ${r.regime.color}`,
      borderRadius: 10, padding: '12px 14px', background: 'var(--panel, rgba(255,255,255,0.02))',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>{r.sym.replace('USDT', '')}</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, opacity: 0.7 }}>ER {r.er.toFixed(2)}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '8px 0' }}>
        <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: `${r.regime.color}22`, color: r.regime.color }}>
          {t(r.regime.label)}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Sparkline values={r.closes} width={120} height={26} variant="line"
                     zeroBaseline={false} colorBySign={false} color={r.regime.color} showEndDot={false} />
        </div>
      </div>
      <div style={{ display: 'flex', height: 6, borderRadius: 4, overflow: 'hidden', margin: '6px 0 4px' }} title={t('Son 10 günün rejim dağılımı')}>
        {REGIME_BANDS.map((bd) => (r.dist[bd.key] > 0 && (
          <span key={bd.key} style={{ width: `${r.dist[bd.key] * 100}%`, background: bd.color }} />
        )))}
      </div>
      <div style={{ fontSize: 10, opacity: 0.5 }}>{t('Hacim')}: {fmtVol(r.vol)}</div>
    </div>
  );

  const wrap = { maxWidth: 1180, margin: '0 auto', padding: '20px 22px 60px' };
  return (
    <div style={{ overflowY: 'auto', height: '100%' }}>
      <div style={wrap}>
        <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: 0.3, margin: '4px 0 4px' }}>{t('Rejim Haritası')}</h1>
        <p style={{ opacity: 0.7, fontSize: 13, lineHeight: 1.55, margin: '0 0 16px', maxWidth: 760 }}>
          {t('Her sembolün 4 saatlik fiyatından Efficiency Ratio hesaplanır ve anlık rejim sınıflanır (trend mi, yatay mı). Salt fiyat verisi — sinyal/backtest değil.')}
        </p>

        {/* VOLUME-WEIGHTED GROUP TREND — click a tile to filter the grid to that market */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 16 }}>
          {groupAgg.map((g) => (
            <button key={g.key} onClick={() => setGroup(g.key)}
              style={{
                textAlign: 'left', cursor: 'pointer', borderRadius: 10, padding: '11px 13px',
                border: `1px solid ${group === g.key ? g.regime.color : 'var(--border, #2a2f3a)'}`,
                background: group === g.key ? `${g.regime.color}1a` : 'var(--panel, rgba(255,255,255,0.02))',
              }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{g.label}</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.55 }}>{g.n} {t('sembol')}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginTop: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: `${g.regime.color}22`, color: g.regime.color }}>
                  {t(g.regime.label)}
                </span>
                <span style={{ fontSize: 11, opacity: 0.7 }}>ER {g.er.toFixed(2)}</span>
              </div>
              <div style={{ fontSize: 10, opacity: 0.5, marginTop: 5 }}>{t('Hacim-ağırlıklı')} · {fmtVol(g.vol)}</div>
            </button>
          ))}
        </div>

        {/* regime filter chips + symbol search */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', marginBottom: 16 }}>
          {REGIME_CHIPS.map((c) => (
            <button key={c.key} onClick={() => setRegime(c.key)}
              style={{
                padding: '5px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                border: `1px solid ${regime === c.key ? c.color : 'var(--border, #2a2f3a)'}`,
                background: regime === c.key ? `${c.color}22` : 'transparent',
                color: regime === c.key ? c.color : 'var(--muted, #848E9C)',
              }}>
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 8, background: c.color, marginRight: 6 }} />
              {c.label} {rows.length > 0 && <b style={{ opacity: 0.8 }}>{counts[c.key] ?? 0}</b>}
            </button>
          ))}
          <input type="text" placeholder={t('Sembol ara...')} value={query} onChange={(e) => setQuery(e.target.value)}
            style={{ marginLeft: 'auto', padding: '6px 10px', borderRadius: 8, fontSize: 12, minWidth: 160,
                     border: '1px solid var(--border, #2a2f3a)', background: 'var(--panel, rgba(255,255,255,0.03))', color: 'inherit' }} />
        </div>

        {loading && <div style={{ opacity: 0.6, fontSize: 14, padding: 40, textAlign: 'center' }}>{t('Veriler yükleniyor...')}</div>}
        {!loading && visible.length === 0 && <div style={{ opacity: 0.6, padding: 40, textAlign: 'center' }}>{t('Sonuç yok')}</div>}

        {/* cards, grouped into market sections */}
        {sections.map((s) => (
          <div key={s.key} style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', opacity: 0.6, margin: '0 0 8px' }}>
              {s.label} <span style={{ opacity: 0.6 }}>({s.items.length})</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 12 }}>
              {s.items.map((r) => <Card key={r.sym} r={r} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TrendPage;
