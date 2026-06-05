import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import PusuLogo from './PusuLogo';

// Engine capabilities, "systems online" style (mirrors the PUSU brief).
const CAPABILITIES = [
  'Smart Money Concepts', 'Liquidity Sweep', 'Order Block Detection',
  'FVG Identification', 'Killzone Filter',
];

const FileLoader = () => {
  const { setMode } = useTradeContext();
  const { lang, setLang, t } = useLang();

  return (
    <div id="mode-selection" className="boot-screen">
      {/* tactical backdrop: grid + slow radar sweep */}
      <div className="boot-grid" aria-hidden="true" />
      <div className="boot-radar" aria-hidden="true" />

      {/* drifting crypto glyphs */}
      <div className="boot-tickers" aria-hidden="true">
        <span style={{ left: '8%',  top: '16%', animationDelay: '0s'   }}>₿</span>
        <span style={{ left: '88%', top: '22%', animationDelay: '1.4s' }}>Ξ</span>
        <span style={{ left: '13%', top: '72%', animationDelay: '2.6s' }}>◎</span>
        <span style={{ left: '83%', top: '74%', animationDelay: '3.8s' }}>◆</span>
        <span style={{ left: '47%', top: '9%',  animationDelay: '0.7s' }}>₳</span>
      </div>

      {/* language toggle */}
      <div className="boot-lang">
        <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
        <span className="boot-lang__sep">·</span>
        <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
      </div>

      <div className="boot-center">
        <div className="boot-reticle">
          <PusuLogo size={108} animated className="boot-logo-mark" />
        </div>

        <div className="boot-text">
          <div className="boot-title">PUSU</div>
          <div className="boot-sub">LIQUIDITY AMBUSH SYSTEM</div>
        </div>

        <div className="boot-tagline-strip">WAIT · TRAP · EXECUTE</div>

        {/* systems-online capability checklist (staggered fade-in) */}
        <div className="boot-systems">
          {CAPABILITIES.map((c, i) => (
            <div className="boot-system" key={c} style={{ animationDelay: `${0.35 + i * 0.16}s` }}>
              <span className="boot-system__check">✓</span>{c}
            </div>
          ))}
        </div>

        <div className="boot-actions">
          <button className="primary-btn" onClick={() => setMode('backtest')}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <rect x="2"  y="9"  width="2.5" height="5"  rx="0.5" fill="currentColor"/>
              <rect x="6"  y="6"  width="2.5" height="8"  rx="0.5" fill="currentColor"/>
              <rect x="10" y="3"  width="2.5" height="11" rx="0.5" fill="currentColor"/>
            </svg>
            Backtest
          </button>
          <button className="primary-btn outline" onClick={() => setMode('live')}>
            <span className="live-dot-icon" aria-hidden="true" />
            Live
          </button>
        </div>

        <div className="boot-engine">
          <span className="boot-engine__dot" /> PUSU ENGINE · ONLINE
        </div>
      </div>

      <div className="boot-footer">© 2026 PUSU · {t('Likidite Avı')}</div>
    </div>
  );
};

export default FileLoader;
