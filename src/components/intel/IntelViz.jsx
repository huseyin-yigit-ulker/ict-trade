import { useId } from 'react';
import { useLang } from '../../context/LanguageContext';

// Shared presentational primitives for the Intelligence comparison surface.
// Pure/stateless: feed them numbers, they draw. All colours come from the theme
// CSS vars (or explicit per-series colours for multi-line overlays where the two
// streams must be told apart regardless of sign).

// Two fixed data-series hues for the A/B streams (used by line overlays where
// win/loss colouring would be meaningless — a cumulative curve is one direction).
export const SERIES_A = '#F5B942'; // donchian 1h — accent amber
export const SERIES_B = '#5C93FF'; // dch30_4h (30m+4h hybrid) — blue
export const SERIES_BLEND = '#0ECB81'; // both books together — win green

const fmtTs = (ts, locale) =>
  new Date(ts).toLocaleDateString(locale, { month: 'short', year: '2-digit' });

// Multi-series cumulative-R-vs-time overlay. Every series is drawn on a SHARED
// time x-axis and R y-axis, so two streams with different trade counts stay
// comparable (denser stream isn't stretched). series: [{ points:[{ts,cum}],
// color, label, valueLabel, dash, area }].
export const MiniCurve = ({ series, height = 170, showLegend = true }) => {
  const { locale } = useLang();
  const gid = useId();
  const all = series.filter((s) => s.points && s.points.length >= 2);
  if (all.length === 0) return <div className="intel-empty">—</div>;

  const xs = all.flatMap((s) => s.points.map((p) => p.ts));
  const ys = all.flatMap((s) => s.points.map((p) => p.cum));
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(0, ...ys);
  const yMax = Math.max(0, ...ys);
  const W = 1000;
  const H = height;
  const pad = 8;
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;
  const x = (t) => pad + ((t - xMin) / xSpan) * (W - pad * 2);
  const y = (v) => H - pad - ((v - yMin) / ySpan) * (H - pad * 2);
  const zeroY = y(0);
  // x ticks: first / mid / last
  const ticks = [xMin, xMin + xSpan / 2, xMax];

  return (
    <div className="intel-curve">
      {showLegend && (
        <div className="intel-legend">
          {all.map((s) => (
            <span key={s.label} className="intel-legend__item">
              <span className="intel-legend__swatch" style={{ background: s.color }} />
              {s.label}
              {s.valueLabel != null && <b style={{ color: s.color }}>{s.valueLabel}</b>}
            </span>
          ))}
        </div>
      )}
      <svg className="intel-curve__svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <defs>
          {all.map((s, i) =>
            s.area ? (
              <linearGradient key={i} id={`ic-${gid}-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity="0.18" />
                <stop offset="100%" stopColor={s.color} stopOpacity="0" />
              </linearGradient>
            ) : null,
          )}
        </defs>
        <line x1={pad} y1={zeroY} x2={W - pad} y2={zeroY} stroke="var(--muted)" strokeDasharray="3 3"
              strokeWidth="1" vectorEffect="non-scaling-stroke" opacity="0.5" />
        {all.map((s, i) => {
          const pts = s.points.map((p) => `${x(p.ts).toFixed(1)},${y(p.cum).toFixed(1)}`).join(' ');
          return (
            <g key={s.label}>
              {s.area && (
                <polygon points={`${x(s.points[0].ts).toFixed(1)},${zeroY.toFixed(1)} ${pts} ${x(
                  s.points[s.points.length - 1].ts,
                ).toFixed(1)},${zeroY.toFixed(1)}`} fill={`url(#ic-${gid}-${i})`} />
              )}
              <polyline points={pts} fill="none" stroke={s.color} strokeWidth="2"
                        strokeDasharray={s.dash || 'none'} strokeLinejoin="round" strokeLinecap="round"
                        vectorEffect="non-scaling-stroke" />
            </g>
          );
        })}
      </svg>
      <div className="intel-curve__axis">
        {ticks.map((t, i) => (
          <span key={i}>{fmtTs(t, locale)}</span>
        ))}
      </div>
    </div>
  );
};

// Horizontal A/B comparison bars over a category list. Each row shows the label,
// two centre-zero bars (top = stream A, bottom = stream B) coloured by sign
// (green profit / red loss), and the two values. One primitive drives the
// per-symbol, per-market, per-direction, weekday, hour and monthly panels.
export const CompareBars = ({ rows, fmt, labelA, labelB, maxAbs, valueOf, subOf, scroll = false }) => {
  const val = valueOf || ((row, side) => (side === 'a' ? row.a : row.b));
  const cap = maxAbs || Math.max(1, ...rows.flatMap((r) => [Math.abs(val(r, 'a')), Math.abs(val(r, 'b'))]));
  const f = fmt || ((v) => (v >= 0 ? `+${v.toFixed(1)}` : v.toFixed(1)));
  const barStyle = (v) => {
    const w = (Math.min(Math.abs(v), cap) / cap) * 50;
    return v >= 0
      ? { left: '50%', width: `${w}%` }
      : { right: '50%', width: `${w}%` };
  };
  return (
    <div className={`cmp-wrap${scroll ? ' cmp-wrap--scroll' : ''}`}>
      <div className="cmp-legend">
        <span><i className="cmp-key cmp-key--a" />{labelA}</span>
        <span><i className="cmp-key cmp-key--b" />{labelB}</span>
      </div>
      <div className="cmp-rows">
        {rows.map((r) => {
          const a = val(r, 'a');
          const b = val(r, 'b');
          return (
            <div key={r.key} className="cmp-row">
              <span className="cmp-row__label" title={r.label}>{r.label}</span>
              <div className="cmp-row__track">
                <span className="cmp-row__axis" />
                <span className={`cmp-bar cmp-bar--a ${a >= 0 ? 'pos' : 'neg'}`} style={barStyle(a)} />
                <span className={`cmp-bar cmp-bar--b ${b >= 0 ? 'pos' : 'neg'}`} style={barStyle(b)} />
              </div>
              <span className="cmp-row__vals">
                <b className={a >= 0 ? 'win' : 'loss'}>{f(a)}{subOf ? <i>{subOf(r, 'a')}</i> : null}</b>
                <b className={b >= 0 ? 'win' : 'loss'}>{f(b)}{subOf ? <i>{subOf(r, 'b')}</i> : null}</b>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// A single head-to-head KPI: label, the two stream values, and which one is
// better (▲ marker + bold). `better` = 'a' | 'b' | null (higher-is-better is the
// default; pass invert for metrics where lower wins, e.g. drawdown / streak).
export const StatRow = ({ label, a, b, fmt, invert = false, neutral = false, hint }) => {
  const f = fmt || ((v) => (v == null ? '—' : String(v)));
  let better = null;
  if (!neutral && Number.isFinite(a) && Number.isFinite(b) && a !== b) {
    const aBetter = invert ? a < b : a > b;
    better = aBetter ? 'a' : 'b';
  }
  return (
    <div className="h2h-row">
      <span className="h2h-row__label" title={hint}>{label}</span>
      <b className={`h2h-row__val ${better === 'a' ? 'h2h-win' : ''}`}>
        {better === 'a' && <span className="h2h-mark">▲</span>}
        {f(a)}
      </b>
      <b className={`h2h-row__val ${better === 'b' ? 'h2h-win' : ''}`}>
        {better === 'b' && <span className="h2h-mark">▲</span>}
        {f(b)}
      </b>
    </div>
  );
};
