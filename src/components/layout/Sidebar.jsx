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
const IconImpulse = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11 1.6 3.4 11.2h4.2l-1.6 7.2 8-9.8h-4.4l1.4-7Z" />
  </svg>
);
const IconRadar = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="10" cy="10" r="7.5" /><circle cx="10" cy="10" r="4" />
    <circle cx="10" cy="10" r="1" fill="currentColor" stroke="none" />
    <line x1="10" y1="10" x2="16.5" y2="5.5" />
  </svg>
);
const IconSqueeze = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 3.2v6.3a6 6 0 0 0 12 0V3.2" />
    <path d="M4 3.2h3.4v6.3a2.6 2.6 0 0 0 5.2 0V3.2H16" />
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

// Strategy × Mode nested nav. Each group exposes Live + Backtest leaves: MAIN runs
// the v1 set (mode='live'), IMPULSE the refined v2 set (mode='impulse'), RADAR the
// NEW v3 compression-breakout set (mode='radar', strategy F — not the retired
// dynamic radar), SQUEEZE the v4 funding-extreme fade (mode='squeeze', strategy G —
// derivative positioning, not price geometry); dag.py emits each hourly.
// PULSE was retired 2026-06-10.
const GROUPS = [
  { key: 'main',    label: 'MAIN',    icon: <IconCommand />, modes: ['live', 'backtest'] },
  { key: 'impulse', label: 'IMPULSE', icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'radar',   label: 'RADAR',   icon: <IconRadar />,   modes: ['live', 'backtest'] },
  { key: 'squeeze', label: 'SQUEEZE', icon: <IconSqueeze />, modes: ['live', 'backtest'] },
];

const Sidebar = () => {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useLang();
  const { theme, setTheme } = useTheme();

  const leafLabel = { live: t('Live'), backtest: t('Backtest') };

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
            {g.modes.map((m) => (
              <NavLink key={m} to={`/${g.key}/${m}`} end className="sidebar__link sidebar__leaf">
                <span className={`sidebar__leaf-dot sidebar__leaf-dot--${m}`} />
                <span>{leafLabel[m]}</span>
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
