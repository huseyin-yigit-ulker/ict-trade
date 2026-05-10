import { useTradeContext } from '../context/TradeContext';

const FileLoader = () => {
  const { setMode } = useTradeContext();

  return (
    <div id="mode-selection" className="boot-screen">
      {/* Floating crypto/finance tickers — drifting at low opacity */}
      <div className="boot-tickers" aria-hidden="true">
        <span style={{ left: '8%',  top: '15%', animationDelay: '0s'   }}>₿</span>
        <span style={{ left: '88%', top: '22%', animationDelay: '1.4s' }}>Ξ</span>
        <span style={{ left: '14%', top: '70%', animationDelay: '2.6s' }}>◎</span>
        <span style={{ left: '82%', top: '78%', animationDelay: '3.8s' }}>$</span>
        <span style={{ left: '46%', top: '8%',  animationDelay: '0.7s' }}>₳</span>
        <span style={{ left: '50%', top: '88%', animationDelay: '2.1s' }}>Ð</span>
      </div>

      <div className="boot-center">
        {/* Stylised "trade" mark — ascending sparkline + breakout candle, yellow ring */}
        <svg className="boot-logo-svg" viewBox="0 0 120 120" fill="none" aria-hidden="true">
          <defs>
            <linearGradient id="bootGrad" x1="0" y1="100%" x2="100%" y2="0">
              <stop offset="0%"  stopColor="#FCD535" stopOpacity="0.0"/>
              <stop offset="80%" stopColor="#FCD535" stopOpacity="0.6"/>
              <stop offset="100%" stopColor="#FCD535" stopOpacity="0.95"/>
            </linearGradient>
          </defs>

          {/* outer glow ring */}
          <circle cx="60" cy="60" r="56" stroke="#FCD535" strokeOpacity="0.18" strokeWidth="1" />
          <circle cx="60" cy="60" r="46" stroke="#FCD535" strokeOpacity="0.35" strokeWidth="1" className="boot-logo-ring" />

          {/* baseline */}
          <line x1="20" y1="92" x2="100" y2="92" stroke="#2B3139" strokeWidth="1" />

          {/* ascending sparkline */}
          <polyline points="22,80 36,68 50,76 64,56 78,42 92,28"
            stroke="url(#bootGrad)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

          {/* candle 1 — small bearish */}
          <line x1="36" y1="62" x2="36" y2="76" stroke="#F6465D" strokeWidth="1" />
          <rect x="33.5" y="66" width="5" height="6" fill="#F6465D" rx="0.5" />

          {/* candle 2 — bullish */}
          <line x1="64" y1="48" x2="64" y2="60" stroke="#0ECB81" strokeWidth="1" />
          <rect x="61.5" y="50" width="5" height="8" fill="#0ECB81" rx="0.5" />

          {/* candle 3 — breakout bullish */}
          <line x1="92" y1="22" x2="92" y2="38" stroke="#0ECB81" strokeWidth="1" />
          <rect x="89" y="26" width="6" height="10" fill="#0ECB81" rx="0.5" className="boot-logo-candle" />

          {/* crosshair pulse */}
          <circle cx="92" cy="28" r="3" fill="#0ECB81" className="boot-logo-pulse" />
        </svg>

        <div className="boot-text">
          <div className="boot-title">ICT TRADE BOT</div>
          <div className="boot-sub">SMART · MONEY · CONCEPTS</div>
        </div>

        <div className="boot-actions">
          <button className="primary-btn" onClick={() => setMode('backtest')}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <rect x="2"  y="9"  width="2.5" height="5" rx="0.5" fill="currentColor"/>
              <rect x="6"  y="6"  width="2.5" height="8" rx="0.5" fill="currentColor"/>
              <rect x="10" y="3"  width="2.5" height="11" rx="0.5" fill="currentColor"/>
            </svg>
            Backtest
          </button>
          <button className="primary-btn outline" onClick={() => setMode('live')}>
            <span className="live-dot-icon" aria-hidden="true" />
            Live
          </button>
        </div>

        <div className="boot-tagline">
          <span className="boot-stat">22</span> sembol
          <span className="boot-stat-divider">·</span>
          <span className="boot-stat">4</span> strateji
          <span className="boot-stat-divider">·</span>
          <span className="boot-stat">1H</span> MTF
        </div>
      </div>
    </div>
  );
};

export default FileLoader;
