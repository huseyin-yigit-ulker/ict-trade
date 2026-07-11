import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import PusuLogo from '../PusuLogo';

// İnce yapışkan header: solda marka, ortada (yalnız masaüstü) 4 nav linki,
// sağda profil avatarı — Binance web'in üst navı gibi; 4 hedef için rail gereksiz.
const UserHeader = () => {
  const { user } = useAuth();
  const { t } = useLang();
  const initial = (user?.name || 'P').trim().charAt(0).toUpperCase();
  const cls = ({ isActive }) => `ush-nav__link${isActive ? ' is-active' : ''}`;

  return (
    <header className="ush-header">
      <Link to="/portfoy" className="ush-brand" aria-label="PUSU">
        <PusuLogo size={24} />
        <span className="ush-brand__name">PUSU</span>
      </Link>
      <nav className="ush-nav" aria-label="primary">
        <NavLink to="/portfoy" className={cls}>{t('Portföy')}</NavLink>
        <NavLink to="/islemler" className={cls}>{t('İşlemler')}</NavLink>
        <NavLink to="/sinyaller" className={cls}>{t('Sinyaller')}</NavLink>
        <NavLink to="/bot" className={cls}>Bot</NavLink>
      </nav>
      <Link to="/profil" className="ush-avatar" title={user?.name || t('Profil')} aria-label={t('Profil')}>
        {initial}
      </Link>
    </header>
  );
};

export default UserHeader;
