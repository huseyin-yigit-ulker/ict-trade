import { useState } from 'react';
import { useTradeContext } from '../context/TradeContext';

const FileLoader = () => {
  const { processData } = useTradeContext();
  const [rawJson, setRawJson] = useState('');
  const [error, setError] = useState('');

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        setError('');
        processData(JSON.parse(event.target.result));
      } catch (err) {
        setError('JSON okunamadı. Lütfen formatı kontrol et.');
      }
    };
    reader.readAsText(file);
  };

  const handlePaste = () => {
    if (!rawJson.trim()) return;
    try {
      setError('');
      processData(JSON.parse(rawJson));
    } catch (err) {
      setError('Yapıştırılan JSON geçersiz.');
    }
  };

  return (
    <div id="mode-selection">
      <div className="loader-hero">
        <div className="loader-badge">TRADINGVIEW WEBHOOK READY</div>
        <div className="bot-logo">
          <div className="bot-core"></div>
          <div className="bot-ring"></div>
          <div className="bot-scan"></div>
        </div>
        <h1 className="logo-title">ICT TRADE BOT</h1>
        <p className="subtitle">1 dakikalık işlem günlüğü. JSON yükle veya webhook çıktısını yapıştır.</p>
      </div>

      <div className="mode-container">
        <div className="mode-card" onClick={() => document.getElementById('jsonInput').click()}>
          <h3>📂 JSON Yükle</h3>
          <p>Webhook çıktısı veya backtest dosyası</p>
          <div className="spinner" id="spinner" style={{ display: 'block' }}></div>
        </div>

        <div className="mode-card">
          <h3>📋 JSON Yapıştır</h3>
          <textarea
            className="json-input"
            placeholder='{"ict_signal":[...]}'
            value={rawJson}
            onChange={(e) => setRawJson(e.target.value)}
          />
          <button className="primary-btn" onClick={handlePaste}>İçe Aktar</button>
          {error && <div className="error-text">{error}</div>}
        </div>
      </div>

      <input type="file" id="jsonInput" accept=".json" style={{ display: 'none' }} onChange={handleFileUpload} />
    </div>
  );
};

export default FileLoader;
