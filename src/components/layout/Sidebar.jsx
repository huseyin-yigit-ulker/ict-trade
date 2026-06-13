import { useState } from 'react';
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
const IconHome = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2.6" y="2.6" width="6" height="6" rx="1.2" /><rect x="11.4" y="2.6" width="6" height="6" rx="1.2" />
    <rect x="2.6" y="11.4" width="6" height="6" rx="1.2" /><rect x="11.4" y="11.4" width="6" height="6" rx="1.2" />
  </svg>
);

// Strategy × Mode nested nav. MAIN runs the v1 set (mode='live'), IMPULSE the refined
// v2 set (mode='impulse') — dag.py emits each hourly. MAIN ½TP (v3) and IMPULSE ½TP
// (v4) read the SAME live main/impulse signals but track them under the partial-TP +
// breakeven exit model (50% out at ½ distance to TP, stop → entry) — Live view tracks
// the lifecycle in real time; Backtest reads the nightly v3/v4 resolution.
// PULSE retired 2026-06-10; RADAR/SQUEEZE removed 2026-06-11.
// KARMA = per-symbol best cell of {main,impulse} x {tam,½TP} from the 2026
// selection run (sync/karma_map.py) — live reads both parents, filtered per symbol.
const GROUPS = [
  { key: 'main',         label: 'MAIN',        icon: <IconCommand />, modes: ['live', 'backtest'] },
  { key: 'impulse',      label: 'IMPULSE',     icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'main_half',    label: 'MAIN ½TP',    icon: <IconCommand />, modes: ['live', 'backtest'] },
  { key: 'impulse_half', label: 'IMPULSE ½TP', icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'karma',        label: 'KARMA',       icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'karma_half',   label: 'KARMA ½TP',   icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'opus',         label: 'OPUS',        icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'opus_half',    label: 'OPUS ½TP',    icon: <IconImpulse />, modes: ['live', 'backtest'] },
  // CHOP-filtered twins — same stream, but skip signals fired while the symbol's 4h
  // was choppy (Efficiency Ratio < 0.25). Helps the broad/½TP streams; redundant on
  // the already-selective ones (shown by their 2026 backtest).
  { key: 'main_chop',         label: 'MAIN · Chop',        icon: <IconCommand />, modes: ['live', 'backtest'] },
  { key: 'impulse_chop',      label: 'IMPULSE · Chop',     icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'main_half_chop',    label: 'MAIN ½TP · Chop',    icon: <IconCommand />, modes: ['live', 'backtest'] },
  { key: 'impulse_half_chop', label: 'IMPULSE ½TP · Chop', icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'karma_chop',        label: 'KARMA · Chop',       icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'karma_half_chop',   label: 'KARMA ½TP · Chop',   icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'opus_chop',         label: 'OPUS · Chop',        icon: <IconImpulse />, modes: ['live', 'backtest'] },
  { key: 'opus_half_chop',    label: 'OPUS ½TP · Chop',    icon: <IconImpulse />, modes: ['live', 'backtest'] },
];

const Sidebar = () => {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useLang();
  const { theme, setTheme } = useTheme();

  const leafLabel = { live: t('Live'), backtest: t('Backtest') };

  // The 8 strategy streams are collected under a collapsible "Stratejiler" header
  // so the rail stays calm now that "Genel Bakış" is the home. Default open;
  // collapse state persists like the other PUSU prefs.
  const [stratOpen, setStratOpen] = useState(() => {
    try { return localStorage.getItem('pusu.navStrategies') !== '0'; } catch { return true; }
  });
  const toggleStrategies = () => setStratOpen((o) => {
    const next = !o;
    try { localStorage.setItem('pusu.navStrategies', next ? '1' : '0'); } catch { /* ignore */ }
    return next;
  });

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <PusuLogo size={38} animated />
        <div className="sidebar__brand-text">
          <div className="sidebar__name">PUSU</div>
        </div>
      </div>

      <nav className="sidebar__nav">
        <NavLink to="/" end className="sidebar__link sidebar__home">
          <span className="sidebar__icon"><IconHome /></span><span>{t('Genel Bakış')}</span>
        </NavLink>

        <button
          className="sidebar__section"
          onClick={toggleStrategies}
          aria-expanded={stratOpen}
          title={stratOpen ? t('Gizle') : t('Göster')}
        >
          <span className="sidebar__section-label">{t('Stratejiler')}</span>
          <span className="sidebar__section-chev" aria-hidden="true">{stratOpen ? '▾' : '▸'}</span>
        </button>

        {stratOpen && (
          <div className="sidebar__strategies">
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
          </div>
        )}

        <div className="sidebar__navsep" />
        <NavLink to="/trend" className="sidebar__link">
          <span className="sidebar__icon"><IconImpulse /></span><span>{t('Rejim Haritası')}</span>
        </NavLink>
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
