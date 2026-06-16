import { useEffect, useMemo, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { BACKTEST_ALLOWED_SYMBOLS } from '../context/TradeContext';
import { regimeAccuracy, marketOf, MARKETS, fetchRegimeKlines, REGIME_INTERVALS } from '../utils/symbolMeta';
import { computeRegime, verdictOf, TREND_RANGE, TREND_RANGE_LIST } from '../utils/regimeDetectors';
import Sparkline from '../components/viz/Sparkline';
import TrendDetail from './TrendDetail';

// REGIME / TREND MAP — pure price-data classification, NO signals/backtest.
// The "trend vs range" question is answered by an ENSEMBLE of six independent
// sub-modules (regimeDetectors.js): three technical (Efficiency Ratio, ADX,
// Choppiness) + three statistical (Hurst, Variance Ratio, lag-1 autocorrelation),
// each placed on a unified TREND(+1) ↔ RANGE(−1) axis and averaged into a consensus.
// Plus a VOLUME-WEIGHTED group reading, symbol search, and market grouping.

const ER_N = 10;        // bars (of the selected tf) — ER window used only by the accuracy panel
const DIST_BARS = 60;   // ~10 days for the sparkline + volume window
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

const fmtVol = (v) => {
  if (!Number.isFinite(v)) return '—';
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

// −1..+1 consensus bar: blue (range) ← grey (random) → green (trend), marker at score.
const ConsensusMeter = ({ score }) => {
  const pct = ((clamp(score, -1, 1) + 1) / 2) * 100;
  const col = verdictOf(score).color;
  return (
    <div style={{ position: 'relative', height: 6, borderRadius: 4,
      background: 'linear-gradient(90deg, rgba(92,147,255,0.30), rgba(132,144,156,0.25) 50%, rgba(14,203,129,0.30))' }}>
      <div style={{ position: 'absolute', left: '50%', top: -2, bottom: -2, width: 1, background: 'var(--border, #2a2f3a)' }} />
      <div style={{ position: 'absolute', left: `${pct}%`, top: -3, transform: 'translateX(-50%)',
        width: 9, height: 12, borderRadius: 3, background: col, boxShadow: '0 0 0 1px rgba(0,0,0,0.35)' }} />
    </div>
  );
};

// ▲trend ●random ▼range tally
const Votes = ({ votes }) => (
  <span style={{ display: 'inline-flex', gap: 7, fontSize: 11, fontFamily: 'var(--mono)' }}>
    <span style={{ color: TREND_RANGE.trend.color }}>▲{votes.trend}</span>
    <span style={{ color: TREND_RANGE.transition.color }}>●{votes.transition}</span>
    <span style={{ color: TREND_RANGE.range.color }}>▼{votes.range}</span>
  </span>
);

const TrendPage = () => {
  const { t } = useLang();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [regime, setRegime] = useState('all');   // trend/range/transition filter
  const [group, setGroup] = useState('all');      // market filter/group
  const [query, setQuery] = useState('');
  const [detail, setDetail] = useState(null);     // symbol opened in the price+regime modal
  const [tf, setTf] = useState('4h');             // regime timeframe: 4h (history) / 1h (recent)

  useEffect(() => {
    let alive = true;
    setLoading(true);
    (async () => {
      const out = await Promise.all(BACKTEST_ALLOWED_SYMBOLS.map(async (sym) => {
        try {
          // Regime history at the selected timeframe (4h pages from 2025; 1h ~last 50 days).
          const d = await fetchRegimeKlines(sym, tf);
          if (!Array.isArray(d) || d.length < 40) return null;
          const now = Date.now();
          const bars = d.filter((k) => Number(k[6]) <= now);   // completed bars (selected tf)
          const reg = computeRegime(bars);                      // ensemble of 6 detectors
          if (!reg) return null;
          const closes = bars.map((k) => Number(k[4]));
          const vol = bars.slice(-DIST_BARS).reduce((a, k) => a + (Number(k[7]) || 0), 0);
          const acc = regimeAccuracy(closes, ER_N);             // predictive-accuracy panel
          return { sym, market: marketOf(sym), reg, vol, acc, closes: closes.slice(-DIST_BARS) };
        } catch { return null; }
      }));
      if (alive) { setRows(out.filter(Boolean)); setLoading(false); }
    })();
    return () => { alive = false; };
  }, [tf]);

  // VOLUME-WEIGHTED group consensus: mean ensemble score weighted by each symbol's
  // recent volume, so the market's reading is led by its big caps. One tile per market + ALL.
  const groupAgg = useMemo(() => {
    const mk = (key, label, list) => {
      const vol = list.reduce((a, r) => a + r.vol, 0);
      const score = vol > 0 ? list.reduce((a, r) => a + r.reg.score * r.vol, 0) / vol : 0;
      return { key, label, score, verdict: verdictOf(score), vol, n: list.length };
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
    TREND_RANGE_LIST.forEach((s) => { c[s.key] = rows.filter((r) => r.reg.verdict.key === s.key).length; });
    return c;
  }, [rows]);

  // Bar-weighted predictive accuracy across every symbol with enough history.
  const accAgg = useMemo(() => {
    const sub = rows.filter((r) => r.acc);
    if (!sub.length) return null;
    const w = sub.reduce((a, r) => a + r.acc.n, 0);
    const wa = (sel) => sub.reduce((a, r) => a + sel(r.acc) * r.acc.n, 0) / w;
    const overall = wa((a) => a.overall);
    const baseline = wa((a) => a.baseline);
    return { n: w, symbols: sub.length, overall, baseline, lift: overall - baseline,
             contP: wa((a) => a.contP ?? 0) };
  }, [rows]);

  const accColor = (p) => (p == null ? 'var(--muted, #848E9C)'
    : p >= 0.54 ? '#0ECB81' : p <= 0.46 ? '#F6465D' : 'var(--muted, #848E9C)');
  const accPct = (p) => (p == null ? '—' : `%${Math.round(p * 100)}`);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows
      .filter((r) => group === 'all' || r.market === group)
      .filter((r) => regime === 'all' || r.reg.verdict.key === regime)
      .filter((r) => !q || r.sym.toLowerCase().includes(q))
      .sort((a, b) => b.reg.score - a.reg.score);
  }, [rows, group, regime, query]);

  const sections = useMemo(() => (
    MARKETS.map((m) => ({ key: m.key, label: t(m.label), items: visible.filter((r) => r.market === m.key) }))
      .filter((s) => s.items.length)
  ), [visible, t]);

  const REGIME_CHIPS = [{ key: 'all', label: t('Tümü'), color: 'var(--accent, #F5B942)' },
    ...TREND_RANGE_LIST.map((s) => ({ key: s.key, label: t(s.label), color: s.color }))];

  const Card = ({ r }) => {
    const v = r.reg.verdict;
    const tip = `${r.sym}\n${t('Konsensüs')}: ${t(v.label)} (${r.reg.score >= 0 ? '+' : ''}${r.reg.score.toFixed(2)})\n`
      + r.reg.detectors.map((dd) => `${t(dd.label)}: ${dd.display} → ${t(TREND_RANGE[dd.state].label)}`).join('\n')
      + (r.acc ? `\n${t('Süreklilik')}: ${accPct(r.acc.contP)}` : '');
    return (
      <div title={tip} onClick={() => setDetail(r.sym)} style={{
        border: '1px solid var(--border, #2a2f3a)', borderLeft: `3px solid ${v.color}`,
        borderRadius: 10, padding: '12px 14px', background: 'var(--panel, rgba(255,255,255,0.02))', cursor: 'pointer',
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>{r.sym.replace('USDT', '')}</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
            background: `${v.color}22`, color: v.color }}>{t(v.label)}</span>
          <span style={{ fontSize: 11, opacity: 0.65, fontFamily: 'var(--mono)' }}>{r.reg.score >= 0 ? '+' : ''}{r.reg.score.toFixed(2)}</span>
        </div>

        <div style={{ margin: '10px 0 6px' }}><ConsensusMeter score={r.reg.score} /></div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }}>
          <Votes votes={r.reg.votes} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <Sparkline values={r.closes} width={120} height={24} variant="line"
                       zeroBaseline={false} colorBySign={false} color={v.color} showEndDot={false} />
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 10, opacity: 0.6 }}>
          <span>{t('Hacim')}: {fmtVol(r.vol)}</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5 }}
                title={`${t('Süreklilik')}: ${accPct(r.acc?.contP)} · ${t('Doğruluk')}: ${accPct(r.acc?.overall)}`}>
            {r.acc ? (
              <>
                <span style={{ opacity: 0.7 }}>{t('Süreklilik')}</span>
                <b style={{ color: accColor(r.acc.contP) }}>{accPct(r.acc.contP)}</b>
              </>
            ) : <span style={{ opacity: 0.5 }}>{t('Yetersiz veri')}</span>}
          </span>
        </div>
      </div>
    );
  };

  const wrap = { maxWidth: 1180, margin: '0 auto', padding: '20px 22px 60px' };
  return (
    <div style={{ overflowY: 'auto', height: '100%' }}>
      <div style={wrap}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '4px 0 4px' }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: 0.3, margin: 0 }}>{t('Rejim Haritası')}</h1>
          <div style={{ marginLeft: 'auto', display: 'inline-flex', border: '1px solid var(--border, #2a2f3a)', borderRadius: 8, overflow: 'hidden' }}>
            {REGIME_INTERVALS.map((x) => (
              <button key={x} onClick={() => setTf(x)}
                title={x === '4h' ? '4h · 2025+ (tam rejim geçmişi)' : '1h · son ~50 gün'}
                style={{ padding: '5px 13px', fontSize: 12, fontWeight: 700, cursor: 'pointer', border: 'none',
                  background: tf === x ? 'var(--accent, #F5B942)' : 'transparent',
                  color: tf === x ? '#0b0e11' : 'var(--muted, #848E9C)' }}>{x}</button>
            ))}
          </div>
        </div>
        <p style={{ opacity: 0.7, fontSize: 13, lineHeight: 1.55, margin: '0 0 16px', maxWidth: 820 }}>
          {t('Her sembolün “trend mi range mi” sorusu altı bağımsız yöntemle ölçülür — üç teknik (Efficiency Ratio, ADX, Choppiness) + üç istatistiksel (Hurst, Varyans Oranı, otokorelasyon) — ve TREND ↔ RANGE ekseninde tek bir konsensüse indirgenir. Salt fiyat verisi — sinyal/backtest değil.')}
          <span style={{ opacity: 0.6 }}>{` · ${tf === '4h' ? '4h · 2025+' : '1h · ~50g'}`}</span>
        </p>

        {/* REGIME ACCURACY — does the trailing label actually predict the next window? */}
        {accAgg && (
          <div style={{
            border: '1px solid var(--border, #2a2f3a)',
            borderLeft: `3px solid ${accAgg.lift >= 0 ? '#0ECB81' : '#F6465D'}`,
            borderRadius: 10, padding: '14px 16px', marginBottom: 16,
            background: 'var(--panel, rgba(255,255,255,0.02))',
          }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
              <span style={{ fontWeight: 800, fontSize: 14 }}>{t('Rejim Doğruluğu')}</span>
              <span style={{ fontSize: 11, opacity: 0.55 }}>{accAgg.symbols} {t('sembol')} · {accAgg.n.toLocaleString()} {t('bar')}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginBottom: 10 }}>
              {[
                { label: t('Süreklilik'), txt: accPct(accAgg.contP), sub: t('trend yönü korunur'), color: accColor(accAgg.contP) },
                { label: t('İleriye dönük uyum'), txt: accPct(accAgg.overall), sub: `${t('Temel oran')} ${accPct(accAgg.baseline)}`, color: accAgg.overall >= accAgg.baseline ? '#0ECB81' : '#F6465D' },
                { label: t('Beceri'), txt: `${accAgg.lift >= 0 ? '+' : ''}${Math.round(accAgg.lift * 100)}%`, sub: `${t('Doğruluk')} − ${t('Temel oran')}`, color: accAgg.lift >= 0 ? '#0ECB81' : '#F6465D' },
              ].map((s) => (
                <div key={s.label} style={{ border: '1px solid var(--border, #2a2f3a)', borderRadius: 8, padding: '9px 11px' }}>
                  <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, opacity: 0.6 }}>{s.label}</div>
                  <div style={{ fontSize: 22, fontWeight: 800, color: s.color, lineHeight: 1.2 }}>{s.txt}</div>
                  <div style={{ fontSize: 10, opacity: 0.5 }}>{s.sub}</div>
                </div>
              ))}
            </div>
            <p style={{ fontSize: 12, lineHeight: 1.55, opacity: 0.78, margin: '0 0 6px' }}>
              {t('ER rejim etiketi geçmiş pencereyi birebir tanımlar; ancak bir sonraki pencereyi öngörmede beceri göstermez. “Trend” dediğinde fiyat yönünü ~yarı yarıya (yazı-tura) sürdürür ve ileriye dönük uyum, hep çoğunluğu söyleme (temel oran) doğruluğunun altında kalır. Yani “şu an trend” bir tahmin değil, geçmişin betimlemesidir.')}
            </p>
            <p style={{ fontSize: 10.5, lineHeight: 1.5, opacity: 0.5, margin: 0 }}>
              {t('Yöntem: her barın geriye-dönük ER etiketi (trend ER≥0.25) bir sonraki 10-bar penceredeki gerçekleşmeyle karşılaştırılır; pencereler ayrıktır. Temel oran = hep çoğunluğu söylemenin doğruluğu, Beceri = doğruluk − temel oran.')}
            </p>
          </div>
        )}

        {/* VOLUME-WEIGHTED GROUP CONSENSUS — click a tile to filter the grid to that market */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 16 }}>
          {groupAgg.map((g) => (
            <button key={g.key} onClick={() => setGroup(g.key)}
              title={`${g.label} — ${t('Hacim-ağırlıklı')} ${t(g.verdict.label)} (${g.score >= 0 ? '+' : ''}${g.score.toFixed(2)})\n${g.n} ${t('sembol')} · ${t('Hacim')} ${fmtVol(g.vol)}`}
              style={{
                textAlign: 'left', cursor: 'pointer', borderRadius: 10, padding: '11px 13px',
                border: `1px solid ${group === g.key ? g.verdict.color : 'var(--border, #2a2f3a)'}`,
                background: group === g.key ? `${g.verdict.color}1a` : 'var(--panel, rgba(255,255,255,0.02))',
              }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{g.label}</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.55 }}>{g.n} {t('sembol')}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginTop: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: `${g.verdict.color}22`, color: g.verdict.color }}>
                  {t(g.verdict.label)}
                </span>
                <span style={{ fontSize: 11, opacity: 0.7, fontFamily: 'var(--mono)' }}>{g.score >= 0 ? '+' : ''}{g.score.toFixed(2)}</span>
              </div>
              <div style={{ marginTop: 7 }}><ConsensusMeter score={g.score} /></div>
            </button>
          ))}
        </div>

        {/* trend/range filter chips + symbol search */}
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
      {detail && <TrendDetail symbol={detail} tf={tf} onClose={() => setDetail(null)} />}
    </div>
  );
};

export default TrendPage;
