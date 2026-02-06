import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, BaselineSeries, LineSeries } from 'lightweight-charts';
import { useTradeContext } from '../context/TradeContext';

const ChartModal = () => {
  const { activeSignal, setActiveSignal, chartView, setChartView } = useTradeContext();
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const [showTv, setShowTv] = useState(chartView === 'tv');
  const [chartError, setChartError] = useState('');
  const [chartLoading, setChartLoading] = useState(false);

  // PnL Hesaplama
  const calculatePnL = (sig) => {
    if (!sig || !sig.entry || !sig.exitPrice) return null;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };

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

    // --- TEMA AYARLARI ---
    const themeConfig = {
      bg: '#131722',           // TradingView Dark
      text: '#d1d4dc',         
      grid: 'transparent',     // Gridler gizli
      upColor: '#089981',      // TV Yeşili
      downColor: '#F23645',    // TV Kırmızısı
      wickUp: '#089981',
      wickDown: '#F23645',
    };

    const chart = createChart(chartContainerRef.current, {
      layout: { 
        background: { type: 'solid', color: themeConfig.bg }, 
        textColor: themeConfig.text,
        fontFamily: "'Trebuchet MS', Roboto, Ubuntu, sans-serif"
      },
      grid: { 
        vertLines: { visible: false }, 
        horzLines: { visible: false } 
      },
      width,
      height,
      rightPriceScale: { 
        borderColor: 'rgba(197, 203, 206, 0.2)',
        scaleMargins: { top: 0.2, bottom: 0.2 },
      },
      timeScale: { 
        timeVisible: true, 
        secondsVisible: true,
        borderColor: 'rgba(197, 203, 206, 0.2)' 
      },
      crosshair: {
        mode: 1,
        vertLine: { color: '#9598a1', style: 2, labelBackgroundColor: '#9598a1' },
        horzLine: { color: '#9598a1', style: 2, labelBackgroundColor: '#9598a1' }
      }
    });
    chartRef.current = chart;

    // 1. Ana Mum Grafiği
    const mainSeries = chart.addSeries(CandlestickSeries, {
      upColor: themeConfig.upColor,
      downColor: themeConfig.downColor,
      borderVisible: false,
      wickUpColor: themeConfig.wickUp,
      wickDownColor: themeConfig.wickDown
    });

    const fetchAndRender = async () => {
      setChartError('');
      try {
        const entryTime = activeSignal.dateObj.getTime();
        const exitTime = activeSignal.exitTs || entryTime + (60 * 60 * 1000);
        
        // Geniş bir aralık çekelim (Görsel bütünlük için)
        const fetchStartTime = entryTime - (60 * 1000 * 120); 
        const fetchEndTime = exitTime + (60 * 1000 * 60);     
        const baseSymbol = normalizeForBinance(activeSignal.symbol);

        let data = [];
        const urlFutures = `https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
        const res = await fetch(urlFutures);
        let rawData = await res.json();

        if (!Array.isArray(rawData)) {
          const urlSpot = `https://api.binance.com/api/v3/klines?symbol=${baseSymbol}&interval=1m&startTime=${fetchStartTime}&endTime=${fetchEndTime}&limit=1500`;
          const resSpot = await fetch(urlSpot);
          rawData = await resSpot.json();
        }

        if (!Array.isArray(rawData) || rawData.length === 0) {
          throw new Error('Kline verisi boş');
        }

        const candles = rawData.map(d => ({
          time: d[0] / 1000,
          open: parseFloat(d[1]),
          high: parseFloat(d[2]),
          low: parseFloat(d[3]),
          close: parseFloat(d[4])
        }));

        mainSeries.setData(candles);

        const { entry, tp, sl, dir } = activeSignal;
        const entryTs = Math.floor(entryTime / 1000);
        const exitTsReal = Math.floor(exitTime / 1000);
        const isLong = dir === 'LONG';

        // --- 2. TRADE ALANI (Görseldeki gibi sadece işlem süresince boyalı) ---
        // Baseline Series kullanarak Entry fiyatını baz alıp boyama yapıyoruz.
        // ÖNEMLİ: Sadece Entry ve Exit arasındaki datayı veriyoruz.
        
        if (entry) {
          const pnlSeries = chart.addSeries(BaselineSeries, {
            baseValue: { type: 'price', price: entry },
            // Long işlemde kar (üst) yeşil, zarar (alt) kırmızı
            // Short işlemde kar (alt) yeşil, zarar (üst) kırmızı
            topLineColor: 'rgba(0,0,0,0)', 
            topFillColor1: isLong ? 'rgba(8, 153, 129, 0.25)' : 'rgba(242, 54, 69, 0.25)', 
            topFillColor2: isLong ? 'rgba(8, 153, 129, 0.05)' : 'rgba(242, 54, 69, 0.05)',
            
            bottomLineColor: 'rgba(0,0,0,0)',
            bottomFillColor1: isLong ? 'rgba(242, 54, 69, 0.25)' : 'rgba(8, 153, 129, 0.25)',
            bottomFillColor2: isLong ? 'rgba(242, 54, 69, 0.05)' : 'rgba(8, 153, 129, 0.05)',
            
            lineWidth: 0, 
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false
          });

          // Datayı filtrele: Sadece işlem süresi
          const tradePeriodData = candles
            .filter(c => c.time >= entryTs && c.time <= exitTsReal)
            .map(c => ({ time: c.time, value: c.close }));
            
          pnlSeries.setData(tradePeriodData);
        }

        // --- 3. DASHED LINE (Girişten Çıkışa Kesikli Çizgi) ---
        if (entry) {
            const trendLineSeries = chart.addSeries(LineSeries, {
                color: '#d1d4dc',
                lineWidth: 1,
                lineStyle: 2, // Dashed
                crosshairMarkerVisible: false,
                lastValueVisible: false,
                priceLineVisible: false
            });
            
            // İki nokta: Başlangıç ve Bitiş
            // Bitiş fiyatı exitPrice, eğer yoksa son kapanış
            const endPrice = activeSignal.exitPrice || candles[candles.length-1].close;
            
            trendLineSeries.setData([
                { time: entryTs, value: entry },
                { time: exitTsReal, value: endPrice }
            ]);

            // --- 4. NOKTA (POINT) İŞARETÇİLERİ ---
            const markers = [];
            
            // Entry Noktası (Mavi Daire)
            markers.push({
                time: entryTs,
                position: 'inBar',
                color: '#2962FF',
                shape: 'circle',
                size: 2, // Biraz daha belirgin
            });

            // Exit Noktası (Varsa)
            if (activeSignal.exitPrice) {
                 markers.push({
                    time: exitTsReal,
                    position: 'inBar',
                    color: calculatePnL(activeSignal) >= 0 ? '#089981' : '#F23645',
                    shape: 'circle',
                    size: 2,
                });
            }
            // TrendLine üzerine marker ekleyemiyoruz ama Main seriye ekleyebiliriz
            // Ancak zamanlar main seride olmalı.
            
            // Biz burada mainSeries üzerine ekleyelim görsel olarak
            const mainMarkers = [];
            
            // Entry Marker (Ok yerine görseldeki gibi point/circle mantığı için yazı eklemiyoruz)
            mainMarkers.push({
              time: entryTs,
              position: isLong ? 'belowBar' : 'aboveBar',
              color: '#2962FF',
              shape: 'arrowUp', // Yönü göstermek için ok daha iyi, ama kullanıcı point istedi.
              text: 'ENTRY'     // Circle shape lightweight-charts markerlarında kısıtlı, 'circle' yok, arrow var.
                                // Circle efekti için series marker yerine custom yapılabilir ama 'circle' şekli en yakın 'circle' yoksa idare edeceğiz.
                                // Workaround: shape: 'circle' lightweight charts v4'te geldi.
            });

            // Sadece işlem kapanışına görsel marker
            if (activeSignal.exitTs) {
               if(exitTsReal <= candles[candles.length - 1].time) {
                 mainMarkers.push({
                   time: exitTsReal,
                   position: isLong ? 'aboveBar' : 'belowBar',
                   color: activeSignal.status === 'TP' ? '#089981' : '#F23645',
                   shape: 'arrowDown',
                   text: activeSignal.status
                 });
               }
            }
            mainSeries.setMarkers(mainMarkers);
        }

        // Fiyat Çizgileri (Entry, TP, SL)
        if (entry) {
          mainSeries.createPriceLine({
            price: entry,
            color: '#2962FF',
            lineWidth: 1,
            lineStyle: 0,
            axisLabelVisible: true,
            title: 'Giriş',
          });
        }
        if (tp) {
          mainSeries.createPriceLine({
            price: tp,
            color: '#089981',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: 'TP',
          });
        }
        if (sl) {
          mainSeries.createPriceLine({
            price: sl,
            color: '#F23645',
            lineWidth: 1,
            lineStyle: 2, 
            axisLabelVisible: true,
            title: 'SL',
          });
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
      chart.remove();
      chartRef.current = null;
    };
  }, [activeSignal, showTv]);

  const formatSignalTime = (dateObj) => {
    if (!dateObj) return '--';
    return dateObj.toLocaleString('tr-TR', { 
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' 
    });
  };

  useEffect(() => {
    if (!showTv) return;
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }
    if (chartContainerRef.current) chartContainerRef.current.innerHTML = '';
    setChartLoading(false);
    setChartError('');
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
        <div className="chart-actions">
          <button className={`chart-toggle ${!showTv ? 'active' : ''}`} onClick={() => { setChartView('journal'); setShowTv(false); }}>Analiz</button>
          <button className={`chart-toggle ${showTv ? 'active' : ''}`} onClick={() => { setChartView('tv'); setShowTv(true); }}>Canlı (TV)</button>
        </div>
      </div>
      
      <button id="close-modal" onClick={() => setActiveSignal(null)} style={{ color:'white' }}>Kapat <span className="esc-pill">ESC</span></button>

      {!showTv && activeSignal && (
        <div className="position-panel" style={{ backgroundColor: '#1e222d', borderRight: '1px solid #2a2e39' }}>
          <div className="position-row">
            <span>Tarih</span>
            <b style={{fontSize:'0.9em'}}>{formatSignalTime(activeSignal.dateObj)}</b>
          </div>
          <div className="position-row"><span>Giriş</span><b>{activeSignal.entry?.toFixed(4)}</b></div>
          <div className="position-row">
             <span>Hedef/Stop</span>
             <b><span style={{color:'#089981'}}>{activeSignal.tp?.toFixed(4)}</span> / <span style={{color:'#F23645'}}>{activeSignal.sl?.toFixed(4)}</span></b>
          </div>
          <div className="position-row">
            <span>Çıkış</span>
            <b>{activeSignal.exitPrice ? activeSignal.exitPrice.toFixed(4) : '--'}</b>
          </div>
          <div className="position-row">
            <span>PnL</span>
            <b style={{color: calculatePnL(activeSignal) >= 0 ? '#089981' : '#F23645'}}>
              {calculatePnL(activeSignal) !== null ? `${calculatePnL(activeSignal).toFixed(2)}%` : '--'}
            </b>
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