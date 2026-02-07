import { useTradeContext } from '../context/TradeContext';

const FileLoader = () => {
  const { setMode } = useTradeContext();
  return (
    <div id="mode-selection" className="boot-screen">
      <div className="boot-center">
        <div className="bot-logo">
          <div className="bot-core"></div>
          <div className="bot-ring"></div>
          <div className="bot-scan"></div>
          <div className="bot-burst"></div>
        </div>
        <div className="boot-text">
          <div className="boot-title">ICT TRADE BOT</div>
          <div className="boot-sub">starting</div>
        </div>
        <div className="boot-actions">
          <button className="primary-btn" onClick={() => setMode('backtest')}>📂 Backtest</button>
          <button className="primary-btn outline" onClick={() => setMode('live')}>🛰️ Live</button>
        </div>
      </div>
    </div>
  );
};

export default FileLoader;
