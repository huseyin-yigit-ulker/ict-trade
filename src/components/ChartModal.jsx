import { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';
import { useTradeContext } from '../context/TradeContext';

const ChartModal = () => {
  const { activeSignal, setActiveSignal } = useTradeContext();
  const chartContainerRef = useRef(null);

  useEffect(() => {
    if (!activeSignal || !chartContainerRef.current) return;

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
      const entryTime = activeSignal.dateObj.getTime();
      const exitTime = activeSignal.exitTs || entryTime + (20 * 60 * 1000);
      const fetchStartTime = entryTime - (60 * 1000 * 20);
      const fetchEndTime = exitTime + (60 * 1000 * 20);
      const baseSymbol = activeSignal.symbol.replace('1000', '');

      try {
        const url = `https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
        const res = await fetch(url);
        const data = await res.json();
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
        console.error("Chart Data Error:", err);
      }
    };

    fetchAndRender();

    return () => chart.remove();
  }, [activeSignal]);

  useEffect(() => {
    const handleEsc = (e) => e.key === 'Escape' && setActiveSignal(null);
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [setActiveSignal]);

  return (
    <div id="modal" style={{ display: 'block' }}>
      <div id="chart-header">
        <h2 style={{color:'white', margin:0, fontSize:'16px'}}>
          {activeSignal.symbol} | {activeSignal.dir}
        </h2>
      </div>
      <button id="close-modal" onClick={() => setActiveSignal(null)}>KAPAT [ESC]</button>
      <div ref={chartContainerRef} id="chart-container" style={{ width: '100%', height: '100%' }}></div>
    </div>
  );
};

export default ChartModal;
