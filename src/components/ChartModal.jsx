import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, BaselineSeries } from 'lightweight-charts';
import { useTradeContext } from '../context/TradeContext';

const ChartModal = () => {
  const { activeSignal, setActiveSignal, chartView, setChartView, mode } = useTradeContext();
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const intervalRef = useRef(null); // Interval'i güvenli yönetmek için Ref

  const [showTv, setShowTv] = useState(chartView === 'tv');
  const [chartError, setChartError] = useState('');
  const [chartLoading, setChartLoading] = useState(false);
  const [hoverInfo, setHoverInfo] = useState(null);
  const [liveTradeStatus, setLiveTradeStatus] = useState('');

  // --- Yardımcı Fonksiyonlar ---
  const calculatePnL = (sig) => {
    if (Number.isFinite(sig?.pnlR)) return sig.pnlR;
    if (!sig || !sig.entry || !sig.exitPrice) return null;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };
  const formatPnL = (sig, pnl) => (Number.isFinite(sig?.pnlR) ? `${pnl.toFixed(2)}R` : `${pnl.toFixed(2)}%`);

  const normalizeForBinance = (sym) => sym ? sym.replace(/[^A-Za-z0-9]/g, '') : '';
  const normalizeForTv = (sym) => sym ? sym.replace(/[^A-Za-z0-9.]/g, '') : '';
  
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
      symbol: tvSymbol, interval: '1', theme: 'dark', style: '1',
      toolbarbg: '1a2333', enable_publishing: 'false', hide_side_toolbar: 'false',
      allow_symbol_change: 'true', studies: '["Volume@tv-basicstudies"]',
      locale: 'tr', withdateranges: 'true', hideideas: 'true', autosize: 'true'
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
      bg: '#131722', text: '#d1d4dc', grid: 'transparent',
      upColor: '#089981', downColor: '#F23645',
      wickUp: '#089981', wickDown: '#F23645',
    };

    // 1. CHART OLUŞTURMA
    const chart = createChart(chartContainerRef.current, {
      layout: { 
        background: { type: 'solid', color: themeConfig.bg }, 
        textColor: themeConfig.text,
        fontFamily: "'Trebuchet MS', Roboto, Ubuntu, sans-serif"
      },
      localization: {
        locale: 'tr-TR', dateFormat: 'dd MMM yyyy',
        timeFormatter: (timestamp) => {
            const date = new Date(timestamp * 1000);
            return date.toLocaleString('tr-TR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
        }
      },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      width, height,
      rightPriceScale: { borderColor: 'rgba(197, 203, 206, 0.2)', scaleMargins: { top: 0.2, bottom: 0.2 } },
      timeScale: { 
        timeVisible: true, secondsVisible: false, borderColor: 'rgba(197, 203, 206, 0.2)',
        tickMarkFormatter: (time, tickMarkType) => {
            const date = new Date(time * 1000);
            if (tickMarkType < 3) return date.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' });
            return date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
        }
      },
      crosshair: {
        mode: 1,
        vertLine: { color: '#9598a1', style: 2, labelBackgroundColor: '#9598a1' },
        horzLine: { color: '#9598a1', style: 2, labelBackgroundColor: '#9598a1' }
      }
    });
    chartRef.current = chart;

    // --- KATMAN 1: MODERN POZİSYON GÖRÜNÜMÜ (Baseline Series) ---
    // Bu seriler Entry seviyesini baz alarak üstünü ve altını boyar.
    
    // TP Bölgesi (Yeşil Alan için)
    const tpAreaSeries = chart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: activeSignal.entry },
        lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        priceFormat: { type: 'price', precision: 5, minMove: 0.00001 }
    });

    // SL Bölgesi (Kırmızı Alan için)
    const slAreaSeries = chart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: activeSignal.entry },
        lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        priceFormat: { type: 'price', precision: 5, minMove: 0.00001 }
    });

    // --- KATMAN 2: MUM GRAFİĞİ ---
    const mainSeries = chart.addSeries(CandlestickSeries, {
      upColor: themeConfig.upColor, downColor: themeConfig.downColor,
      borderVisible: false, wickUpColor: themeConfig.wickUp, wickDownColor: themeConfig.wickDown,
      priceFormat: { type: 'price', precision: 5, minMove: 0.00001 }
    });

    // ---------------------------------------------------------
    // VERİ ÇEKME VE MANTIK ALANI
    // ---------------------------------------------------------
    const fetchAndRender = async () => {
      setChartError('');
      try {
        const entryTime = activeSignal.dateObj.getTime();
        const fallbackBacktestEnd = entryTime + (60 * 1000 * 240);
        const backtestExitTsMs = Number.isFinite(activeSignal?.exitTs) ? activeSignal.exitTs : fallbackBacktestEnd;
        // Backend records exit_time as the OPEN of the bar that hit TP/SL.
        // Add a buffer so the actual hit wick is within the dataset; trim on the
        // frontend to stop at the real touch.
        const exitBufferMs = 2 * 60 * 60 * 1000; // 2h headroom to capture the hit bar
        const fetchEndTime = mode === 'live'
          ? Date.now()
          : Math.max(backtestExitTsMs + exitBufferMs, entryTime + (60 * 1000));
        const fetchStartTime = mode === 'live'
          ? (entryTime - (60 * 1000 * 120))
          : entryTime;
        const baseSymbol = normalizeForBinance(activeSignal.symbol);

        // Backtest trades can span days (1500 1m bars = ~25h). Pick a coarser
        // interval automatically so the full signal-to-close window fits.
        const pickInterval = () => {
          if (mode === 'live') return '1m';
          const hours = (fetchEndTime - fetchStartTime) / 3600000;
          if (hours <= 25) return '1m';
          if (hours <= 125) return '5m';     // up to ~5 days
          if (hours <= 375) return '15m';    // up to ~15 days
          return '1h';                        // long trades
        };
        const klineInterval = pickInterval();

        // 1. Veriyi Çek
        let rawData = [];
        const urlFutures = `https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=${klineInterval}&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
        const res = await fetch(urlFutures);
        rawData = await res.json();

        // Futures yoksa Spot dene
        if (!Array.isArray(rawData)) {
            const urlSpot = `https://api.binance.com/api/v3/klines?symbol=${baseSymbol}&interval=${klineInterval}&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
            const resSpot = await fetch(urlSpot);
            rawData = await resSpot.json();
        }

        if (!Array.isArray(rawData) || rawData.length === 0) throw new Error('Kline verisi boş');

        let candles = rawData.map(d => ({
          time: d[0] / 1000,
          open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
        }));

        // Backtest: trim candles to the first 1m bar that touches TP, SL or pre-entry invalidation.
        // This makes the chart show only the signal-to-close window even though we fetched extra.
        if (mode === 'backtest' && activeSignal.entry && activeSignal.tp && activeSignal.sl && candles.length > 0) {
          const isLongTrade = activeSignal.dir === 'LONG';
          const entrySec = Math.floor(entryTime / 1000);
          let entryHitLocal = false;
          let cutIdx = candles.length;
          for (let idx = 0; idx < candles.length; idx++) {
            const c = candles[idx];
            if (c.time < entrySec) continue;
            const tpHit = isLongTrade ? c.high >= activeSignal.tp : c.low <= activeSignal.tp;
            const slHit = isLongTrade ? c.low <= activeSignal.sl : c.high >= activeSignal.sl;
            if (!entryHitLocal) {
              const entryHit = isLongTrade ? c.low <= activeSignal.entry : c.high >= activeSignal.entry;
              if (!entryHit && (tpHit || slHit)) { cutIdx = idx + 1; break; }
              if (entryHit) {
                entryHitLocal = true;
                if (tpHit || slHit) { cutIdx = idx + 1; break; }
              }
            } else if (tpHit || slHit) {
              cutIdx = idx + 1;
              break;
            }
          }
          candles = candles.slice(0, cutIdx);
        }

        mainSeries.setData(candles);

        // 2. İşlem Durumunu Analiz Et (Trading Logic)
        const { entry, tp, sl, dir } = activeSignal;
        const entryTs = Math.floor(entryTime / 1000);
        const isLong = dir === 'LONG';
        
        let statusText = '⏳ Sinyal Bekliyor';
        let isTerminalState = false; // İşlem bitti mi?
        let isCancelled = false;
        // After trimming in backtest mode, the last candle IS the close bar.
        let endTimeForGraph = candles[candles.length - 1].time;

        if (mode === 'live' && entry && tp && sl && candles.length > 0) {
             let entryHit = false;

             for (const c of candles) {
                 if (c.time < entryTs) continue; 

                 const cHigh = c.high;
                 const cLow = c.low;

                 // A) Henüz giriş yapılmadıysa
                 if (!entryHit) {
                     const hitEntryLevel = isLong ? cLow <= entry : cHigh >= entry;
                     const hitTpLevel = isLong ? cHigh >= tp : cLow <= tp;
                     const hitSlLevel = isLong ? cLow <= sl : cHigh >= sl;

                     // İPTAL KONTROLÜ: Entry'ye gelmeden TP veya SL'ye değdi mi?
                     if (!hitEntryLevel && (hitTpLevel || hitSlLevel)) {
                         isCancelled = true;
                         isTerminalState = true;
                         statusText = '❌ İptal (Entry Öncesi Temas)';
                         endTimeForGraph = c.time; // Grafiği burada kes
                         break;
                     }

                     if (hitEntryLevel) {
                         entryHit = true;
                         statusText = '⚡ İşlem Aktif';
                     }
                 }

                 // B) Giriş yapıldıysa -> TP/SL Kontrolü
                 if (entryHit) {
                     const hitTpLevel = isLong ? cHigh >= tp : cLow <= tp;
                     const hitSlLevel = isLong ? cLow <= sl : cHigh >= sl;

                     if (hitTpLevel && hitSlLevel) {
                         statusText = '⚠️ TP/SL Aynı Mum';
                         isTerminalState = true;
                         endTimeForGraph = c.time;
                         break;
                     } else if (hitTpLevel) {
                         statusText = '✅ Hedef (TP) Alındı';
                         isTerminalState = true;
                         endTimeForGraph = c.time;
                         break;
                     } else if (hitSlLevel) {
                         statusText = '🛑 Stop (SL) Oldu';
                         isTerminalState = true;
                         endTimeForGraph = c.time;
                         break;
                     }
                 }
             }
        }
        if (mode === 'backtest') {
          if (activeSignal.status === 'TP') {
            statusText = '✅ Kapanış: TP';
            isTerminalState = true;
          } else if (activeSignal.status === 'SL') {
            statusText = '🛑 Kapanış: SL';
            isTerminalState = true;
          } else if (activeSignal.status === 'WAITING') {
            statusText = '⏳ Beklemede';
          }
        }

        setLiveTradeStatus(statusText);

        // 3. Veri Akışını Durdurma (Live Mode & Aktif Değilse)
        if (mode === 'live' && (isTerminalState || statusText !== '⚡ İşlem Aktif')) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }

        // 4. Modern Pozisyon Görünümü (TradingView Style)
        // BaselineSeries kullanarak Entry'nin üstünü/altını boyuyoruz.
        
        if (isLong) {
            // LONG: TP (Üst) Yeşil, SL (Alt) Kırmızı
            tpAreaSeries.applyOptions({
                topLineColor: '#089981', topFillColor1: 'rgba(8, 153, 129, 0.25)', topFillColor2: 'rgba(8, 153, 129, 0.05)',
                bottomLineColor: 'transparent', bottomFillColor1: 'transparent', bottomFillColor2: 'transparent'
            });
            slAreaSeries.applyOptions({
                topLineColor: 'transparent', topFillColor1: 'transparent', topFillColor2: 'transparent',
                bottomLineColor: '#F23645', bottomFillColor1: 'rgba(242, 54, 69, 0.25)', bottomFillColor2: 'rgba(242, 54, 69, 0.05)'
            });
        } else {
            // SHORT: TP (Alt) Yeşil, SL (Üst) Kırmızı
            tpAreaSeries.applyOptions({
                topLineColor: 'transparent', topFillColor1: 'transparent', topFillColor2: 'transparent',
                bottomLineColor: '#089981', bottomFillColor1: 'rgba(8, 153, 129, 0.25)', bottomFillColor2: 'rgba(8, 153, 129, 0.05)'
            });
            slAreaSeries.applyOptions({
                topLineColor: '#F23645', topFillColor1: 'rgba(242, 54, 69, 0.25)', topFillColor2: 'rgba(242, 54, 69, 0.05)',
                bottomLineColor: 'transparent', bottomFillColor1: 'transparent', bottomFillColor2: 'transparent'
            });
        }

        // Veriyi Serilere Ata
        if (entry && tp && sl) {
          // Entry anından -> Bitiş anına kadar bir kutu çiz (iptalde de)
          tpAreaSeries.setData([ { time: entryTs, value: tp }, { time: endTimeForGraph, value: tp } ]);
          slAreaSeries.setData([ { time: entryTs, value: sl }, { time: endTimeForGraph, value: sl } ]);
        } else {
          tpAreaSeries.setData([]);
          slAreaSeries.setData([]);
        }

        // 5. Referans Çizgileri (tek sefer)
        if (!chartRef.current._priceLinesAdded) {
          if (entry) mainSeries.createPriceLine({ price: entry, color: '#787B86', lineWidth: 1, lineStyle: 0, title: 'Giriş', axisLabelVisible: true });
          if (tp) mainSeries.createPriceLine({ price: tp, color: '#089981', lineWidth: 1, lineStyle: 2, title: 'TP', axisLabelVisible: true });
          if (sl) mainSeries.createPriceLine({ price: sl, color: '#F23645', lineWidth: 1, lineStyle: 2, title: 'SL', axisLabelVisible: true });
          if (mode === 'backtest' && activeSignal?.exitPrice) {
            mainSeries.createPriceLine({
              price: activeSignal.exitPrice,
              color: '#f4bf50',
              lineWidth: 1,
              lineStyle: 1,
              title: 'Çıkış',
              axisLabelVisible: true
            });
          }
          chartRef.current._priceLinesAdded = true;
        }

        chart.timeScale().fitContent();
        setChartLoading(false);

      } catch (err) {
        setChartError('Veri alınamadı.');
        setChartLoading(false);
        console.error(err);
      }
    };

    fetchAndRender();
    if (mode === 'live') {
      intervalRef.current = setInterval(fetchAndRender, 3000); // 3 saniyede bir güncelle
    }

    // --- Crosshair ve Resize ---
    const handleCrosshairMove = (param) => {
      if (!param || !param.time || !param.seriesData) { setHoverInfo(null); return; }
      const candle = param.seriesData.get(mainSeries);
      if (!candle) { setHoverInfo(null); return; }
      setHoverInfo({ time: param.time, open: candle.open, high: candle.high, low: candle.low, close: candle.close });
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry && chartRef.current) {
        const { width: w, height: h } = entry.contentRect;
        chartRef.current.applyOptions({ width: w, height: h });
      }
    });
    observer.observe(chartContainerRef.current);

    return () => {
      observer.disconnect();
      if (intervalRef.current) clearInterval(intervalRef.current);
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.remove();
      chartRef.current = null;
    };
  }, [activeSignal, showTv, mode]);

  // UI Formatters
  const formatSignalTime = (dateObj) => dateObj ? dateObj.toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--';
  const formatHoverTime = (t) => t ? new Date(t * 1000).toLocaleString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--';
  const formatPrice = (value) => typeof value === 'number' ? value.toFixed(5) : '--';
  const activePnL = calculatePnL(activeSignal);

  useEffect(() => {
    if (!showTv && chartContainerRef.current) {}
  }, [showTv]);

  useEffect(() => {
    const handleEsc = (e) => e.key === 'Escape' && setActiveSignal(null);
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [setActiveSignal]);

  useEffect(() => { setShowTv(chartView === 'tv'); }, [activeSignal, chartView]);

  return (
    <div id="modal" style={{ display: 'block', backgroundColor: '#131722', color: '#d1d4dc' }}>
      <div id="chart-header" style={{ borderBottom: '1px solid #2a2e39', padding: '10px' }}>
        <h2 style={{color:'white', margin:0, fontSize:'16px'}}>
          {activeSignal?.symbol} <span style={{color: activeSignal?.dir === 'LONG' ? '#089981' : '#F23645'}}>{activeSignal?.dir}</span>
        </h2>
        {!showTv && hoverInfo && (
          <div className="chart-hover-info">
            {formatHoverTime(hoverInfo.time)} • O {formatPrice(hoverInfo.open)} H {formatPrice(hoverInfo.high)} L {formatPrice(hoverInfo.low)} C {formatPrice(hoverInfo.close)}
          </div>
        )}
      </div>
      
      <button id="close-modal" className="close-modern" onClick={() => setActiveSignal(null)}>
        <span className="close-label">Kapat</span><span className="esc-pill neo">ESC</span>
      </button>

      {!showTv && activeSignal && (
        <div className="position-panel" style={{ backgroundColor: '#1e222d', borderRight: '1px solid #2a2e39' }}>
          <div className="position-row"><span>Tarih</span><b>{formatSignalTime(activeSignal.dateObj)}</b></div>
          <div className="position-row"><span>Giriş</span><b>{formatPrice(activeSignal.entry)}</b></div>
          <div className="position-row">
             <span>Hedef/Stop</span>
             <b><span style={{color:'#089981'}}>{formatPrice(activeSignal.tp)}</span> / <span style={{color:'#F23645'}}>{formatPrice(activeSignal.sl)}</span></b>
          </div>
          <div className="position-row">
            <span>PnL</span>
            <b style={{color: activePnL === null || activePnL >= 0 ? '#089981' : '#F23645'}}>
              {activePnL !== null ? formatPnL(activeSignal, activePnL) : '--'}
            </b>
          </div>
          {mode === 'live' && (
            <div className="position-row">
              <span>Canlı Durum</span>
              <b style={{ color: liveTradeStatus.includes('İptal') || liveTradeStatus.includes('Stop') ? '#F23645' : liveTradeStatus.includes('Hedef') ? '#089981' : '#d1d4dc' }}>
                {liveTradeStatus || 'Hesaplanıyor...'}
              </b>
            </div>
          )}
        </div>
      )}

      {showTv && activeSignal && mode === 'live' && (
        <div className="position-panel horizontal bottom-left" style={{ backgroundColor: '#1e222d', borderRight: '1px solid #2a2e39' }}>
          <div className="position-row"><span>Sembol</span><b>{activeSignal.symbol}</b></div>
          <div className="position-row">
            <span>Yön</span>
            <b style={{ color: activeSignal.dir === 'LONG' ? '#089981' : '#F23645' }}>
              {activeSignal.dir}
            </b>
          </div>
          <div className="position-row"><span>Sinyal</span><b>{formatSignalTime(activeSignal.dateObj)}</b></div>
          <div className="position-row"><span>Entry</span><b>{formatPrice(activeSignal.entry)}</b></div>
          <div className="position-row">
            <span>TP / SL</span>
            <b><span style={{color:'#089981'}}>{formatPrice(activeSignal.tp)}</span> / <span style={{color:'#F23645'}}>{formatPrice(activeSignal.sl)}</span></b>
          </div>
        </div>
      )}

      {chartError && !showTv && <div className="chart-warning" style={{color:'#F23645'}}>{chartError}</div>}
      {chartLoading && !showTv && <div className="chart-warning">Veriler yükleniyor...</div>}

      <div
        ref={chartContainerRef}
        id="chart-container"
        className="journal-chart"
        style={{ width: '100%', height: '100%', minHeight: '520px', display: showTv ? 'none' : 'block', backgroundColor: '#131722' }}
      ></div>

      {showTv && (
        <iframe className="tv-iframe" title="TradingView" src={getTvEmbedUrl()} frameBorder="0" allowTransparency="true" allow="fullscreen; clipboard-write" loading="lazy" />
      )}
    </div>
  );
};

export default ChartModal;
