import { Link } from 'react-router-dom';
import { useLang } from '../../context/LanguageContext';
import SettingsPage from '../SettingsPage';

// Profil — mevcut Ayarlar sayfasının ince sarmalayıcısı. SettingsPage admin-only
// kartlarını zaten kendi içinde gizler (tema/dil/push/bildirim/şifre/çıkış kalır);
// üstte Yardım & SSS kısayolu.
export default function ProfilePage() {
  const { t } = useLang();
  return (
    <div className="ush-profile">
      <Link to="/yardim" className="ush-helplink">
        <span>❓ {t('Yardım & SSS')}</span>
        <small>{t('Nasıl çalışır, güvenlik, ücretler, Paper modu')}</small>
        <b>→</b>
      </Link>
      <SettingsPage />
    </div>
  );
}
