import { useTradeContext } from '../context/TradeContext';

const FileLoader = () => {
  const { processData } = useTradeContext();

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => processData(JSON.parse(event.target.result));
    reader.readAsText(file);
  };

  return (
    <div id="mode-selection">
      <h1 className="logo-title">ICT JOURNAL</h1>
      <div className="mode-container">
        <div className="mode-card" onClick={() => document.getElementById('jsonInput').click()}>
          <h3>📂 BACKTEST</h3>
          <p>Yükleniyor... veya Dosya Seç</p>
          <div className="spinner" id="spinner" style={{display:'block'}}></div>
        </div>
      </div>
      <input type="file" id="jsonInput" accept=".json" style={{ display: 'none' }} onChange={handleFileUpload} />
    </div>
  );
};

export default FileLoader;