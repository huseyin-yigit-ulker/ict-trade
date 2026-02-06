import { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';
import { useTradeContext } from '../context/TradeContext';

const ChartModal = () => {
  const { activeSignal, setActiveSignal } = useTradeContext();
  const chartContainerRef = useRef(null);

  useEffect(() => {
    if (!activeSignal || !chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { backgroundColor: '#131722', textColor: '#d1d4dc' },
      grid: { vertLines: { color: '#242938' }, horzLines: { color: '#242938' } },
      timeScale: { timeVisible: true, secondsVisible: false },
      width: chartContainerRef.current.clientWidth,
      height: 500,
    });

    const series = chart.addCandlestickSeries({
      upColor: '#089981', downColor: '#F23645', borderVisible: false, wickUpColor: '#089981', wickDownColor: '#F23645'
    });

    // Binance Verisi
    const fetchAndRender = async () => {
      const entryTime = activeSignal.dateObj.getTime();
      const fetchStartTime = entryTime - (60 * 60 * 1000 * 4);
      const fetchEndTime = activeSignal.exitTs + (60 * 60 * 1000 * 4);
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
        
        series.createPriceLine({ price: activeSignal.entry, color: '#787b86', lineWidth: 1, lineStyle: 2, title: 'ENTRY' });
        series.createPriceLine({ price: activeSignal.tp, color: '#089981', lineWidth: 2, title: 'TP' });
        series.createPriceLine({ price: activeSignal.sl, color: '#F23645', lineWidth: 2, title: 'SL' });

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