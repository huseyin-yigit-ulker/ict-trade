import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth, RequireAuth, RequireActive, RequireAdmin, RequireFeature } from './context/AuthContext';
import LoginScreen from './components/LoginScreen';
import AppShell from './components/layout/AppShell';
import IntroPage from './pages/IntroPage';
import CommandCenterPage from './pages/CommandCenterPage';
import IntelligencePage from './pages/IntelligencePage';
import SettingsPage from './pages/SettingsPage';
import TrendPage from './pages/TrendPage';
import MarketCapPage from './pages/MarketCapPage';
import LivePositionsPage from './pages/LivePositionsPage';
import MidasXLivePage from './pages/MidasXLivePage';
import TradingSettingsPage from './pages/TradingSettingsPage';
import AdminPage from './pages/AdminPage';
import ExecGate from './components/ExecGate';
import UserShell from './components/user/UserShell';
import PortfolioPage from './pages/user/PortfolioPage';
import TradesPage from './pages/user/TradesPage';
import SignalsPage from './pages/user/SignalsPage';
import BotPage from './pages/user/BotPage';
import ProfilePage from './pages/user/ProfilePage';
import HelpPage from './pages/user/HelpPage';
import PusuLogo from './components/PusuLogo';
import SharedTradePage from './pages/SharedTradePage';

// PUBLIC yüzey (2026-07-13): /p/:token = admin'in ürettiği 1 saatlik paylaşım linki.
// /login gibi RequireAuth'un DIŞINDA ve HER İKİ dalda tanımlı olmalı — aksi halde oturumu
// olan biri linki açtığında ilgili dalın '*' fallback'ine takılıp eve yönlenir.

// Rol çatalı (2026-07-11): admin MEVCUT arayüzün tamamını görür (aşağıdaki AdminRoutes,
// eski App.jsx rota ağacının birebir taşınmışı); admin-dışı herkes Binance-tarzı 4 sekmeli
// basit kabuğa (UserShell) düşer. Güvenlik sınırı Supabase RLS'tir — bu çatal yalnız deneyimi
// ayırır. Profil yüklenmeden shell seçmek, admin'in soğuk deep-link'ini /portfoy'a EZER
// (URL mutasyonu, sadece flash değil) — o yüzden profil gelene dek BootSplash.

const BootSplash = () => (
  <div style={{
    minHeight: '100vh', display: 'flex', alignItems: 'center',
    justifyContent: 'center', background: 'var(--bg)', color: 'var(--accent)',
  }}>
    <PusuLogo size={64} animated />
  </div>
);

const AdminRoutes = () => (
  <Routes>
    <Route path="/login" element={<LoginScreen />} />
    <Route path="/p/:token" element={<SharedTradePage />} />
    <Route element={<RequireAuth><AppShell /></RequireAuth>}>
      <Route index element={<IntroPage />} />
      <Route path="/trend" element={<TrendPage />} />
      <Route path="/total" element={<MarketCapPage />} />
      <Route path="/binance" element={<RequireActive><ExecGate network="mainnet"><LivePositionsPage network="mainnet" /></ExecGate></RequireActive>} />
      <Route path="/binance-paper" element={<RequireActive><ExecGate network="testnet"><LivePositionsPage network="testnet" /></ExecGate></RequireActive>} />
      <Route path="/binance-altin" element={<RequireActive><ExecGate network="any"><MidasXLivePage /></ExecGate></RequireActive>} />
      <Route path="/trading" element={<RequireActive><RequireFeature k="trading"><TradingSettingsPage /></RequireFeature></RequireActive>} />
      <Route path="/admin" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
      <Route path="/:strategy/:mode" element={<CommandCenterPage />} />
      {/* İstihbarat = kurumsal quant tearsheet → yalnız admin. Non-admin (eski
          user_features.intelligence=true izni olsa bile) '/'e döner. */}
      <Route path="/intelligence" element={<RequireAdmin><IntelligencePage /></RequireAdmin>} />
      <Route path="/settings" element={<SettingsPage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
);

const UserRoutes = () => (
  <Routes>
    <Route path="/login" element={<LoginScreen />} />
    <Route path="/p/:token" element={<SharedTradePage />} />
    <Route element={<RequireAuth><UserShell /></RequireAuth>}>
      <Route index element={<Navigate to="/portfoy" replace />} />
      <Route path="/portfoy" element={<PortfolioPage />} />
      <Route path="/islemler" element={<TradesPage />} />
      <Route path="/sinyaller" element={<SignalsPage />} />
      <Route path="/bot" element={<RequireActive><BotPage /></RequireActive>} />
      <Route path="/profil" element={<ProfilePage />} />
      <Route path="/yardim" element={<HelpPage />} />
      {/* Push/deep-link/bookmark alias'ları — sw.js push data.url eski yolları taşıyabilir. */}
      <Route path="/binance" element={<Navigate to="/portfoy" replace />} />
      <Route path="/binance-paper" element={<Navigate to="/portfoy" replace />} />
      <Route path="/binance-altin" element={<Navigate to="/islemler" replace />} />
      <Route path="/trading" element={<Navigate to="/bot" replace />} />
      <Route path="/settings" element={<Navigate to="/profil" replace />} />
    </Route>
    {/* Gizli yüzeyler (/trend, /total, /admin, /intelligence, /:strategy/:mode …) bu dalda
        hiç tanımlı değil → hepsi eve döner. */}
    <Route path="*" element={<Navigate to="/portfoy" replace />} />
  </Routes>
);

export default function AppRoutes() {
  const { isAuthed, isAdmin, profile, profileLoading } = useAuth();
  // Profil fetch'i kalıcı başarısız olursa (profile=null, loading=false) kullanıcı
  // kabuğuna düşülür — fail-closed, gizlilik-güvenli taraf.
  if (isAuthed && !profile && profileLoading) return <BootSplash />;
  return isAdmin ? <AdminRoutes /> : <UserRoutes />;
}
