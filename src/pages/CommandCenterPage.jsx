import { useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { useTradeContext } from '../context/TradeContext';
import Dashboard from '../components/Dashboard';

// Strategy × Mode view. The URL (/:strategy/:mode) is the source of truth: it syncs
// the route params into context (setView) so the single data-load effect fetches the
// right set (main/impulse × live/backtest; main_half/impulse_half are backtest-only —
// the partial-TP exit model has no live emitter). Invalid combos bounce to /main/live
// (retired radar/squeeze/pulse routes and any *_half/live therefore land there).
const CommandCenterPage = () => {
  const { strategy: pStrat, mode: pMode } = useParams();
  const { strategy, mode, setView } = useTradeContext();
  const isHalf = pStrat === 'main_half' || pStrat === 'impulse_half';
  const validS = (pStrat === 'main' || pStrat === 'impulse' || isHalf) ? pStrat : null;
  const validM = isHalf
    ? (pMode === 'backtest' ? 'backtest' : null)            // ½TP streams are backtest-only
    : ((pMode === 'backtest' || pMode === 'live') ? pMode : null);

  useEffect(() => {
    if (validS && validM && (validS !== strategy || validM !== mode)) setView(validS, validM);
  }, [validS, validM, strategy, mode, setView]);

  if (!validS || !validM) return <Navigate to="/main/live" replace />;
  return <Dashboard />;
};

export default CommandCenterPage;
