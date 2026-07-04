import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import LiveTicker from '../LiveTicker';
import ChartModal from '../ChartModal';
import StatsModal from '../StatsModal';
import SummaryModal from '../SummaryModal';
import { useTradeContext } from '../../context/TradeContext';

const AppShell = () => {
  const {
    activeSignal, showStats, showSummary,
    sidebarHidden, mobileNavOpen, closeMobileNav,
  } = useTradeContext();
  const loc = useLocation();

  // Close the phone drawer on every navigation (tapping a nav item routes away).
  useEffect(() => { closeMobileNav(); }, [loc.pathname, closeMobileNav]);

  return (
    <div className={`app-shell${sidebarHidden ? ' is-collapsed' : ''}${mobileNavOpen ? ' is-drawer-open' : ''}`}>
      {/* Sidebar is ALWAYS mounted so the phone drawer can slide in; the desktop
          collapse is handled purely in CSS (.is-collapsed .sidebar { display:none }). */}
      <Sidebar />
      {mobileNavOpen && <div className="sidebar-scrim" onClick={closeMobileNav} />}
      <div className="app-main">
        <Topbar />
        <main className="app-content"><Outlet /></main>
      </div>

      {activeSignal && <ChartModal />}
      {showStats && <StatsModal />}
      {showSummary && <SummaryModal />}
      <LiveTicker />
    </div>
  );
};

export default AppShell;
