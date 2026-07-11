import SettingsPage from '../SettingsPage';

// Profil — mevcut Ayarlar sayfasının ince sarmalayıcısı. SettingsPage admin-only
// kartlarını zaten kendi içinde gizler (tema/dil/push/bildirim/şifre/çıkış kalır);
// kullanıcı modunda yalnız üst başlık farklı bir kabuk sınıfı alır.
export default function ProfilePage() {
  return (
    <div className="ush-profile">
      <SettingsPage />
    </div>
  );
}
