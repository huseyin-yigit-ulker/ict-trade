import { useEffect, useRef, useState } from 'react';
import { createChart } from 'lightweight-charts';
import { useTradeContext } from '../context/TradeContext';

const ChartModal = () => {
  const { activeSignal, setActiveSignal } = useTradeContext();
  const chartContainerRef = useRef(null);
  const [showTv, setShowTv] = useState(true);
  const [chartError, setChartError] = useState('');

  const normalizeForBinance = (sym) => {
    if (!sym) return '';
    return sym.replace(/[^A-Za-z0-9]/g, '');
  };

  const normalizeForTv = (sym) => {
    if (!sym) return '';
    return sym.replace(/[^A-Za-z0-9.]/g, '');
  };

  const toTvFuturesSymbol = (sym) => {
    let base = normalizeForTv(sym);
    if (!base) return '';
    if (base.endsWith('.P')) return `BINANCE:${base}`;
    if (base.endsWith('PERP')) base = base.replace(/PERP$/, '');
    return `BINANCE:${base}.P`;
  };

  const getTvEmbedUrl = () => {
    const tvSymbol = toTvFuturesSymbol(activeSignal?.symbol);
    const params = new URLSearchParams({
      symbol: tvSymbol,
      interval: '1',
      theme: 'dark',
      style: '1',
      toolbarbg: '1a2333',
      enable_publishing: 'false',
      hide_side_toolbar: 'false',
      allow_symbol_change: 'true',
      studies: '["Volume@tv-basicstudies"]',
      locale: 'tr',
      withdateranges: 'true',
      hideideas: 'true',
      autosize: 'true'
    });
    return `https://s.tradingview.com/widgetembed/?${params.toString()}`;
  };

  useEffect(() => {
    if (!activeSignal || !chartContainerRef.current || showTv) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { backgroundColor: '#0b0f18', textColor: '#d6e1ff' },
      grid: { vertLines: { color: '#1a2333' }, horzLines: { color: '#1a2333' } },
      timeScale: { timeVisible: true, secondsVisible: false },
      width: chartContainerRef.current.clientWidth,
      height: 520,
      rightPriceScale: { borderColor: '#1a2333' },
      crosshair: { mode: 1 }
    });

    const series = chart.addCandlestickSeries({
      upColor: '#089981', downColor: '#F23645', borderVisible: false, wickUpColor: '#089981', wickDownColor: '#F23645'
    });

    // Binance Verisi
    const fetchAndRender = async () => {
      setChartError('');
      const entryTime = activeSignal.dateObj.getTime();
      const exitTime = activeSignal.exitTs || entryTime + (20 * 60 * 1000);
      const fetchStartTime = entryTime - (60 * 1000 * 20);
      const fetchEndTime = exitTime + (60 * 1000 * 20);
      const baseSymbol = normalizeForBinance(activeSignal.symbol);

      try {
        const urlFutures = `https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
        const res = await fetch(urlFutures);
        let data = await res.json();

        if (!Array.isArray(data)) {
          const urlSpot = `https://api.binance.com/api/v3/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
          const resSpot = await fetch(urlSpot);
          data = await resSpot.json();
        }

        if (!Array.isArray(data)) {
          throw new Error('Kline verisi alınamadı');
        }

        const candles = data.map(d => ({
          time: d[0] / 1000,
          open: parseFloat(d[1]),
          high: parseFloat(d[2]),
          low: parseFloat(d[3]),
          close: parseFloat(d[4])
        }));

        series.setData(candles);

        series.createPriceLine({ price: activeSignal.entry, color: '#7b8cff', lineWidth: 2, lineStyle: 2, title: 'ENTRY' });
        series.createPriceLine({ price: activeSignal.tp, color: '#30d158', lineWidth: 2, title: 'TP' });
        series.createPriceLine({ price: activeSignal.sl, color: '#ff4d6d', lineWidth: 2, title: 'SL' });

        const markerSeries = chart.addLineSeries({ color: 'transparent' });
        markerSeries.setData(candles.map(c => ({ time: c.time, value: c.close })));
        markerSeries.setMarkers([
          {
            time: Math.floor(entryTime / 1000),
            position: 'belowBar',
            color: '#7b8cff',
            shape: 'arrowUp',
            text: 'ENTRY'
          },
          {
            time: Math.floor(exitTime / 1000),
            position: 'aboveBar',
            color: activeSignal.status === 'TP' ? '#30d158' : '#ff4d6d',
            shape: 'arrowDown',
            text: activeSignal.status === 'TP' ? 'TP' : 'SL'
          }
        ]);

        chart.timeScale().fitContent();
      } catch (err) {
        setChartError('Grafik verisi çekilemedi. TradingView görünümüne geçebilirsin.');
        console.error("Chart Data Error:", err);
      }
    };

    fetchAndRender();

    return () => chart.remove();
  }, [activeSignal, showTv]);

  useEffect(() => {
    const handleEsc = (e) => e.key === 'Escape' && setActiveSignal(null);
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [setActiveSignal]);

  useEffect(() => {
    setShowTv(true);
  }, [activeSignal]);

  return (
    <div id="modal" style={{ display: 'block' }}>
      <div id="chart-header">
        <h2 style={{color:'white', margin:0, fontSize:'16px'}}>
          {activeSignal.symbol} | {activeSignal.dir}
        </h2>
        <div className="chart-actions">
          <button className={`chart-toggle ${!showTv ? 'active' : ''}`} onClick={() => setShowTv(false)}>Journal</button>
          <button className={`chart-toggle ${showTv ? 'active' : ''}`} onClick={() => setShowTv(true)}>TradingView</button>
        </div>
      </div>
      <button id="close-modal" onClick={() => setActiveSignal(null)}>KAPAT [ESC]</button>
      {chartError && !showTv && (
        <div className="chart-warning">{chartError}</div>
      )}
      <div
        ref={chartContainerRef}
        id="chart-container"
        style={{ width: '100%', height: '100%', display: showTv ? 'none' : 'block' }}
      ></div>
      {showTv && (
        <iframe
          className="tv-iframe"
          title="TradingView"
          src={getTvEmbedUrl()}
          frameBorder="0"
          allowTransparency="true"
          allow="fullscreen; clipboard-write"
          loading="lazy"
        />
      )}
    </div>
  );
};

export default ChartModal;
