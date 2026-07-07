import { NavLink } from 'react-router-dom';
import { useTradeContext } from '../../context/TradeContext';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { useExecActivation } from '../../utils/execActivation';

// Native-app-style bottom navigation (Binance-like) — phone only (CSS-gated to
// ≤768px). Five slots: the 4 primary destinations + a "Menü" that opens the full
// drawer (all strategies / TOTAL / Ayarlar / prefs). The desktop sidebar/drawer
// is unchanged; this is an additive mobile surface.

const IHome = () => (
  <svg viewBox="0 0 20 20" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 9.4 10 3l7 6.4" /><path d="M4.7 8.6V16h10.6V8.6" />
  </svg>
);
const ILive = () => (
  <svg viewBox="0 0 20 20" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <line x1="6" y1="3" x2="6" y2="17" /><rect x="3.8" y="6.4" width="4.4" height="6" rx="1" fill="currentColor" stroke="none" opacity=".85" />
    <line x1="13.6" y1="4" x2="13.6" y2="16" /><rect x="11.4" y="7.6" width="4.4" height="5" rx="1" />
  </svg>
);
const IGear = () => (
  <svg viewBox="0 0 20 20" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="10" cy="10" r="2.7" />
    <path d="M10 2.6v2.3M10 15.1v2.3M2.6 10h2.3M15.1 10h2.3M4.9 4.9l1.6 1.6M13.5 13.5l1.6 1.6M15.1 4.9l-1.6 1.6M6.5 13.5l-1.6 1.6" />
  </svg>
);
const IIntel = () => (
  <svg viewBox="0 0 20 20" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2.4 10s3-5.2 7.6-5.2S17.6 10 17.6 10s-3 5.2-7.6 5.2S2.4 10 2.4 10Z" /><circle cx="10" cy="10" r="2.2" />
  </svg>
);
const IMenu = () => (
  <svg viewBox="0 0 20 20" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
    <line x1="3.5" y1="6" x2="16.5" y2="6" /><line x1="3.5" y1="10" x2="16.5" y2="10" /><line x1="3.5" y1="14" x2="16.5" y2="14" />
  </svg>
);

const MobileTabBar = () => {
  const { mobileNavOpen, toggleMobileNav, closeMobileNav } = useTradeContext();
  const { features } = useAuth();
  const { t } = useLang();
  const act = useExecActivation();   // "Canlı" sekmesi kişisel aktivasyona bağlı (2026-07-07)
  const cls = ({ isActive }) => `mtab${isActive ? ' is-active' : ''}`;
  const liveTo = act.mainnet ? '/binance' : act.testnet ? '/binance-paper' : null;

  return (
    <nav className="mobile-tabbar" aria-label="primary">
      <NavLink to="/" end className={cls} onClick={closeMobileNav}>
        <IHome /><span>{t('Genel')}</span>
      </NavLink>
      {liveTo && (
        <NavLink to={liveTo} className={cls} onClick={closeMobileNav}>
          <ILive /><span>{t('Canlı')}</span>
        </NavLink>
      )}
      {/* İşlem Merkezi — per-user trading controls; admin kullanıcı-başına kapatabilir. */}
      {features?.trading !== false && (
        <NavLink to="/trading" className={cls} onClick={closeMobileNav}>
          <IGear /><span>{t('İşlem')}</span>
        </NavLink>
      )}
      {features?.intelligence !== false && (
        <NavLink to="/intelligence" className={cls} onClick={closeMobileNav}>
          <IIntel /><span>{t('İstihbarat')}</span>
        </NavLink>
      )}
      <button
        type="button"
        className={`mtab${mobileNavOpen ? ' is-active' : ''}`}
        onClick={toggleMobileNav}
        aria-expanded={mobileNavOpen}
        aria-label={t('Menü')}
      >
        <IMenu /><span>{t('Menü')}</span>
      </button>
    </nav>
  );
};

export default MobileTabBar;
