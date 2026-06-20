import { useEffect, useMemo, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { BACKTEST_ALLOWED_SYMBOLS } from '../context/TradeContext';
import { STRATEGY_INFO } from '../utils/strategyInfo';
import { STREAMS, fmtR, fmtExp, fmtPct, fmtPf } from '../utils/streamStats';
import { MARKETS } from '../utils/symbolMeta';
import {
  normalizeRows, bundle, symbolCompare, categoryCompare, diversification,
  weekdayKey, hourKey, monthKey, yearKey, WEEKDAYS, filterWindow, filterMarket,
} from '../utils/intelStats';
import { MiniCurve, CompareBars, StatRow, SERIES_A, SERIES_B, SERIES_BLEND } from '../components/intel/IntelViz';

// Which backtest streams are comparable = the STREAMS registry (its `version` tags
// physically exist in ict_trade.trading_signals). Selection is dynamic: the user
// picks any two from this list, so adding a stream to the registry surfaces it here
// automatically — nothing in this file is hardcoded to a specific pair.
const cleanTable = (raw) => {
  const c = (raw || 'ict_trade.trading_signals').toString().trim().replace(/^["']|["']$/g, '');
  return c.includes('.') ? c.split('.') : ['ict_trade', c];
};

// Paginated pull of one version's rows from the backtest Supabase REST (mirrors
// TradeContext.loadBacktest: Accept-Profile schema header + 1000-row pages).
const fetchVersion = async (version) => {
  const url = import.meta.env.BACKTESTING_VITE_SUPABASE_URL;
  const key = import.meta.env.BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
  if (!url || !key) throw new Error('config');
  const [schema, table] = cleanTable(import.meta.env.BACKTESTING_DB_TABLE);
  const params = new URLSearchParams({
    select: 'symbol,trade_type,direction,signal_time,real_entry_time,exit_time,entry_price,sl_price,tp_price,status,exit_price,pnl_r,version',
    order: 'signal_time.desc',
  });
  params.append('version', `eq.${version}`);
  params.append('signal_time', 'gte.2024-01-01T00:00:00Z');
  params.append('symbol', `in.(${BACKTEST_ALLOWED_SYMBOLS.join(',')})`);
  const endpoint = `${url}/rest/v1/${table}?${params.toString()}`;
  const pageSize = 1000;
  let from = 0;
  const all = [];
  for (;;) {
    const res = await fetch(endpoint, {
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        'Accept-Profile': schema,
        'Range-Unit': 'items',
        Range: `${from}-${from + pageSize - 1}`,
      },
    });
    if (!res.ok) throw new Error(`fetch ${version} ${res.status}`);
    const rows = await res.json();
    if (!Array.isArray(rows) || rows.length === 0) break;
    all.push(...rows);
    if (rows.length < pageSize) break;
    from += pageSize;
  }
  return all;
};

// Session-level cache: version -> Promise<normalised trades>. Historical backtest
// rows are immutable, so each stream is fetched at most ONCE per session (shared
// across page remounts and stream re-selection — the "cache logic"). Caching the
// promise also de-dupes concurrent loads of the same version.
const STREAM_CACHE = new Map();
const loadStream = (version) => {
  if (!STREAM_CACHE.has(version)) {
    STREAM_CACHE.set(
      version,
      fetchVersion(version)
        .then((rows) => normalizeRows(rows, version))
        .catch((e) => { STREAM_CACHE.delete(version); throw e; }),   // don't cache failures
    );
  }
  return STREAM_CACHE.get(version);
};

const validVersion = (v, fallback) => (STREAMS.some((s) => s.version === v) ? v : fallback);
const DEFAULT_A = STREAMS[0]?.version;
const DEFAULT_B = STREAMS[1]?.version || STREAMS[0]?.version;

const Section = ({ title, sub, children, full }) => (
  <section className={`intel-section${full ? ' intel-section--full' : ''}`}>
    <div className="intel-section__head">
      <h3>{title}</h3>
      {sub && <p>{sub}</p>}
    </div>
    {children}
  </section>
);

const IntelligencePage = () => {
  const { t, lang, locale } = useLang();
  const fmtHrs = (h) => (h == null ? '—' : h >= 48 ? `${(h / 24).toFixed(1)}${t('g')}` : `${h.toFixed(1)}${t('sa')}`);
  const [data, setData] = useState({});            // version -> normalised trades (all streams)
  const [status, setStatus] = useState('loading'); // loading | ok | error
  const [win, setWin] = useState('common');        // common (overlap, fair) | full
  const [market, setMarket] = useState('all');
  const [verA, setVerA] = useState(() => { try { return validVersion(localStorage.getItem('pusu.intelA'), DEFAULT_A); } catch { return DEFAULT_A; } });
  const [verB, setVerB] = useState(() => { try { return validVersion(localStorage.getItem('pusu.intelB'), DEFAULT_B); } catch { return DEFAULT_B; } });

  const persistA = (v) => { setVerA(v); try { localStorage.setItem('pusu.intelA', v); } catch { /* ignore */ } };
  const persistB = (v) => { setVerB(v); try { localStorage.setItem('pusu.intelB', v); } catch { /* ignore */ } };
  // Picking a stream already held by the other side swaps them (keep A ≠ B).
  const pickA = (v) => { if (v === verB) persistB(verA); persistA(v); };
  const pickB = (v) => { if (v === verA) persistA(verB); persistB(v); };

  // Load EVERY registered stream once (cache-aware) so switching the A/B selectors
  // is instant — no refetch. Subsequent visits reuse STREAM_CACHE.
  useEffect(() => {
    let alive = true;
    Promise.allSettled(STREAMS.map((s) => loadStream(s.version).then((tr) => [s.version, tr])))
      .then((results) => {
        if (!alive) return;
        const ok = results.filter((r) => r.status === 'fulfilled').map((r) => r.value);
        if (!ok.length) { setStatus('error'); return; }
        setData(Object.fromEntries(ok));
        setStatus('ok');
      });
    return () => { alive = false; };
  }, []);

  const meta = (version) => {
    const s = STREAMS.find((x) => x.version === version) || { key: version, tf: version };
    const info = STRATEGY_INFO[s.key]?.[lang] || STRATEGY_INFO[s.key]?.tr;
    return { tf: s.tf || s.key, title: s.label || info?.title || s.key };
  };
  const metaA = meta(verA);
  const metaB = meta(verB);
  const titleA = metaA.title; const tagA = metaA.tf;
  const titleB = metaB.title; const tagB = metaB.tf;

  const m = useMemo(() => {
    const rawA = data[verA];
    const rawB = data[verB];
    if (!rawA || !rawB) return null;
    const minTs = (arr) => (arr.length ? Math.min(...arr.map((x) => x.signalTs)) : Infinity);
    const yearOf = (ts) => (Number.isFinite(ts) ? new Date(ts).getUTCFullYear() : null);
    // Common window = the actual OVERLAP of the two selected streams (max of their starts).
    const commonFrom = Math.max(minTs(rawA), minTs(rawB));
    const fromTs = win === 'common' ? commonFrom : null;
    const va = filterMarket(filterWindow(rawA, fromTs), market);
    const vb = filterMarket(filterWindow(rawB, fromTs), market);
    const bA = bundle(va);
    const bB = bundle(vb);
    // Diversification/blend co-movement is only defined on the overlap, so it always
    // uses the common window regardless of the toggle.
    const ca = win === 'common' ? va : filterMarket(filterWindow(rawA, commonFrom), market);
    const cb = win === 'common' ? vb : filterMarket(filterWindow(rawB, commonFrom), market);
    const monthsSet = [...new Set([...va, ...vb].filter((x) => x.closed).map(monthKey))].sort();
    const years = [...new Set([...rawA, ...rawB].map(yearKey))].sort();
    return {
      bA, bB,
      bAc: win === 'common' ? bA : bundle(ca),
      bBc: win === 'common' ? bB : bundle(cb),
      sym: symbolCompare(va, vb),
      div: diversification(ca, cb),
      mkt: categoryCompare(va, vb, (x) => x.market, ['crypto', 'metal', 'stock']),
      dir: categoryCompare(va, vb, (x) => x.dir, ['LONG', 'SHORT']),
      wd: categoryCompare(va, vb, weekdayKey, WEEKDAYS),
      hr: categoryCompare(va, vb, hourKey, Array.from({ length: 24 }, (_, i) => i)),
      mo: categoryCompare(va, vb, monthKey, monthsSet),
      // year panel always spans full history (the OOS story) but honours the market filter
      yr: categoryCompare(filterMarket(rawA, market), filterMarket(rawB, market), yearKey, years),
      commonYear: yearOf(commonFrom),
      startA: yearOf(minTs(rawA)),
      startB: yearOf(minTs(rawB)),
    };
  }, [data, verA, verB, win, market]);

  if (status === 'loading') {
    return <div className="intel-page"><div className="intel-state">{t('Veriler yükleniyor...')}</div></div>;
  }
  if (status === 'error' || !m) {
    return <div className="intel-page"><div className="intel-state intel-state--err">{t('Veri alınamadı.')}</div></div>;
  }

  const { bA, bB, sym, div } = m;
  const optLabel = (s) => `${meta(s.version).title} · ${s.tf}`;

  // equity overlay series (both on the shared overlap time axis)
  const curve = [
    { label: `${titleA} (${tagA})`, color: SERIES_A, points: bA.equity, valueLabel: fmtR(bA.totalR) },
    { label: `${titleB} (${tagB})`, color: SERIES_B, points: bB.equity, valueLabel: fmtR(bB.totalR) },
  ];
  const drawdownCurve = [
    { label: `${titleA} (${tagA})`, color: SERIES_A, points: bA.equity.map((p) => ({ ts: p.ts, cum: p.cum - p.peak })) },
    { label: `${titleB} (${tagB})`, color: SERIES_B, points: bB.equity.map((p) => ({ ts: p.ts, cum: p.cum - p.peak })) },
  ];
  // Blend chart: all three series on the common overlap window so they share an axis.
  const blendCurve = [
    { label: `${titleA} (${tagA})`, color: SERIES_A, points: m.bAc.equity },
    { label: `${titleB} (${tagB})`, color: SERIES_B, points: m.bBc.equity },
    { label: t('İkisi birden'), color: SERIES_BLEND, points: div.blendEq, valueLabel: fmtR(div.blendTotal), area: true },
  ];

  // Verdict (selected window for R/efficiency/risk; diversification on the overlap).
  const leadR = bA.totalR >= bB.totalR ? titleA : titleB;
  const leadEff = bA.avgR >= bB.avgR ? titleA : titleB;
  const leadRisk = (bA.recovery ?? 0) >= (bB.recovery ?? 0) ? titleA : titleB;
  const bestSingleRec = Math.max(div.aRecovery ?? 0, div.bRecovery ?? 0);
  const blendHelps = (div.blendRecovery ?? 0) > bestSingleRec;

  // Cost sensitivity: net R after `s` bps/side of slippage ON TOP of the embedded 0.1%.
  const netAfter = (b, bps) => b.totalR - (2 * bps) / 1e4 * b.invRiskSum;
  const breakeven = (b) => (b.invRiskSum > 0 ? (b.totalR * 1e4) / (2 * b.invRiskSum) : null);
  const beFmt = (b) => { const v = breakeven(b); return v != null && v > 0 ? `${v.toFixed(1)} bps` : '—'; };
  const COST_BPS = [1, 2, 3, 5];
  const beA = breakeven(bA); const beB = breakeven(bB);
  const fragile = beA != null && beB != null && beA > 0 && beB > 0 ? (beA < beB ? titleA : titleB) : null;
  // Positive-month rate over each stream's OWN active months (fair across windows).
  const posMonthRate = (rows, side) => {
    const active = rows.filter((c) => (side === 'a' ? c.aN : c.bN) > 0);
    if (!active.length) return null;
    return (active.filter((c) => (side === 'a' ? c.aR : c.bR) > 0).length / active.length) * 100;
  };

  const valR = (r, s) => (s === 'a' ? r.aR : r.bR);
  const subN = (r, s) => ` (${s === 'a' ? r.aN : r.bN})`;
  const rBars = (cmp, key) => cmp.map((c) => ({ key: String(c[key] ?? c.key), ...c }));

  return (
    <div className="intel-page intel-cmp">
      {/* ---- header + controls ---- */}
      <div className="intel-hero">
        <div>
          <div className="intel-kicker">PUSU · {t('İstihbarat')}</div>
          <h2>{t('Strateji Karşılaştırma')}</h2>
          <p>{t('Backtest’teki stratejilerin çok boyutlu karşılaştırması — {a} ve {b}.', { a: titleA, b: titleB })}</p>
        </div>
        <div className="intel-controls">
          <div className="intel-pick">
            <select className="intel-select intel-select--a" value={verA} onChange={(e) => pickA(e.target.value)} aria-label="stream A">
              {STREAMS.map((s) => <option key={s.version} value={s.version}>{optLabel(s)}</option>)}
            </select>
            <span className="intel-vs">{t('vs')}</span>
            <select className="intel-select intel-select--b" value={verB} onChange={(e) => pickB(e.target.value)} aria-label="stream B">
              {STREAMS.map((s) => <option key={s.version} value={s.version}>{optLabel(s)}</option>)}
            </select>
          </div>
          <div className="seg seg--sm" role="group" aria-label="window">
            <button className={win === 'common' ? 'active' : ''} onClick={() => setWin('common')}>{t('Ortak Pencere ({y})', { y: m.commonYear })}</button>
            <button className={win === 'full' ? 'active' : ''} onClick={() => setWin('full')}>{t('Tüm Geçmiş')}</button>
          </div>
          <div className="seg seg--sm" role="group" aria-label="market">
            <button className={market === 'all' ? 'active' : ''} onClick={() => setMarket('all')}>{t('Tümü')}</button>
            {MARKETS.map((mk) => (
              <button key={mk.key} className={market === mk.key ? 'active' : ''} onClick={() => setMarket(mk.key)}>{t(mk.label)}</button>
            ))}
          </div>
        </div>
      </div>

      {win === 'full' && m.startA !== m.startB && (
        <div className="intel-note">{t('“Tüm Geçmiş”: akımlar farklı tarihlerde başlar ({a}: {ya}, {b}: {yb}) — toplam R’ler farklı pencereleri kapsar. Adil A/B için “Ortak Pencere”yi kullanın.', { a: titleA, ya: m.startA, b: titleB, yb: m.startB })}</div>
      )}

      {/* ---- verdict ---- */}
      <Section title={t('İstihbarat Değerlendirmesi')} sub={t('Aynı aile, farklı varyant — hangisi nerede önde?')} full>
        <div className="intel-verdict">
          <div className="verdict-card">
            <span className="verdict-card__k">{t('Toplam R lideri')}</span>
            <b className="verdict-card__v">{leadR}</b>
            <span className="verdict-card__d">{fmtR(bA.totalR)} {tagA} · {fmtR(bB.totalR)} {tagB}</span>
          </div>
          <div className="verdict-card">
            <span className="verdict-card__k">{t('İşlem başına verim')}</span>
            <b className="verdict-card__v">{leadEff}</b>
            <span className="verdict-card__d">{fmtExp(bA.avgR)} {tagA} · {fmtExp(bB.avgR)} {tagB}</span>
          </div>
          <div className="verdict-card">
            <span className="verdict-card__k">{t('Risk verimi (Recovery)')}</span>
            <b className="verdict-card__v">{leadRisk}</b>
            <span className="verdict-card__d">{fmtPf(bA.recovery)} {tagA} · {fmtPf(bB.recovery)} {tagB}</span>
          </div>
          <div className="verdict-card">
            <span className="verdict-card__k">{t('Günlük R korelasyonu')}</span>
            <b className="verdict-card__v">{div.corr == null ? '—' : div.corr.toFixed(2)}</b>
            <span className="verdict-card__d">{(blendHelps ? t('ikisi birden daha sağlam') : t('büyük ölçüde örtüşüyor'))} · {m.commonYear}</span>
          </div>
        </div>
      </Section>

      {/* ---- head-to-head KPI table ---- */}
      <Section title={t('Birebir Metrikler')} sub={t('▲ = o metrikte önde olan akım')}>
        <div className="h2h">
          <div className="h2h-head">
            <span />
            <b>{titleA}<i>{tagA}</i></b>
            <b>{titleB}<i>{tagB}</i></b>
          </div>
          <StatRow label={t('Toplam R')} a={bA.totalR} b={bB.totalR} fmt={fmtR} />
          <StatRow label={t('İşlem (kapanan)')} a={bA.closedN} b={bB.closedN} fmt={(v) => v.toLocaleString(locale)} neutral />
          <StatRow label={t('Win Rate')} a={bA.winRate} b={bB.winRate} fmt={fmtPct} />
          <StatRow label={t('Beklenti')} a={bA.avgR} b={bB.avgR} fmt={fmtExp} />
          <StatRow label={t('Profit Factor')} a={bA.profitFactor} b={bB.profitFactor} fmt={fmtPf} />
          <StatRow label={t('Ort. Kazanç / Kayıp')} a={bA.payoff} b={bB.payoff} fmt={(v) => (v == null ? '—' : `${v.toFixed(1)}×`)} />
          <StatRow label={t('Maks. Düşüş')} a={bA.maxDD} b={bB.maxDD} fmt={(v) => `-${v.toFixed(1)}R`} invert />
          <StatRow label={t('Recovery Factor')} a={bA.recovery} b={bB.recovery} fmt={fmtPf} hint={t('Toplam R / Maks. Düşüş')} />
          <StatRow label={t('Tutarlılık (R/σ)')} a={bA.rPerStd} b={bB.rPerStd} fmt={fmtPf} hint={t('İşlem başına R / standart sapma')} />
          <StatRow label={t('En uzun kayıp serisi')} a={bA.maxLossStreak} b={bB.maxLossStreak} fmt={(v) => String(v)} invert />
          <StatRow label={t('En kötü tek işlem')} a={bA.worstR} b={bB.worstR} fmt={(v) => `${v.toFixed(1)}R`} hint={t('Kayma/gap kaynaklı en derin tek kayıp')} />
          <StatRow label={t('R / piyasada-gün')} a={bA.rPerExposureDay} b={bB.rPerExposureDay} fmt={(v) => (v == null ? '—' : v.toFixed(2))} hint={t('Sermaye verimi: Toplam R / piyasada geçen gün')} />
          <StatRow label={t('Ort. tutma süresi')} a={bA.avgHoldHrs} b={bB.avgHoldHrs} fmt={fmtHrs} neutral />
          <StatRow label={t('Pozitif ay oranı')} a={posMonthRate(m.mo, 'a')} b={posMonthRate(m.mo, 'b')} fmt={fmtPct} hint={t('Akımın işlem yaptığı ayların yüzde kaçı pozitif')} />
          <StatRow label={t('Aylık işlem temposu')} a={bA.perMonth} b={bB.perMonth} fmt={(v) => v.toFixed(0)} neutral hint={t('Ayda kapanan işlem sayısı')} />
          <StatRow label={t('No-fill (iptal) oranı')} a={bA.cancelRate} b={bB.cancelRate} fmt={fmtPct} invert />
        </div>
      </Section>

      {/* ---- equity overlay ---- */}
      <Section title={t('Sermaye Eğrisi — üst üste')} sub={t('Her iki akım ortak zaman ekseninde; eğrinin ŞEKLİ edge’i anlatır.')} full>
        <div className="overview-card">
          <MiniCurve series={curve} height={190} />
        </div>
      </Section>

      <div className="intel-grid-2">
        {/* ---- drawdown ---- */}
        <Section title={t('Sualtı (Drawdown) Eğrisi')} sub={t('Tepe altında geçen R — derinlik ve süre = acı eşiği.')}>
          <div className="overview-card">
            <MiniCurve series={drawdownCurve} height={150} />
            <div className="intel-readout">
              <span>{titleA}: <b className="loss">-{bA.maxDD.toFixed(1)}R</b> · {bA.maxDDDays.toFixed(0)}{t('g')}</span>
              <span>{titleB}: <b className="loss">-{bB.maxDD.toFixed(1)}R</b> · {bB.maxDDDays.toFixed(0)}{t('g')}</span>
            </div>
          </div>
        </Section>

        {/* ---- asymmetry / distribution ---- */}
        <Section title={t('Asimetri — az kazan, büyük kazan')} sub={t('RR=4 tam-TP → çıktı iki kutuplu: −1R (SL) ya da +4R (TP).')}>
          <div className="overview-card intel-asym">
            {[{ b: bA, tag: tagA, c: SERIES_A }, { b: bB, tag: tagB, c: SERIES_B }].map(({ b, tag, c }) => (
              <div key={tag} className="asym-block">
                <div className="asym-block__h"><i style={{ background: c }} />{tag}</div>
                <div className="asym-split">
                  <span className="asym-seg win" style={{ flex: Math.max(0.04, b.winRate) }}>{b.winRate.toFixed(0)}%</span>
                  <span className="asym-seg loss" style={{ flex: Math.max(0.04, 100 - b.winRate) }}>{(100 - b.winRate).toFixed(0)}%</span>
                </div>
                <div className="asym-meta">
                  <span>{t('Ort. kazanç')} <b className="win">+{b.avgWin.toFixed(2)}R</b></span>
                  <span>{t('Ort. kayıp')} <b className="loss">-{b.avgLoss.toFixed(2)}R</b></span>
                  <span>{t('Kazanç süresi')} <b>{fmtHrs(b.avgWinHoldHrs)}</b></span>
                  <span>{t('Kayıp süresi')} <b>{fmtHrs(b.avgLossHoldHrs)}</b></span>
                </div>
              </div>
            ))}
            <div className="asym-foot">{t('Kazananlar kaybedenlerden ~2× daha uzun tutuluyor — “kayıpları kes, kazananları koştur” imzası.')}</div>
          </div>
        </Section>
      </div>

      {/* ---- per-symbol head-to-head ---- */}
      <Section title={t('Sembol Bazında Birebir')} sub={t('Her sembolde hangi akım daha çok R üretti (R’ye göre sıralı).')} full>
        <div className="overview-card">
          <CompareBars rows={rBars(sym, 'symbol')} valueOf={valR} subOf={subN}
                       labelA={`${titleA} (${tagA})`} labelB={`${titleB} (${tagB})`} fmt={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}R`} scroll />
        </div>
      </Section>

      <div className="intel-grid-2">
        {/* ---- market buckets ---- */}
        <Section title={t('Piyasa Sınıfı')} sub={t('Kripto / metal / ABD hisse — trend edge’i nerede?')}>
          <div className="overview-card">
            <CompareBars rows={m.mkt.map((c) => ({ ...c, key: c.key, label: t({ crypto: 'Kripto', metal: 'Metal', stock: 'ABD Hisse' }[c.key]) }))}
                         valueOf={valR} subOf={subN} labelA={tagA} labelB={tagB} fmt={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}R`} />
          </div>
        </Section>

        {/* ---- direction ---- */}
        <Section title={t('Yön — Long / Short')} sub={t('Kırılım yönü bazında R ve isabet.')}>
          <div className="overview-card">
            <CompareBars rows={m.dir.map((c) => ({ ...c, key: c.key, label: c.key === 'LONG' ? t('Long ↗') : t('Short ↘') }))}
                         valueOf={valR} subOf={subN} labelA={tagA} labelB={tagB} fmt={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}R`} />
          </div>
        </Section>
      </div>

      {/* ---- monthly ---- */}
      <Section title={t('Aylık Getiri')} sub={win === 'common' ? t('Ortak penceredeki her ayın net R’si — tutarlılık ve eş-zamanlılık.') : t('Seçili penceredeki her ayın net R’si — tutarlılık ve eş-zamanlılık.')} full>
        <div className="overview-card">
          <CompareBars rows={m.mo.map((c) => ({ ...c, key: c.key, label: new Date(`${c.key}-01T00:00:00Z`).toLocaleDateString(locale, { month: 'short', year: '2-digit' }) }))}
                       valueOf={valR} subOf={subN} labelA={`${titleA} (${tagA})`} labelB={`${titleB} (${tagB})`} fmt={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}R`} scroll />
        </div>
      </Section>

      <div className="intel-grid-2">
        {/* ---- weekday ---- */}
        <Section title={t('Haftanın Günü')} sub={t('Sinyal gününe göre R (UTC).')}>
          <div className="overview-card">
            <CompareBars rows={m.wd.map((c) => ({ ...c, key: c.key, label: t(c.key) }))}
                         valueOf={valR} subOf={subN} labelA={tagA} labelB={tagB} fmt={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}R`} />
          </div>
        </Section>

        {/* ---- hour of day ---- */}
        <Section title={t('Günün Saati (UTC)')} sub={t('Kırılımın saatine göre R — seans etkisi.')}>
          <div className="overview-card">
            <CompareBars rows={m.hr.map((c) => ({ ...c, key: String(c.key), label: `${String(c.key).padStart(2, '0')}:00` }))}
                         valueOf={valR} subOf={subN} labelA={tagA} labelB={tagB} fmt={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}R`} scroll />
          </div>
        </Section>
      </div>

      {/* ---- cost / slippage sensitivity ---- */}
      <Section title={t('Maliyet Duyarlılığı')} sub={t('Backtest %0.1 round-trip’i zaten içerir; aşağısı EK kaymadır (bps/yön). Düşük WR + yüksek frekans bu stratejileri kaymaya çok duyarlı yapar.')} full>
        <div className="h2h">
          <div className="h2h-head">
            <span>{t('Ek kayma')}</span>
            <b>{titleA}<i>{tagA}</i></b>
            <b>{titleB}<i>{tagB}</i></b>
          </div>
          <StatRow label={t('Backtest (gömülü maliyet)')} a={bA.totalR} b={bB.totalR} fmt={fmtR} />
          {COST_BPS.map((bps) => (
            <StatRow key={bps} label={`+${bps} bps/${t('yön')}`} a={netAfter(bA, bps)} b={netAfter(bB, bps)} fmt={fmtR} />
          ))}
          <StatRow label={t('Başabaş ek kayma')} a={beA} b={beB} fmt={(v) => (v != null && v > 0 ? `${v.toFixed(1)} bps` : '—')} hint={t('Net R’yi sıfıra indiren ek kayma (yüksek = dayanıklı)')} />
        </div>
        <div className="intel-foot">
          {fragile
            ? t('{f} kaymaya daha kırılgan (daha sık işlem ve/veya daha kısa risk mesafesi) — başabaş {a} ≈ {x}, {b} ≈ {y}.', { f: fragile, a: titleA, x: beFmt(bA), b: titleB, y: beFmt(bB) })
            : t('Başabaş ek kayma: {a} ≈ {x}, {b} ≈ {y}.', { a: titleA, x: beFmt(bA), b: titleB, y: beFmt(bB) })}
        </div>
      </Section>

      {/* ---- diversification / blend ---- */}
      <Section title={t('Çeşitlendirme — ikisini birden çalıştırmak')} sub={t('İki akım ikame mi, tamamlayıcı mı? Düşük korelasyon + daha iyi Recovery = tamamlayıcı.')} full>
        <div className="overview-card">
          <MiniCurve series={blendCurve} height={190} />
          <div className="intel-readout intel-readout--wide">
            <span>{t('Günlük R korelasyonu')} <b>{div.corr == null ? '—' : div.corr.toFixed(2)}</b></span>
            <span>{t('İkisi birden Toplam R')} <b className="win">{fmtR(div.blendTotal)}</b></span>
            <span>{t('İkisi birden Maks. Düşüş')} <b className="loss">-{div.blendMaxDD.toFixed(1)}R</b></span>
            <span>{t('İkisi birden Recovery')} <b>{fmtPf(div.blendRecovery)}</b> {t('(en iyi tek: {x})', { x: fmtPf(bestSingleRec) })}</span>
            <span>{t('Aynı gün ikisi de işlemde')} <b>{div.days ? ((div.bothDays / div.days) * 100).toFixed(0) : 0}%</b></span>
          </div>
          <div className="intel-foot">
            {blendHelps
              ? t('İkisini birlikte çalıştırmak, en iyi tek akımdan daha yüksek risk verimi (Recovery) veriyor — akımlar birbirini tamamlıyor.')
              : t('Eğriler büyük ölçüde örtüşüyor — birini seçmek, ikisini birden çalıştırmaya yakın sonuç verir.')}
          </div>
        </div>
      </Section>

      {/* ---- multi-year OOS ---- */}
      <Section title={t('Yıllara Göre (Örneklem-dışı)')} sub={t('Akımlar farklı sayıda yıl kapsar — çok-yıla yayılan akım tek bir yıla overfit değildir.')} full>
        <div className="overview-card">
          <CompareBars rows={m.yr.map((c) => ({ ...c, key: c.key, label: c.key }))}
                       valueOf={valR} subOf={subN} labelA={`${titleA} (${tagA})`} labelB={`${titleB} (${tagB})`} fmt={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}R`} />
          <div className="intel-foot">{t('Yıl bazında karşılaştırma daima tüm geçmişi kullanır (pencere filtresinden bağımsız).')}</div>
        </div>
      </Section>
    </div>
  );
};

export default IntelligencePage;
