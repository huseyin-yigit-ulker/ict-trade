import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { useTheme } from '../../context/ThemeContext';
import PusuLogo from '../PusuLogo';

const IconCommand = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <circle cx="10" cy="10" r="6.4" /><circle cx="10" cy="10" r="1.5" fill="currentColor" stroke="none" />
    <line x1="10" y1="1.4" x2="10" y2="4" /><line x1="10" y1="16" x2="10" y2="18.6" />
    <line x1="1.4" y1="10" x2="4" y2="10" /><line x1="16" y1="10" x2="18.6" y2="10" />
  </svg>
);
const IconRadar = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="10" cy="10" r="7.5" /><circle cx="10" cy="10" r="4" />
    <circle cx="10" cy="10" r="1" fill="currentColor" stroke="none" />
    <line x1="10" y1="10" x2="16.5" y2="5.5" />
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

// Strategy × Mode nested nav: each strategy group exposes Live + Backtest leaves.
const GROUPS = [
  { key: 'main',  label: 'MAIN',  icon: <IconCommand /> },
  { key: 'radar', label: 'RADAR', icon: <IconRadar /> },
];

const Sidebar = () => {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useLang();
  const { theme, setTheme } = useTheme();

  const leaves = [
    { mode: 'live', label: t('Live') },
    { mode: 'backtest', label: t('Backtest') },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <PusuLogo size={38} animated />
        <div className="sidebar__brand-text">
          <div className="sidebar__name">PUSU</div>
        </div>
      </div>

      <nav className="sidebar__nav">
        {GROUPS.map((g) => (
          <div key={g.key} className={`sidebar__group sidebar__group--${g.key}`}>
            <div className="sidebar__group-label">
              <span className="sidebar__icon">{g.icon}</span>{g.label}
            </div>
            {leaves.map((l) => (
              <NavLink key={l.mode} to={`/${g.key}/${l.mode}`} end className="sidebar__link sidebar__leaf">
                <span className={`sidebar__leaf-dot sidebar__leaf-dot--${l.mode}`} />
                <span>{l.label}</span>
              </NavLink>
            ))}
          </div>
        ))}

        <div className="sidebar__navsep" />
        <NavLink to="/intelligence" className="sidebar__link">
          <span className="sidebar__icon"><IconIntel /></span><span>{t('İstihbarat')}</span>
        </NavLink>
        <NavLink to="/settings" className="sidebar__link">
          <span className="sidebar__icon"><IconSettings /></span><span>{t('Ayarlar')}</span>
        </NavLink>
      </nav>

      <div className="sidebar__foot">
        <div className="sidebar__prefs">
          <div className="sidebar__ctl">
            <span className="sidebar__ctl-label">{t('Tema')}</span>
            <div className="seg seg--sm" role="group" aria-label="theme">
              <button className={theme === 'dark' ? 'active' : ''} onClick={() => setTheme('dark')} title={t('Koyu')}>☾</button>
              <button className={theme === 'light' ? 'active' : ''} onClick={() => setTheme('light')} title={t('Açık')}>☀</button>
            </div>
          </div>
          <div className="sidebar__ctl">
            <span className="sidebar__ctl-label">{t('Dil')}</span>
            <div className="seg seg--sm" role="group" aria-label="language">
              <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
              <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
            </div>
          </div>
        </div>

        <div className="sidebar__user">
          <span className="sidebar__avatar">{(user?.name || 'P').slice(0, 1).toUpperCase()}</span>
          <span className="sidebar__user-meta">
            <span className="sidebar__uname">{user?.name || 'pusu'}</span>
            <span className="sidebar__urole">{t('Operatör')}</span>
          </span>
          <button className="sidebar__logout" onClick={logout} title={t('Çıkış Yap')} aria-label={t('Çıkış Yap')}>⏻</button>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
