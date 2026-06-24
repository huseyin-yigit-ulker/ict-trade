import { useState, useMemo, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useLang } from '../context/LanguageContext';
import { useTradeContext } from '../context/TradeContext';
import './DemoView.css';

// Demo-faithful backtest view: the REAL live-executor portfolio logic (one position per symbol,
// opposite signal reverses, same-direction ignored) replayed over history — distinct from the
// "take every signal" backtest. The trades live in the SAME backtest table the dashboard reads
// (ict_trade.trading_signals, version='<cap>_demo', written by sync/live_exec/demo_backtest.py),
// so this is just a backtest stream + the portfolio rule. Laid out like the backtest dashboard:
// a KPI hero + a Years -> Months -> Days drill that opens the day's trade cards. One cap each.

const CAP_TABS = [
  { key: 'd30_4h_soc', label: '4R' },
  { key: 'd30so6c', label: '6R' },
  { key: 'd30so8c', label: '8R' },
];
const CAP_LABEL = {
  d30_4h_soc: 'DONCHIAN 30m+4h·WR 4R ·0.5R',
  d30so6c: 'DONCHIAN 30m+4h·WR 6R ·0.5R',
  d30so8c: 'DONCHIAN 30m+4h·WR 8R ·0.5R',
};
// cap strategy key -> demo backtest version tag in the DB (varchar(10))
const DEMO_VERSION = { d30_4h_soc: 'demo4', d30so6c: 'demo6', d30so8c: 'demo8' };

// Pull this cap's demo rows from the backtest DB (paginated, like TradeContext.fetchAllBacktestRows)
// and map them to the compact trade shape the cards render. version = '<cap>_demo'.
async function fetchDemoTrades(strategyKey) {
  const url = import.meta.env.BACKTESTING_VITE_SUPABASE_URL;
  const key = import.meta.env.BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
  if (!url || !key) throw new Error('no-db-config');
  const raw = (import.meta.env.BACKTESTING_DB_TABLE || 'ict_trade.trading_signals')
    .toString().trim().replace(/^["']|["']$/g, '');
  const [schema, table] = raw.includes('.') ? raw.split('.') : ['ict_trade', raw];
  const p = new URLSearchParams({
    select: 'symbol,direction,entry_price,sl_price,tp_price,signal_time,real_entry_time,exit_time,exit_price,status,pnl_r',
    order: 'signal_time.desc',
  });
  p.append('version', `eq.${DEMO_VERSION[strategyKey] || strategyKey}`);
  const endpoint = `${url}/rest/v1/${table}?${p.toString()}`;
  const pageSize = 1000;
  const rows = [];
  for (let from = 0; ; from += pageSize) {
    const res = await fetch(endpoint, {
      headers: { apikey: key, Authorization: `Bearer ${key}`, 'Accept-Profile': schema,
                 'Range-Unit': 'items', Range: `${from}-${from + pageSize - 1}` },
    });
    if (!res.ok) throw new Error(`db-${res.status}`);
    const page = await res.json();
    if (!Array.isArray(page) || page.length === 0) break;
    rows.push(...page);
    if (page.length < pageSize) break;
  }
  // status -> card outcome. A scale-out runner that's stopped at breakeven AFTER TP1 exits AT entry
  // (exit_price == entry_price) with the 60% still banked (~+0.6R) — the resolver tags it closed_tp,
  // but it's really a breakeven runner, so show it as BE (not a clean TP).
  const outcome = (r) => {
    const x = (r.status || '').toLowerCase();
    if (x.includes('sl')) return 'SL';
    if (x.includes('active')) return 'OPEN';
    if (x.includes('tp')) {
      const e = Number(r.entry_price), xp = Number(r.exit_price);
      if (Number.isFinite(e) && Number.isFinite(xp) && Math.abs(xp - e) <= Math.abs(e) * 1e-6) return 'BE';
      return 'TP';
    }
    return 'TP';
  };
  return rows
    .filter((r) => r.exit_time && r.pnl_r != null)   // realized only (skip still-riding/active)
    .map((r) => ({
      s: r.symbol,
      d: String(r.direction || '').toUpperCase().startsWith('S') ? 'short' : 'long',
      e: Number(r.entry_price), sl: Number(r.sl_price), tp: Number(r.tp_price),
      sig: r.signal_time, in: r.real_entry_time, out: r.exit_time,
      r: Number(r.pnl_r), o: outcome(r),
    }));
}

const MONTHS_FULL = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
const MONTHS_SHORT = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];

const fmtR = (v) => `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}R`;
const usd = (r) => `${Number(r) >= 0 ? '+' : '-'}$${Math.abs(Number(r) * 5).toFixed(0)}`;

// price formatter — scales decimals to magnitude (BTC ~100000 ... DOGE ~0.3)
const fmtPx = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return '--';
  const a = Math.abs(n);
  const dp = a >= 1000 ? 2 : a >= 1 ? 3 : a >= 0.01 ? 5 : 7;
  return n.toFixed(dp);
};

// how a demo position left the book → display label + color class (R sign is authoritative)
const OUTCOMES = {
  TP: { key: 'TP', cls: 'win' }, BE: { key: 'BE', cls: 'waiting' }, SL: { key: 'SL', cls: 'loss' },
  REV: { key: 'Ters', cls: '' }, OPEN: { key: 'Açık', cls: 'waiting' },
};
const outClass = (tr) => (tr.o === 'OPEN' ? 'waiting' : tr.r > 0 ? 'win' : tr.r < 0 ? 'loss' : 'waiting');

// chronological bucket (win = R>0, loss = R<0) keyed by a slice of the exit ISO (UTC)
function bucketize(trades, sliceLen) {
  const m = new Map();
  for (const tr of trades) {
    const k = tr.out.slice(0, sliceLen);
    (m.get(k) || m.set(k, []).get(k)).push(tr);
  }
  return [...m.entries()]
    .map(([key, list]) => {
      let tp = 0, sl = 0, totalR = 0;
      for (const x of list) { totalR += x.r; if (x.r > 0) tp += 1; else if (x.r < 0) sl += 1; }
      return { key, list, count: list.length, tp, sl, totalR };
    })
    .sort((a, b) => (a.key < b.key ? 1 : -1));
}

// per-bucket R bar (scaled to the level's max |R|) — mirrors the backtest drill
function RBar({ totalR, maxAbs }) {
  return (
    <div className="drill-rbar">
      <div className="drill-rbar__fill"
           style={{ width: `${Math.min(100, (Math.abs(totalR) / (maxAbs || 1)) * 100)}%`,
                    background: totalR >= 0 ? 'var(--win)' : 'var(--loss)' }} />
    </div>
  );
}

const WinLossBar = ({ tp, sl }) => {
  const total = tp + sl;
  if (!total) return null;
  return (
    <span className="wl-bar" title={`Kazanan ${tp} · Kaybeden ${sl}`}>
      <span className="wl-bar__tp" style={{ width: `${(tp / total) * 100}%` }} />
    </span>
  );
};

// demo trade record -> the signal shape ChartModal renders. The chart pulls klines straight from
// Binance and re-derives the entry-fill / TP1 / runner-cap geometry from these fields (exactly like
// a backtest row), so it needs the SIGNAL-bar time (`sig`), the exit time, and entry/sl/tp/dir.
function toSignal(tr, strategyKey) {
  return {
    id: `demo-${strategyKey}-${tr.s}-${tr.sig}`,
    symbol: tr.s,
    dir: tr.d === 'long' ? 'LONG' : 'SHORT',
    entry: tr.e, sl: tr.sl, tp: tr.tp,
    dateObj: new Date(tr.sig),
    exitTs: tr.out ? new Date(tr.out).getTime() : null,
    entryFillTs: tr.in ? new Date(tr.in).getTime() : null,
    pnlR: tr.r,
    status: tr.o === 'OPEN' ? 'ACTIVE' : tr.r >= 0 ? 'TP' : 'SL',
    ltfTimeframe: '30m',
    htfTimeframe: '4h',
    strategy: strategyKey,
  };
}

// ---- one demo trade card (mirrors the backtest card; portfolio-faithful R) ----
function DemoTradeCard({ tr, t, onOpen }) {
  const long = tr.d === 'long';
  const oc = OUTCOMES[tr.o] || OUTCOMES.TP;
  const pnlCls = outClass(tr);
  const timeLabel = `${tr.out.slice(11, 16)} UTC`;
  const rr = Math.abs(tr.tp - tr.e) / (Math.abs(tr.e - tr.sl) || 1);
  return (
    <div className={`trade-card trade-card--${long ? 'long' : 'short'}`}
         role="button" tabIndex={0} style={{ cursor: 'pointer' }}
         onClick={() => onOpen(tr)}
         onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(tr); } }}>
      <div className="intel-head">
        <span className="symbol-box">{tr.s}</span>
        <span className={`dir-badge ${long ? 'long' : 'short'}`}>
          <span className="dir-arrow" aria-hidden="true">{long ? '↗' : '↘'}</span>
          {long ? 'LONG' : 'SHORT'}
        </span>
        <span className="time-detail">{timeLabel}</span>
        {Number.isFinite(rr) && <span className="rr-pill" title={`Risk-Reward · 1:${rr.toFixed(2)}`}>1:{rr.toFixed(2)}</span>}
      </div>
      <div className="intel-exec">
        <div className="trade-body intel-exec__grid">
          <div className="trade-metric">
            <span className="metric-label">{t('Durum')}</span>
            <span className={`status-text ${oc.cls || pnlCls}`}>{t(oc.key)}</span>
          </div>
          <div className="trade-metric">
            <span className="metric-label">{t('P/L')}</span>
            <span className={`pnl-text ${pnlCls}`}>{tr.o === 'OPEN' ? '--' : `${fmtR(tr.r)} · ${usd(tr.r)}`}</span>
          </div>
          <div className="trade-metric">
            <span className="metric-label">{t('Entry')} ·0.5R</span>
            <span className="metric-value">{fmtPx(tr.e)}</span>
          </div>
          <div className="trade-metric intel-exec__tpsl">
            <span className="metric-label">{t('Hedef')} / {t('Risk')}</span>
            <span className="metric-value">
              <span className="win">{fmtPx(tr.tp)}</span>
              <span className="intel-sep"> · </span>
              <span className="loss">{fmtPx(tr.sl)}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DemoView({ strategyKey }) {
  const { t } = useLang();
  const { setActiveSignal, setChartView } = useTradeContext();

  // this cap's demo rows, fetched from the backtest DB (version='<cap>_demo'). Single state object
  // (set only in the async callbacks) + derived view, so a cap switch shows 'loading' WITHOUT a
  // synchronous setState in the effect body.
  const [fetched, setFetched] = useState({ key: null, status: 'loading', trades: [] });
  useEffect(() => {
    let alive = true;
    fetchDemoTrades(strategyKey)
      .then((tr) => alive && setFetched({ key: strategyKey, status: tr.length ? 'ok' : 'empty', trades: tr }))
      .catch(() => alive && setFetched({ key: strategyKey, status: 'error', trades: [] }));
    return () => { alive = false; };
  }, [strategyKey]);
  const ready = fetched.key === strategyKey;
  const status = ready ? fetched.status : 'loading';
  const trades = useMemo(() => (ready ? fetched.trades : []), [ready, fetched.trades]);

  // open the SAME chart the backtest uses (ChartModal, mounted globally in AppShell)
  const openChart = (tr) => { setChartView('journal'); setActiveSignal(toSignal(tr, strategyKey)); };

  // Years -> Months -> Days drill state. 2026 is the priority default.
  const yearBuckets = useMemo(() => bucketize(trades, 4), [trades]);
  const [selYear, setSelYear] = useState('2026');
  const [selMonth, setSelMonth] = useState('');
  const [selDay, setSelDay] = useState('');

  const activeYear = yearBuckets.some((y) => y.key === selYear)
    ? selYear : (yearBuckets[0]?.key ?? null);
  const yearTrades = useMemo(
    () => (activeYear ? trades.filter((tr) => tr.out.slice(0, 4) === activeYear) : []),
    [trades, activeYear],
  );
  const monthBuckets = useMemo(() => bucketize(yearTrades, 7), [yearTrades]);
  const monthTrades = useMemo(
    () => (selMonth ? yearTrades.filter((tr) => tr.out.slice(0, 7) === selMonth) : []),
    [yearTrades, selMonth],
  );
  const dayBuckets = useMemo(() => bucketize(monthTrades, 10), [monthTrades]);
  const dayTrades = useMemo(
    () => monthTrades.filter((tr) => tr.out.slice(0, 10) === selDay)
      .sort((a, b) => (a.out < b.out ? 1 : -1)),
    [monthTrades, selDay],
  );

  // all-time KPIs for this cap, computed straight from the trade list
  const kpi = useMemo(() => {
    let tp = 0, sl = 0, totalR = 0;
    for (const x of trades) { totalR += x.r; if (x.r > 0) tp += 1; else if (x.r < 0) sl += 1; }
    const closed = tp + sl;
    return { tp, sl, totalR, closed, n: trades.length,
             wr: closed ? (tp / closed) * 100 : 0, exp: closed ? totalR / closed : 0 };
  }, [trades]);

  if (status !== 'ok') {
    const msg = status === 'loading' ? t('Demo verisi yükleniyor…')
      : status === 'error' ? t('Demo verisi alınamadı (DB).')
      : t('Demo backtest verisi henüz hesaplanmadı. (sync/live_exec/demo_backtest.py çalıştır)');
    return (
      <div className="demo">
        <div className="demo__head"><h1>{CAP_LABEL[strategyKey] || t('Demo')}</h1><span className="demo__badge">DEMO</span></div>
        <div className="demo__empty">{msg}</div>
      </div>
    );
  }

  const symbolCount = new Set(trades.map((x) => x.s)).size;
  const pickYear = (y) => { setSelYear(y); setSelMonth(''); setSelDay(''); };
  const monthLabel = (key) => { const [y, m] = key.split('-'); return `${MONTHS_FULL[+m - 1]} ${y}`; };
  const dayLabel = (key) => { const [, m, d] = key.split('-'); return `${+d} ${MONTHS_SHORT[+m - 1]}`; };
  const yearsMaxR = Math.max(1, ...yearBuckets.map((b) => Math.abs(b.totalR)));
  const monthsMaxR = Math.max(1, ...monthBuckets.map((b) => Math.abs(b.totalR)));
  const daysMaxR = Math.max(1, ...dayBuckets.map((b) => Math.abs(b.totalR)));
  const selDayBucket = dayBuckets.find((d) => d.key === selDay);

  return (
    <div className="demo">
      <div className="demo__head">
        <h1>{CAP_LABEL[strategyKey] || t('Demo')}</h1>
        <span className="demo__badge">DEMO</span>
        <span className="demo__tabs">
          {CAP_TABS.map((c) => (
            <Link key={c.key} to={`/${c.key}/demo`}
                  className={`demo__tab ${c.key === strategyKey ? 'active' : ''}`}>{c.label}</Link>
          ))}
        </span>
        <span className="demo__gen">{trades.length} {t('işlem')} · {symbolCount} sembol</span>
      </div>

      <div className="demo__note">
        {t('Gerçek demo mantığı: sembol başına tek pozisyon · ters sinyal pozisyonu çevirir · aynı yön yok sayılır. ("Her sinyali al" backtestinden farklı, daha düşük ama gerçekçi.)')}
      </div>

      {/* KPI hero (all-time, this cap) */}
      <div className="kpi-hero">
        <div className="kpi-cell">
          <div className="kpi-cell__label">{t('Win Rate')}</div>
          <div className="kpi-cell__value">{kpi.wr.toFixed(1)}%</div>
          <div className="kpi-cell__sub">{kpi.closed} {t('kapanan')}</div>
        </div>
        <div className="kpi-cell kpi-cell--wide">
          <div className="kpi-cell__label">{t('Toplam R')}</div>
          <div className={`kpi-cell__value ${kpi.totalR >= 0 ? 'win' : 'loss'}`}>
            {kpi.totalR >= 0 ? '+' : ''}{kpi.totalR.toFixed(1)}R
          </div>
          <div className="kpi-cell__sub">{usd(kpi.totalR)}</div>
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell__label">{t('Beklenti')}</div>
          <div className={`kpi-cell__value ${kpi.exp >= 0 ? 'win' : 'loss'}`}>
            {kpi.exp >= 0 ? '+' : ''}{kpi.exp.toFixed(2)}R
          </div>
          <div className="kpi-cell__sub">{t('işlem başına')}</div>
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell__label">{t('İşlem')}</div>
          <div className="kpi-cell__value">{kpi.n}</div>
          <div className="kpi-cell__sub">{t('toplam')}</div>
        </div>
      </div>

      {/* Years -> Months -> Days drill */}
      <div className="drill-header">
        <div className="drill-path">
          {!selMonth && `${activeYear || ''} / ${t('Aylar')}`}
          {selMonth && `${selMonth.split('-')[0]} / ${MONTHS_FULL[+selMonth.split('-')[1] - 1]} / ${t('Günler')}`}
        </div>
        <div className="drill-actions">
          {selMonth && (
            <button className="drill-back-btn" onClick={() => { setSelMonth(''); setSelDay(''); }}>
              {t('Aylara Dön')}
            </button>
          )}
        </div>
      </div>

      {/* year selector row */}
      <div className="drill-grid years">
        {yearBuckets.map((y) => (
          <button key={y.key} className={`drill-card ${y.key === activeYear ? 'active' : ''}`}
                  onClick={() => pickYear(y.key)}>
            <div className="drill-title">{y.key}{y.key === '2026' ? ' ★' : ''}</div>
            <div className="drill-meta">{y.count} {t('işlem')}</div>
            <div className="drill-meta">K/Z: <span className="win">{y.tp}</span>/<span className="loss">{y.sl}</span></div>
            <div className={`drill-r ${y.totalR >= 0 ? 'win' : 'loss'}`}>{y.totalR >= 0 ? '+' : ''}{y.totalR.toFixed(2)}R</div>
            <RBar totalR={y.totalR} maxAbs={yearsMaxR} />
          </button>
        ))}
      </div>

      {!selMonth && (
        <div className="drill-grid months">
          {monthBuckets.map((m) => (
            <button key={m.key} className="drill-card" onClick={() => { setSelMonth(m.key); setSelDay(''); }}>
              <div className="drill-title">{monthLabel(m.key)}</div>
              <div className="drill-meta">{m.count} {t('işlem')}</div>
              <div className="drill-meta">K/Z: <span className="win">{m.tp}</span>/<span className="loss">{m.sl}</span></div>
              <div className={`drill-r ${m.totalR >= 0 ? 'win' : 'loss'}`}>{m.totalR >= 0 ? '+' : ''}{m.totalR.toFixed(2)}R</div>
              <RBar totalR={m.totalR} maxAbs={monthsMaxR} />
            </button>
          ))}
        </div>
      )}

      {selMonth && (
        <>
          <div className="drill-grid days">
            {dayBuckets.map((d) => (
              <button key={d.key} className={`drill-card ${selDay === d.key ? 'active' : ''}`}
                      onClick={() => setSelDay(d.key)}>
                <div className="drill-title">{dayLabel(d.key)}</div>
                <div className="drill-meta">{d.count} {t('işlem')}</div>
                <div className="drill-meta">K/Z: <span className="win">{d.tp}</span>/<span className="loss">{d.sl}</span></div>
                <div className={`drill-r ${d.totalR >= 0 ? 'win' : 'loss'}`}>{d.totalR >= 0 ? '+' : ''}{d.totalR.toFixed(2)}R</div>
                <RBar totalR={d.totalR} maxAbs={daysMaxR} />
              </button>
            ))}
          </div>

          {selDay && dayTrades.length > 0 && (
            <div className="day-notebook">
              <div className="day-header">
                <div className="day-title">{`${+selDay.split('-')[2]} ${monthLabel(selDay.slice(0, 7))}`}</div>
                <div className="day-summary">
                  <span>{dayTrades.length} {t('işlem')}</span>
                  {selDayBucket && <WinLossBar tp={selDayBucket.tp} sl={selDayBucket.sl} />}
                  {selDayBucket && (
                    <span className="tp-sl-ratio">
                      {t('Toplam R')}:{' '}
                      <span className={selDayBucket.totalR >= 0 ? 'win' : 'loss'}>
                        {selDayBucket.totalR >= 0 ? '+' : ''}{selDayBucket.totalR.toFixed(2)}
                      </span>
                    </span>
                  )}
                </div>
              </div>
              <div className="trade-grid">
                {dayTrades.map((tr, i) => (
                  <DemoTradeCard key={`${tr.s}-${tr.out}-${i}`} tr={tr} t={t} onOpen={openChart} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
