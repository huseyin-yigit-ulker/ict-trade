import { useId, useMemo } from 'react';
import { useLang } from '../../context/LanguageContext';

// The centrepiece the dashboard lacked: the actual SHAPE of a low-win /
// big-payoff edge. Cumulative-R line + soft area, underwater drawdown band,
// dashed zero, accent markers on the biggest single-trade jumps, and a
// peak dot — all from the same cumulative-R math used by the KPI/drill sparks.
// Pure: give it ASC-sorted signals + the caller's calculatePnL.
const EquityCurvePanel = ({ signals, calculatePnL, profitFactor }) => {
  const { t } = useLang();
  const gid = useId();

  const model = useMemo(() => {
    if (!Array.isArray(signals) || signals.length < 2) return null;
    const cum = [];
    const peakLine = [];
    // peak seeded at the 0 starting equity (matches lo/hi=0 baseline) so an opening
    // drawdown before the first new high is counted, not silently dropped.
    let c = 0, peak = 0, peakIdx = 0, maxDD = 0, lo = 0, hi = 0;
    signals.forEach((s, i) => {
      c += Number(calculatePnL(s)) || 0;
      cum.push(c);
      if (c > peak) { peak = c; peakIdx = i; }
      peakLine.push(peak);
      if (peak - c > maxDD) maxDD = peak - c;
      if (c < lo) lo = c;
      if (c > hi) hi = c;
    });
    const jumps = signals
      .map((s, i) => ({ i, r: Number(calculatePnL(s)) || 0 }))
      .filter((j) => j.r > 0)
      .sort((a, b) => b.r - a.r)
      .slice(0, 3);
    return { cum, peakLine, total: cum[cum.length - 1], peak, peakIdx, maxDD, jumps, lo, hi };
  }, [signals, calculatePnL]);

  if (!model) return null;
  const { cum, peakLine, total, peak, peakIdx, maxDD, jumps, lo, hi } = model;

  const W = 1000, H = 150, pad = 6;
  const n = cum.length;
  const span = hi - lo || 1;
  const x = (i) => (i / (n - 1)) * W;
  const y = (v) => H - pad - ((v - lo) / span) * (H - pad * 2);
  const zeroY = y(0);
  const linePts = cum.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const ddPoly = [
    ...cum.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`),
    ...peakLine.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).reverse(),
  ].join(' ');

  const pos = total >= 0;
  const lineColor = pos ? 'var(--win)' : 'var(--loss)';
  const pf = Number(profitFactor);

  return (
    <div className="overview-card equity-panel" style={{ gridColumn: '1 / -1' }}>
      <div className="equity-head">
        <div className="summary-title equity-title">{t('Sermaye Eğrisi (R)')}</div>
        <div className="equity-readout">
          <span className={pos ? 'win' : 'loss'}>{pos ? '+' : ''}{total.toFixed(1)}R</span>
          {Number.isFinite(pf) && pf > 0 && <span className="equity-pf"> · PF {pf.toFixed(2)}</span>}
        </div>
      </div>
      <svg className="equity-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id={`eq-${gid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={pos ? 'var(--win-soft)' : 'var(--loss-soft)'} />
            <stop offset="100%" stopColor="transparent" />
          </linearGradient>
        </defs>
        <polygon className="equity-area" points={`0,${zeroY.toFixed(1)} ${linePts} ${W},${zeroY.toFixed(1)}`}
                 fill={`url(#eq-${gid})`} />
        <polygon className="equity-dd-band" points={ddPoly} fill="var(--loss-soft)" opacity="0.5" />
        <line className="equity-zero" x1="0" y1={zeroY.toFixed(1)} x2={W} y2={zeroY.toFixed(1)}
              stroke="var(--muted)" strokeDasharray="3 3" strokeWidth="1" vectorEffect="non-scaling-stroke" opacity="0.5" />
        {jumps.map((j) => (
          <line key={j.i} className="equity-marker" x1={x(j.i).toFixed(1)} y1={pad} x2={x(j.i).toFixed(1)} y2={H - pad}
                stroke="var(--accent)" strokeWidth="1" vectorEffect="non-scaling-stroke" opacity="0.3" />
        ))}
        <polyline className="equity-line" points={linePts} fill="none" stroke={lineColor} strokeWidth="2"
                  strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" pathLength="1" />
        <circle className="equity-peak-dot" cx={x(peakIdx).toFixed(1)} cy={y(peak).toFixed(1)} r="3" fill="var(--accent)" />
      </svg>
      <div className="equity-caption">
        {t('Tepe')} <b className="win">+{peak.toFixed(1)}R</b> · {t('Max DD')} <b className="loss">-{maxDD.toFixed(1)}R</b>
        {jumps.length > 0 && (
          <> · <span className="equity-legend-dot">◆</span> {t('en büyük {n} kazanç', { n: jumps.length })}</>
        )}
      </div>
    </div>
  );
};

export default EquityCurvePanel;
