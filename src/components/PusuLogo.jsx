// PUSU reticle mark — a sniper-scope / target-lock crosshair: the "liquidity
// ambush" idea as a logo. Uses currentColor so the parent sets the (amber) tone.
// animated=true (boot screen) spins the outer ring + pulses the strike/core.
const PusuLogo = ({ size = 40, className = '', animated = false }) => (
  <svg
    className={`pusu-mark ${animated ? 'pusu-mark--anim' : ''} ${className}`}
    width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true"
  >
    {/* outer scanning ring (dashed → reads like a radar/scope) */}
    <circle className="pusu-ring" cx="24" cy="24" r="21" stroke="currentColor"
            strokeWidth="2" strokeDasharray="3.5 5" strokeLinecap="round" />
    {/* mid ring */}
    <circle cx="24" cy="24" r="13.5" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.4" />
    {/* crosshair ticks */}
    <g stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="24" y1="1.5" x2="24" y2="8.5" />
      <line x1="24" y1="39.5" x2="24" y2="46.5" />
      <line x1="1.5" y1="24" x2="8.5" y2="24" />
      <line x1="39.5" y1="24" x2="46.5" y2="24" />
    </g>
    {/* lock-on marker: downward strike triangle (the ambush) */}
    <path className="pusu-strike" d="M24 13.5 L30 25 L18 25 Z" fill="currentColor" />
    {/* center core */}
    <circle className="pusu-core" cx="24" cy="24" r="2.4" fill="currentColor" />
  </svg>
);

export default PusuLogo;
