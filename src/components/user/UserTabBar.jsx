import { NavLink } from 'react-router-dom';
import { useLang } from '../../context/LanguageContext';

// Alt sekme çubuğu (yalnız ≤768px, CSS kapılı) — Binance app'in ana navigasyonu gibi
// 4 büyük dokunma hedefi. Profil 5. sekme DEĞİL: header avatarının arkasında.

const IWallet = () => (
  <svg viewBox="0 0 20 20" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2.5" y="5" width="15" height="11" rx="2" />
    <path d="M2.5 8h15" opacity=".45" />
    <circle cx="14" cy="12" r="1.1" fill="currentColor" stroke="none" />
  </svg>
);
const ITrades = () => (
  <svg viewBox="0 0 20 20" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 7h10.5" /><path d="m11.5 3.8 3.2 3.2-3.2 3.2" />
    <path d="M16 13H5.5" /><path d="m8.5 9.8-3.2 3.2 3.2 3.2" />
  </svg>
);
const ISignal = () => (
  <svg viewBox="0 0 20 20" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11.5 2.5 5 11h4l-1 6.5L14.5 9h-4l1-6.5Z" />
  </svg>
);
const IBot = () => (
  <svg viewBox="0 0 20 20" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="7" width="12" height="9" rx="2" />
    <path d="M10 4.5V7" /><circle cx="10" cy="3.5" r="1" />
    <circle cx="7.5" cy="11" r=".9" fill="currentColor" stroke="none" />
    <circle cx="12.5" cy="11" r=".9" fill="currentColor" stroke="none" />
    <path d="M8 13.8h4" />
  </svg>
);

const UserTabBar = () => {
  const { t } = useLang();
  const cls = ({ isActive }) => `ush-tab${isActive ? ' is-active' : ''}`;
  return (
    <nav className="ush-tabbar" aria-label="primary">
      <NavLink to="/portfoy" className={cls}><IWallet /><span>{t('Portföy')}</span></NavLink>
      <NavLink to="/islemler" className={cls}><ITrades /><span>{t('İşlemler')}</span></NavLink>
      <NavLink to="/sinyaller" className={cls}><ISignal /><span>{t('Sinyaller')}</span></NavLink>
      <NavLink to="/bot" className={cls}><IBot /><span>Bot</span></NavLink>
    </nav>
  );
};

export default UserTabBar;
