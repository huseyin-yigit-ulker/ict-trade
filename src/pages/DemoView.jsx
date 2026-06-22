import { Link } from 'react-router-dom';
import { useLang } from '../context/LanguageContext';
import demoData from '../data/demoBacktest.json';
import './DemoView.css';

// Demo-faithful backtest view: the REAL live-executor portfolio logic (one position per symbol,
// opposite signal reverses, same-direction ignored) replayed over 2024/2025/2026 — distinct from
// the "take every signal" backtest. Data is precomputed by sync/live_exec/demo_backtest.py into
// src/data/demoBacktest.json (no DB / no grant). Each scale-out strategy (4R/6R/8R) has its own cap.

const CAP_TABS = [
  { key: 'd30_4h_soc', label: '4R' },
  { key: 'd30so6c', label: '6R' },
  { key: 'd30so8c', label: '8R' },
];
const YEARS = ['2024', '2025', '2026'];

const fmtR = (v) => `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(1)}R`;
const usd = (r) => `${Number(r) >= 0 ? '+' : '-'}$${Math.abs(Number(r) * 5).toFixed(0)}`;

// ---- cumulative-R equity curve (monthly points across the full span) ----
function EquityChart({ equity, t }) {
  if (!equity || equity.length < 2) return null;
  const W = 1000, H = 200, pad = 8;
  const vals = equity.map((p) => p.cumR);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const span = hi - lo || 1;
  const n = equity.length;
  const x = (i) => (i / (n - 1)) * W;
  const y = (v) => H - pad - ((v - lo) / span) * (H - pad * 2);
  const line = equity.map((p, i) => `${x(i).toFixed(1)},${y(p.cumR).toFixed(1)}`).join(' ');
  const zeroY = y(0);
  const total = vals[n - 1];
  const pos = total >= 0;
  // year boundary ticks
  const ticks = [];
  equity.forEach((p, i) => { if (p.m.endsWith('-01')) ticks.push({ i, label: p.m.slice(0, 4) }); });
  return (
    <div className="demo-card demo-equity">
      <div className="demo-card__head">
        <span>{t('Sermaye Eğrisi (kümülatif R)')}</span>
        <b className={pos ? 'pos' : 'neg'}>{fmtR(total)}</b>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="demo-equity__svg">
        <defs>
          <linearGradient id="demoeq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={pos ? 'var(--win-soft)' : 'var(--loss-soft)'} />
            <stop offset="100%" stopColor="transparent" />
          </linearGradient>
        </defs>
        <polygon points={`0,${zeroY.toFixed(1)} ${line} ${W},${zeroY.toFixed(1)}`} fill="url(#demoeq)" />
        <line x1="0" y1={zeroY.toFixed(1)} x2={W} y2={zeroY.toFixed(1)} stroke="var(--muted)"
              strokeDasharray="3 3" strokeWidth="1" vectorEffect="non-scaling-stroke" opacity="0.5" />
        {ticks.map((tk) => (
          <line key={tk.i} x1={x(tk.i).toFixed(1)} y1={pad} x2={x(tk.i).toFixed(1)} y2={H - pad}
                stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        <polyline points={line} fill="none" stroke={pos ? 'var(--win)' : 'var(--loss)'} strokeWidth="2"
                  strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="demo-equity__ticks">
        {ticks.map((tk) => <span key={tk.i}>{tk.label}</span>)}
      </div>
    </div>
  );
}

// ---- per-symbol horizontal bars ----
function SymbolBars({ rows, t }) {
  if (!rows || !rows.length) return null;
  const max = Math.max(...rows.map((r) => Math.abs(r.r)), 1);
  return (
    <div className="demo-card">
      <div className="demo-card__head"><span>{t('Sembol Bazında (tüm dönem)')}</span></div>
      <div className="demo-bars">
        {rows.map((r) => (
          <div key={r.s} className="demo-bar-row">
            <span className="demo-bar-row__sym mono">{r.s.replace('USDT', '')}</span>
            <div className="demo-bar-row__track">
              <div className={`demo-bar-row__fill ${r.r >= 0 ? 'pos' : 'neg'}`}
                   style={{ width: `${(Math.abs(r.r) / max) * 100}%` }} />
            </div>
            <span className={`demo-bar-row__r mono ${r.r >= 0 ? 'pos' : 'neg'}`}>{fmtR(r.r)}</span>
            <span className="demo-bar-row__wr">{r.wr}% · {r.n}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DemoView({ strategyKey }) {
  const { t } = useLang();
  const data = demoData?.caps?.[strategyKey];

  if (!data || !data.years) {
    return (
      <div className="demo">
        <div className="demo__head"><h1>{t('Demo')}</h1></div>
        <div className="demo__empty">
          {t('Demo backtest verisi henüz hesaplanmadı. (sync/live_exec/demo_backtest.py çalıştır)')}
        </div>
      </div>
    );
  }

  const at = data.allTime;
  return (
    <div className="demo">
      <div className="demo__head">
        <h1>{data.label}</h1>
        <span className="demo__badge">DEMO</span>
        <span className="demo__tabs">
          {CAP_TABS.map((c) => (
            <Link key={c.key} to={`/${c.key}/demo`}
                  className={`demo__tab ${c.key === strategyKey ? 'active' : ''}`}>{c.label}</Link>
          ))}
        </span>
        <span className="demo__gen">{demoData.generated} · {demoData.universe.length} sembol</span>
      </div>

      <div className="demo__note">
        {t('Gerçek demo mantığı: sembol başına tek pozisyon · ters sinyal pozisyonu çevirir · aynı yön yok sayılır. ("Her sinyali al" backtestinden farklı, daha düşük ama gerçekçi.)')}
      </div>

      {/* KPI: all-time + per year */}
      <div className="demo__kpis">
        <div className="demo-kpi demo-kpi--big">
          <span>{t('Tüm Dönem')}</span>
          <b className={at.totalR >= 0 ? 'pos' : 'neg'}>{fmtR(at.totalR)}</b>
          <small>{usd(at.totalR)} · WR {at.wr}% · {at.trades} {t('işlem')}</small>
        </div>
        {YEARS.map((y) => {
          const yr = data.years[y];
          if (!yr || yr.trades === 0) {
            return (
              <div key={y} className="demo-kpi demo-kpi--empty">
                <span>{y}</span><b>—</b><small>{t('veri bekleniyor')}</small>
              </div>
            );
          }
          return (
            <div key={y} className="demo-kpi">
              <span>{y}{y === '2026' ? ' (kısmi)' : ''}</span>
              <b className={yr.totalR >= 0 ? 'pos' : 'neg'}>{fmtR(yr.totalR)}</b>
              <small>WR {yr.wr}% · {yr.trades} {t('işlem')}</small>
            </div>
          );
        })}
      </div>

      <EquityChart equity={data.equity} t={t} />
      <SymbolBars rows={data.perSymbolAll} t={t} />
    </div>
  );
}
