import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useTradeContext } from '../../context/TradeContext';
import { LIVE_STREAM_KEYS } from '../../utils/streamMask';
import UserHeader from './UserHeader';
import UserTabBar from './UserTabBar';
import ChartModal from '../ChartModal';
import '../../assets/css/user.css';

// Kullanıcı kabuğu — Binance-tarzı 4 sekme (Portföy · İşlemler · Sinyaller · Bot),
// Profil header avatarında. Sidebar/Topbar/LiveTicker/Stats-Summary modalları yok;
// ChartModal Sinyaller kartları için AppShell'dekiyle aynı koşulla global mount edilir.
const UserShell = () => {
  const { activeSignal, strategy, mode, setView, setChartView } = useTradeContext();
  const loc = useLocation();

  // Sinyal feed'ini CANLI bir akışa sabitle: bayat localStorage bir araştırma
  // akışını/backtest modunu gösteriyor olabilir — kullanıcı o veriyi asla çekmesin
  // (TradeProvider mount'ta pusu.strategy/pusu.mode ne derse onu yükler).
  // Grafik varsayılanı da NATIVE PUSU grafiği (giriş/TP/SL overlay'li) — TV embed'i
  // değil; kullanıcı modal içindeki toggle'dan yine TV'ye geçebilir.
  useEffect(() => {
    if (!LIVE_STREAM_KEYS.includes(strategy) || mode !== 'live') {
      setView(LIVE_STREAM_KEYS[0], 'live');
    }
    setChartView('chart');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { window.scrollTo(0, 0); }, [loc.pathname]);

  return (
    <div className="ush">
      <UserHeader />
      <main className="ush-content">
        {/* key=pathname → her sekme geçişinde kısa fade/slide animasyonu */}
        <div className="ush-page" key={loc.pathname}>
          <Outlet />
        </div>
      </main>
      <UserTabBar />
      {activeSignal && <ChartModal />}
    </div>
  );
};

export default UserShell;
