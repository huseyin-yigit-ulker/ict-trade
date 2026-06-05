import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
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
const IconSettings = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <line x1="3" y1="6.5" x2="17" y2="6.5" /><circle cx="13" cy="6.5" r="2.1" fill="var(--panel)" />
    <line x1="3" y1="13.5" x2="17" y2="13.5" /><circle cx="7" cy="13.5" r="2.1" fill="var(--panel)" />
  </svg>
);

const CAPS = ['Smart Money Concepts', 'Liquidity Sweep', 'Order Block', 'FVG', 'Killzone'];

const Sidebar = () => {
  const { user, logout } = useAuth();
  const { t } = useLang();

  const nav = [
    { to: '/command', label: t('Komuta Merkezi'), icon: <IconCommand /> },
    { to: '/intelligence', label: t('İstihbarat'), icon: <IconIntel /> },
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

      <div className="sidebar__foot">
        <div className="sidebar__engine">
          <div className="sidebar__engine-head"><span className="boot-engine__dot" /> PUSU ENGINE · ONLINE</div>
          <ul className="sidebar__caps">
            {CAPS.map((c) => (
              <li key={c}><span className="boot-system__check">✓</span>{c}</li>
            ))}
          </ul>
        </div>
        <div className="sidebar__user">
          <span className="sidebar__avatar">{(user?.name || '?').slice(0, 1).toUpperCase()}</span>
          <span className="sidebar__uname">{user?.name || 'PUSU'}</span>
          <button className="sidebar__logout" onClick={logout} title={t('Çıkış Yap')} aria-label={t('Çıkış Yap')}>⏻</button>
        </div>
        <div className="sidebar__copy">© 2026 PUSU</div>
      </div>
    </aside>
  );
};

export default Sidebar;
