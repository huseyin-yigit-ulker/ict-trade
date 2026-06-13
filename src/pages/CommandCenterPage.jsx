import { useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { useTradeContext } from '../context/TradeContext';
import Dashboard from '../components/Dashboard';

// Strategy × Mode view. The URL (/:strategy/:mode) is the source of truth: it syncs
// the route params into context (setView) so the single data-load effect fetches the
// right set. All four modules (main/impulse × classic/½TP) have Live + Backtest —
// the ½TP modules read the SAME live signals as their parent and track them under
// the partial-TP + breakeven exit rules. Invalid combos bounce to /main/live.
const CommandCenterPage = () => {
  const { strategy: pStrat, mode: pMode } = useParams();
  const { strategy, mode, setView } = useTradeContext();
  const isHalf = pStrat === 'main_half' || pStrat === 'impulse_half' || pStrat === 'karma_half' || pStrat === 'opus_half';
  const validS = (pStrat === 'main' || pStrat === 'impulse' || pStrat === 'karma' || pStrat === 'opus' || isHalf) ? pStrat : null;
  const validM = (pMode === 'backtest' || pMode === 'live') ? pMode : null;

  useEffect(() => {
    if (validS && validM && (validS !== strategy || validM !== mode)) setView(validS, validM);
  }, [validS, validM, strategy, mode, setView]);

  if (!validS || !validM) return <Navigate to="/main/live" replace />;
  return <Dashboard />;
};

export default CommandCenterPage;
