import { useId } from 'react';

// Shared inline-SVG micro-chart — the ONLY place spark path math lives, so the
// "shape of the edge" reads identically everywhere it appears (KPI strip,
// drill cards). Pure/presentational: feed it a numeric series, nothing else.
//   variant: 'area' | 'line' | 'bars'
//   colorBySign: stroke/fill = --win when last value >= 0 else --loss
// Degrades to null on too-few points so empty data renders nothing.
const Sparkline = ({
  values,
  width = 64,
  height = 18,
  variant = 'area',
  zeroBaseline = true,
  colorBySign = true,
  color,
  showEndDot = true,
  className = '',
}) => {
  const gid = useId();
  const n = Array.isArray(values) ? values.length : 0;
  if (n < (variant === 'bars' ? 1 : 2)) return null;

  const pad = 1.5;
  const lo = Math.min(...values, zeroBaseline ? 0 : Infinity);
  const hi = Math.max(...values, zeroBaseline ? 0 : -Infinity);
  const span = hi - lo || 1;
  const x = (i) => (n === 1 ? width / 2 : (i / (n - 1)) * width);
  const y = (v) => height - pad - ((v - lo) / span) * (height - pad * 2);

  const last = values[n - 1];
  const stroke = colorBySign ? (last >= 0 ? 'var(--win)' : 'var(--loss)') : (color || 'var(--accent)');
  const soft = last >= 0 ? 'var(--win-soft)' : 'var(--loss-soft)';
  const zeroY = y(0);
  const linePts = values.map((v, i) => `${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ');

  return (
    <svg className={`spark ${className}`} viewBox={`0 0 ${width} ${height}`} width={width} height={height}
         preserveAspectRatio="none" aria-hidden="true">
      {variant === 'bars' ? (
        values.map((v, i) => {
          const bw = (width / n) * 0.66;
          const top = v >= 0 ? y(v) : zeroY;
          const h = Math.max(1, Math.abs(zeroY - y(v)));
          return (
            <rect key={i} className="spark__bar" x={(x(i) - bw / 2).toFixed(2)} y={top.toFixed(2)}
                  width={bw.toFixed(2)} height={h.toFixed(2)} rx="0.5"
                  fill={v >= 0 ? 'var(--win)' : 'var(--loss)'} />
          );
        })
      ) : (
        <>
          {variant === 'area' && (
            <>
              <defs>
                <linearGradient id={`spk-${gid}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={soft} />
                  <stop offset="100%" stopColor="transparent" />
                </linearGradient>
              </defs>
              <polygon className="spark__area" points={`0,${height} ${linePts} ${width},${height}`}
                       fill={`url(#spk-${gid})`} />
            </>
          )}
          {zeroBaseline && (
            <line className="spark__zero" x1="0" y1={zeroY.toFixed(2)} x2={width} y2={zeroY.toFixed(2)}
                  stroke="var(--muted)" strokeWidth="1" strokeDasharray="2 2"
                  vectorEffect="non-scaling-stroke" opacity="0.45" />
          )}
          <polyline className="spark__line" points={linePts} fill="none" stroke={stroke} strokeWidth="1.5"
                    strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          {showEndDot && (
            <circle className="spark__dot" cx={x(n - 1).toFixed(2)} cy={y(last).toFixed(2)} r="2" fill={stroke} />
          )}
        </>
      )}
    </svg>
  );
};

export default Sparkline;
