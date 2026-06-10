import { useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { useTradeContext } from '../context/TradeContext';
import Dashboard from '../components/Dashboard';

// Strategy × Mode view. The URL (/:strategy/:mode) is the source of truth: it syncs
// the route params into context (setView) so the single data-load effect fetches the
// right set (main/impulse/radar/squeeze × live/backtest). Invalid strategy bounces to
// /main/live. 'radar' is the NEW v3 breakout stream, 'squeeze' the v4 funding-fade
// stream (the retired dynamic radar and pulse routes still bounce to /main/live).
const CommandCenterPage = () => {
  const { strategy: pStrat, mode: pMode } = useParams();
  const { strategy, mode, setView } = useTradeContext();
  const validS = (pStrat === 'main' || pStrat === 'impulse' || pStrat === 'radar' || pStrat === 'squeeze') ? pStrat : null;
  const validM = (pMode === 'backtest' || pMode === 'live') ? pMode : null;

  useEffect(() => {
    if (validS && validM && (validS !== strategy || validM !== mode)) setView(validS, validM);
  }, [validS, validM, strategy, mode, setView]);

  if (!validS || !validM) return <Navigate to="/main/live" replace />;
  return <Dashboard />;
};

export default CommandCenterPage;
