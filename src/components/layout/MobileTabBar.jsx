import { NavLink } from 'react-router-dom';
import { useTradeContext } from '../../context/TradeContext';
import { useLang } from '../../context/LanguageContext';
import { useExecActivation } from '../../utils/execActivation';
import { slugFor, LIVE_STREAM_KEYS } from '../../utils/streamMask';

// Native-app-style bottom navigation (Binance-like) — phone only (CSS-gated to
// ≤768px). 2026-07-09: Genel · Binance · Strateji · Menü. İşlem Merkezi, İstihbarat
// (admin), TOTAL, Ayarlar vb. Menü drawer'ında (Sidebar). Desktop sidebar değişmez.

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
// Strateji — yükselen çizgi grafik (canlı komuta merkezi kısayolu)
const IStrat = () => (
  <svg viewBox="0 0 20 20" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 13.5 7.5 9l3 3L17 5.5" /><path d="M13 5.5h4v4" />
  </svg>
);
const IMenu = () => (
  <svg viewBox="0 0 20 20" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
    <line x1="3.5" y1="6" x2="16.5" y2="6" /><line x1="3.5" y1="10" x2="16.5" y2="10" /><line x1="3.5" y1="14" x2="16.5" y2="14" />
  </svg>
);

const MobileTabBar = () => {
  const { mobileNavOpen, toggleMobileNav, closeMobileNav } = useTradeContext();
  const { t } = useLang();
  const act = useExecActivation();
  const cls = ({ isActive }) => `mtab${isActive ? ' is-active' : ''}`;
  // Binance canlı pozisyonlar — aktivasyona göre mainnet/paper'a yönlenir, ama sekme
  // HER ZAMAN görünür (aktivasyon yoksa mainnet panosu API-anahtarı istemini gösterir).
  const binanceTo = act.mainnet ? '/binance' : act.testnet ? '/binance-paper' : '/binance';
  // Strateji — ana canlı stratejinin (en yüksek R'li ATLAS) komuta merkezi.
  const strategyTo = `/${slugFor(LIVE_STREAM_KEYS[0])}/live`;

  return (
    <nav className="mobile-tabbar" aria-label="primary">
      <NavLink to="/" end className={cls} onClick={closeMobileNav}>
        <IHome /><span>{t('Genel')}</span>
      </NavLink>
      <NavLink to={binanceTo} className={cls} onClick={closeMobileNav}>
        <ILive /><span>Binance</span>
      </NavLink>
      <NavLink to={strategyTo} className={cls} onClick={closeMobileNav}>
        <IStrat /><span>{t('Strateji')}</span>
      </NavLink>
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
