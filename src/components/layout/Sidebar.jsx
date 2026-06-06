import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { useTradeContext } from '../../context/TradeContext';
import PusuLogo from '../PusuLogo';

const IconCommand = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <circle cx="10" cy="10" r="6.4" /><circle cx="10" cy="10" r="1.5" fill="currentColor" stroke="none" />
    <line x1="10" y1="1.4" x2="10" y2="4" /><line x1="10" y1="16" x2="10" y2="18.6" />
    <line x1="1.4" y1="10" x2="4" y2="10" /><line x1="16" y1="10" x2="18.6" y2="10" />
  </svg>
);
const IconIntel = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2.4 10s3-5.2 7.6-5.2S17.6 10 17.6 10s-3 5.2-7.6 5.2S2.4 10 2.4 10Z" />
    <circle cx="10" cy="10" r="2.2" />
  </svg>
);
const IconRadar = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="10" cy="10" r="7.5" /><circle cx="10" cy="10" r="4" />
    <circle cx="10" cy="10" r="1" fill="currentColor" stroke="none" />
    <line x1="10" y1="10" x2="16.5" y2="5.5" />
  </svg>
);
const IconSettings = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <line x1="3" y1="6.5" x2="17" y2="6.5" /><circle cx="13" cy="6.5" r="2.1" fill="var(--panel)" />
    <line x1="3" y1="13.5" x2="17" y2="13.5" /><circle cx="7" cy="13.5" r="2.1" fill="var(--panel)" />
  </svg>
);

const MODES = ['live', 'observe', 'backtest'];

const Sidebar = () => {
  const { user, logout } = useAuth();
  const { t } = useLang();
  const { appMode, setAppMode } = useTradeContext();

  const nav = [
    { to: '/command', label: t('Komuta Merkezi'), icon: <IconCommand /> },
    { to: '/intelligence', label: t('İstihbarat'), icon: <IconIntel /> },
    { to: '/radar', label: t('Hacim Radarı'), icon: <IconRadar /> },
    { to: '/settings', label: t('Ayarlar'), icon: <IconSettings /> },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <PusuLogo size={30} />
        <div className="sidebar__brand-text">
          <div className="sidebar__name">PUSU</div>
          <div className="sidebar__tag">LIQUIDITY AMBUSH</div>
        </div>
      </div>

      <nav className="sidebar__nav">
        {nav.map((n) => (
          <NavLink key={n.to} to={n.to} className="sidebar__link">
            <span className="sidebar__icon">{n.icon}</span>
            <span>{n.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__modes" role="group" aria-label="system mode">
        <div className="sidebar__group-label">{t('Mod')}</div>
        {MODES.map((m) => (
          <button
            key={m}
            className={`sidebar__mode sidebar__mode--${m} ${appMode === m ? 'active' : ''}`}
            onClick={() => setAppMode(m)}
          >
            <span className="sidebar__mode-dot" />
            <span>{t(m.toUpperCase())}</span>
          </button>
        ))}
      </div>

      <div className="sidebar__foot">
        <div className="sidebar__user">
          <span className="sidebar__avatar">
            {(user?.name || '?').slice(0, 1).toUpperCase()}
            <span className="sidebar__avatar-status" />
          </span>
          <span className="sidebar__user-meta">
            <span className="sidebar__uname">{user?.name || 'PUSU'}</span>
            <span className="sidebar__urole">{t('Operatör')}</span>
          </span>
          <button className="sidebar__logout" onClick={logout} title={t('Çıkış Yap')} aria-label={t('Çıkış Yap')}>⏻</button>
        </div>
        <div className="sidebar__copy">© 2026 PUSU</div>
      </div>
    </aside>
  );
};

export default Sidebar;
