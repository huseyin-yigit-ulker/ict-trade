import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, LineSeries } from 'lightweight-charts';
import { useTradeContext } from '../context/TradeContext';

const ChartModal = () => {
  const { activeSignal, setActiveSignal, chartView, setChartView } = useTradeContext();
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const [showTv, setShowTv] = useState(chartView === 'tv');
  const [chartError, setChartError] = useState('');
  const [chartLoading, setChartLoading] = useState(false);
  const calculatePnL = (sig) => {
    if (!sig || !sig.entry || !sig.exitPrice) return null;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };

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

    setChartLoading(true);
    chartContainerRef.current.innerHTML = '';

    const rect = chartContainerRef.current.getBoundingClientRect();
    const width = rect.width > 0 ? rect.width : 900;
    const height = rect.height > 0 ? rect.height : 520;

    const themeConfig = {
      bg: '#0b0f18',
      text: '#d6e1ff',
      grid: 'rgba(0,0,0,0)',
      up: '#bfc9d9',
      down: '#1b1b1b'
    };

    const chart = createChart(chartContainerRef.current, {
      layout: { backgroundColor: themeConfig.bg, textColor: themeConfig.text },
      grid: { vertLines: { color: themeConfig.grid }, horzLines: { color: themeConfig.grid } },
      width,
      height,
      rightPriceScale: { borderColor: 'rgba(0,0,0,0)' },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: 'rgba(0,0,0,0)' },
      crosshair: {
        mode: 1,
        vertLine: { color: 'rgba(255,255,255,0.15)', style: 2 },
        horzLine: { color: 'rgba(255,255,255,0.15)', style: 2 }
      }
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: themeConfig.up,
      downColor: themeConfig.down,
      borderVisible: false,
      wickUpColor: themeConfig.up,
      wickDownColor: themeConfig.down
    });

    // Binance Verisi
    const fetchAndRender = async () => {
      setChartError('');
      const entryTime = activeSignal.dateObj.getTime();
      const exitTime = activeSignal.exitTs || entryTime + (50 * 60 * 1000);
      const fetchStartTime = entryTime - (60 * 1000 * 50);
      const fetchEndTime = exitTime + (60 * 1000 * 50);
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

        if (candles.length === 0) {
          throw new Error('Kline verisi boş');
        }

        series.setData(candles);

        const entryPrice = activeSignal.entry;
        const tpPrice = activeSignal.tp;
        const slPrice = activeSignal.sl;
        const entryTs = Math.floor(entryTime / 1000);
        const exitTs = Math.floor(exitTime / 1000);

        if (entryPrice && tpPrice) {
          const tpBand = chart.addBaselineSeries({
            baseValue: { type: 'price', price: entryPrice },
            topLineColor: 'rgba(48, 209, 88, 0.9)',
            topFillColor1: 'rgba(48, 209, 88, 0.28)',
            topFillColor2: 'rgba(48, 209, 88, 0.06)',
            bottomLineColor: 'rgba(0,0,0,0)',
            bottomFillColor1: 'rgba(0,0,0,0)',
            bottomFillColor2: 'rgba(0,0,0,0)',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false
          });
          tpBand.setData([
            { time: entryTs, value: tpPrice },
            { time: exitTs, value: tpPrice }
          ]);
        }

        if (entryPrice && slPrice) {
          const slBand = chart.addBaselineSeries({
            baseValue: { type: 'price', price: entryPrice },
            topLineColor: 'rgba(0,0,0,0)',
            topFillColor1: 'rgba(0,0,0,0)',
            topFillColor2: 'rgba(0,0,0,0)',
            bottomLineColor: 'rgba(255, 77, 109, 0.9)',
            bottomFillColor1: 'rgba(255, 77, 109, 0.28)',
            bottomFillColor2: 'rgba(255, 77, 109, 0.06)',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false
          });
          slBand.setData([
            { time: entryTs, value: slPrice },
            { time: exitTs, value: slPrice }
          ]);
        }

        if (entryPrice && entryTs && exitTs) {
          const entryLine = chart.addSeries(LineSeries, { color: 'rgba(123, 140, 255, 0.8)', lineWidth: 1 });
          entryLine.setData([
            { time: entryTs, value: entryPrice },
            { time: exitTs, value: entryPrice }
          ]);
        }

        if (entryPrice) {
          const marker = chart.addSeries(LineSeries, { color: 'transparent' });
          marker.setData(candles.map(c => ({ time: c.time, value: c.close })));
          marker.setMarkers([
            {
              time: entryTs,
              position: 'belowBar',
              color: '#7b8cff',
              shape: 'arrowUp',
              text: 'ENTRY'
            },
            {
              time: exitTs,
              position: 'aboveBar',
              color: activeSignal.status === 'TP' ? '#30d158' : '#ff4d6d',
              shape: 'arrowDown',
              text: activeSignal.status === 'TP' ? 'TP' : 'SL'
            }
          ]);
        }

        chart.timeScale().fitContent();
        setChartLoading(false);
      } catch (err) {
        setChartError('Grafik verisi çekilemedi. TradingView görünümüne geçebilirsin.');
        setChartLoading(false);
        console.error("Chart Data Error:", err);
      }
    };

    fetchAndRender();

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry || !chartRef.current) return;
      const { width: w, height: h } = entry.contentRect;
      if (w > 0 && h > 0) {
        chartRef.current.applyOptions({ width: w, height: h });
      }
    });
    observer.observe(chartContainerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [activeSignal, showTv]);

  useEffect(() => {
    if (!showTv) return;
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }
    if (chartContainerRef.current) {
      chartContainerRef.current.innerHTML = '';
    }
    setChartLoading(false);
    setChartError('');
  }, [showTv]);

  useEffect(() => {
    const handleEsc = (e) => e.key === 'Escape' && setActiveSignal(null);
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [setActiveSignal]);

  useEffect(() => {
    const isTv = chartView === 'tv';
    setShowTv(isTv);
  }, [activeSignal, chartView]);

  return (
    <div id="modal" style={{ display: 'block' }}>
      <div id="chart-header">
        <h2 style={{color:'white', margin:0, fontSize:'16px'}}>
          {activeSignal.symbol} | {activeSignal.dir}
        </h2>
        <div className="chart-actions">
          <button
            className={`chart-toggle ${!showTv ? 'active' : ''}`}
            onClick={() => {
              setChartView('journal');
              setShowTv(false);
            }}
          >
            Trade Graph
          </button>
          <button
            className={`chart-toggle ${showTv ? 'active' : ''}`}
            onClick={() => {
              setChartView('tv');
              setShowTv(true);
            }}
          >
            Live Graph
          </button>
        </div>
      </div>
      <button id="close-modal" onClick={() => setActiveSignal(null)}>
        Kapat <span className="esc-pill">ESC</span>
      </button>
      {!showTv && activeSignal && (
        <div className="position-panel">
          <div className="position-row">
            <span>Sembol</span>
            <b>{activeSignal.symbol}</b>
          </div>
          <div className="position-row">
            <span>Yön</span>
            <b>{activeSignal.dir}</b>
          </div>
          <div className="position-row">
            <span>Entry</span>
            <b>{activeSignal.entry?.toFixed(4)}</b>
          </div>
          <div className="position-row">
            <span>TP / SL</span>
            <b>
              <span className="pos-tp">{activeSignal.tp?.toFixed(4)}</span>
              {' / '}
              <span className="pos-sl">{activeSignal.sl?.toFixed(4)}</span>
            </b>
          </div>
          <div className="position-row">
            <span>Çıkış</span>
            <b>{activeSignal.exitPrice?.toFixed(4)}</b>
          </div>
          <div className="position-row">
            <span>Durum</span>
            <b className={activeSignal.status === 'TP' ? 'win' : activeSignal.status === 'SL' ? 'loss' : ''}>
              {activeSignal.status}
            </b>
          </div>
          <div className="position-row">
            <span>PnL</span>
            <b className={calculatePnL(activeSignal) >= 0 ? 'win' : 'loss'}>
              {calculatePnL(activeSignal) !== null ? `${calculatePnL(activeSignal).toFixed(2)}%` : '--'}
            </b>
          </div>
          <div className="position-row">
            <span>Süre</span>
            <b>
              {activeSignal.exitTs
                ? `${Math.max(1, Math.round((activeSignal.exitTs - activeSignal.dateObj.getTime()) / 60000))} dk`
                : '--'}
            </b>
          </div>
        </div>
      )}
      {chartError && !showTv && (
        <div className="chart-warning">{chartError}</div>
      )}
      {chartLoading && !showTv && (
        <div className="chart-warning">Grafik yükleniyor...</div>
      )}
      <div
        ref={chartContainerRef}
        id="chart-container"
        className="journal-chart"
        style={{ width: '100%', height: '100%', minHeight: '520px', display: showTv ? 'none' : 'block' }}
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
