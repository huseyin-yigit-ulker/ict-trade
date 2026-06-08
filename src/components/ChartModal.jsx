import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, LineSeries, BaselineSeries, createSeriesMarkers } from 'lightweight-charts';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';

const IconCandles = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.3">
    <line x1="4" y1="1.3" x2="4" y2="12.7" /><rect x="2.4" y="4" width="3.2" height="5.2" fill="currentColor" stroke="none" />
    <line x1="10" y1="2.4" x2="10" y2="11.6" /><rect x="8.4" y="5.4" width="3.2" height="4.2" fill="currentColor" stroke="none" />
  </svg>
);
const IconLine = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="1,10 5,6 8.5,8.5 13,2" />
  </svg>
);

// Entry-fill timeout (mirror of TradeContext ENTRY_EXPIRY_MINUTES / backtest EXPIRY_MINUTES):
// a signal that never fills is cancelled this many minutes after the signal fires.
const ENTRY_EXPIRY_MINUTES = 180;

const ChartModal = () => {
  const { activeSignal, setActiveSignal, chartView, setChartView, mode, liveStatuses } = useTradeContext();
  const { t, locale } = useLang();
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const intervalRef = useRef(null); // Interval'i güvenli yönetmek için Ref

  const [showTv, setShowTv] = useState(chartView === 'tv');
  const [chartError, setChartError] = useState('');
  const [chartLoading, setChartLoading] = useState(false);
  const [hoverInfo, setHoverInfo] = useState(null);

  // Candle ↔ line series toggle (persisted). Debug ergonomics: line reads
  // structure faster at low zoom, candles for bar-by-bar detail.
  const [chartStyle, setChartStyle] = useState(() => {
    try { return localStorage.getItem('pusu.chartStyle') === 'line' ? 'line' : 'candles'; } catch { return 'candles'; }
  });
  const setChartStyleP = (s) => { setChartStyle(s); try { localStorage.setItem('pusu.chartStyle', s); } catch { /* ignore */ } };

  // Draggable + collapsible info panel so it never hides price action.
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [panelPos, setPanelPos] = useState(null);   // {x,y} in viewport coords once dragged
  const panelRef = useRef(null);
  const startPanelDrag = (e) => {
    if (!panelRef.current || e.button === 2) return;
    const rect = panelRef.current.getBoundingClientRect();
    const offX = e.clientX - rect.left, offY = e.clientY - rect.top;
    const move = (ev) => setPanelPos({ x: Math.max(0, ev.clientX - offX), y: Math.max(0, ev.clientY - offY) });
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  // Single source of truth for live status: TradeContext.liveStatuses
  // (the dashboard's polled value). Compact label + colored dot — same
  // mapping as the dashboard so the two views read identical.
  const LIVE_STATUS_DISPLAY = {
    'TP Oldu':                      { label: 'TP',       cls: 'st-tp' },
    'SL Oldu':                      { label: 'SL',       cls: 'st-sl' },
    'TP/SL Aynı Mum':               { label: 'TP+SL',    cls: 'st-mixed' },
    'İşlem Aktif (Entry Geldi)':    { label: 'AKTİF',    cls: 'st-active' },
    'İptal (Entry Gelmeden TP/SL)': { label: 'İPTAL',    cls: 'st-cancel' },
    'İptal (Süre Doldu)':           { label: 'İPTAL',    cls: 'st-cancel' },
    'Sinyal Bekliyor':              { label: 'BEKLİYOR', cls: 'st-wait' },
  };
  const ctxLiveStatus = (mode === 'live' && activeSignal) ? liveStatuses[activeSignal.id]?.status : null;
  const liveDisplay = LIVE_STATUS_DISPLAY[ctxLiveStatus] || (ctxLiveStatus ? null : null);
  const liveTradeStatus = liveDisplay ? liveDisplay.label : (mode === 'live' ? t('Hesaplanıyor...') : '');

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

    let cancelled = false;   // guards async resume after cleanup (modal close / StrictMode)
    setChartLoading(true);
    chartContainerRef.current.innerHTML = '';

    const rect = chartContainerRef.current.getBoundingClientRect();
    const width = rect.width > 0 ? rect.width : 900;
    const height = rect.height > 0 ? rect.height : 520;

    // Binance-aligned palette: yellow accents not used here, but candle/wick
    // colors and crosshair match the dashboard's --win / --loss / --muted tokens.
    const themeConfig = {
      bg: '#0B0E11', text: '#EAECEF', grid: 'transparent',
      upColor: '#0ECB81', downColor: '#F6465D',
      wickUp: '#0ECB81', wickDown: '#F6465D',
    };

    // 1. CHART OLUŞTURMA
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: 'solid', color: themeConfig.bg },
        textColor: themeConfig.text,
        fontFamily: "'JetBrains Mono', 'SF Mono', 'Roboto Mono', Consolas, monospace"
      },
      localization: {
        locale: locale, dateFormat: 'dd MMM yyyy',
        timeFormatter: (timestamp) => {
            const date = new Date(timestamp * 1000);
            return date.toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
        }
      },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      width, height,
      rightPriceScale: { borderColor: '#2B3139', scaleMargins: { top: 0.2, bottom: 0.2 } },
      timeScale: {
        timeVisible: true, secondsVisible: false, borderColor: '#2B3139',
        tickMarkFormatter: (time, tickMarkType) => {
            const date = new Date(time * 1000);
            if (tickMarkType < 3) return date.toLocaleDateString(locale, { day: 'numeric', month: 'short' });
            return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
        }
      },
      crosshair: {
        mode: 1,
        vertLine: { color: '#848E9C', style: 2, labelBackgroundColor: '#1E2329' },
        horzLine: { color: '#848E9C', style: 2, labelBackgroundColor: '#1E2329' }
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

    // --- KATMAN 2: ANA SERİ (mum ↔ çizgi) ---
    const isLineChart = chartStyle === 'line';
    const mainSeries = isLineChart
      ? chart.addSeries(LineSeries, {
          color: '#EAECEF', lineWidth: 2, lastValueVisible: false, crosshairMarkerVisible: true,
          priceFormat: { type: 'price', precision: 5, minMove: 0.00001 }
        })
      : chart.addSeries(CandlestickSeries, {
          upColor: themeConfig.upColor, downColor: themeConfig.downColor,
          borderVisible: true, wickUpColor: themeConfig.wickUp, wickDownColor: themeConfig.wickDown,
          priceFormat: { type: 'price', precision: 5, minMove: 0.00001 }
        });

    // ---------------------------------------------------------
    // VERİ ÇEKME VE MANTIK ALANI
    // ---------------------------------------------------------
    const fetchAndRender = async () => {
      setChartError('');
      try {
        const entryTime = activeSignal.dateObj.getTime();   // signal bar OPEN
        const signalOpenMs = entryTime;
        const fallbackBacktestEnd = entryTime + (60 * 1000 * 240);
        const backtestExitTsMs = Number.isFinite(activeSignal?.exitTs) ? activeSignal.exitTs : fallbackBacktestEnd;
        const exitBufferMs = 2 * 60 * 60 * 1000; // headroom so the hit wick is in the dataset

        const intervalMs = (tf) => {
          const m = String(tf || '1h').match(/^(\d+)([smhd])$/i);
          if (!m) return 60 * 60 * 1000;
          const units = { s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000 };
          return Number(m[1]) * units[m[2].toLowerCase()];
        };

        // --- Context padding, measured in SIGNAL-timeframe periods ---
        // Show ~PAD_BARS bars BEFORE the signal (ÖNCE) and AFTER the close (SONRA)
        // so the trade is never glued to the chart edge.
        const PAD_BARS = 6;          // 5-10 band
        const MIN_PAD_DISPLAY = 8;   // floor in display bars so short-TF (1m live) still breathes
        const ltfMs = intervalMs(activeSignal.ltfTimeframe);
        let padMs = PAD_BARS * ltfMs;

        // Window extends BACKWARD before the signal in BOTH modes (drop the old
        // live "+1 bar push-forward" so the run-up into the signal is visible).
        let fetchStartTime = signalOpenMs - padMs;
        const fetchEndTime = mode === 'live'
          ? Date.now()
          : Math.max(backtestExitTsMs + Math.max(exitBufferMs, padMs), signalOpenMs + 60 * 1000);

        // Display interval chosen over the PADDED span; coarsen so it fits <=1500 bars.
        const ladder = ['1m', '5m', '15m', '1h', '4h', '1d', '1w'];
        const pickInterval = () => {
          if (mode === 'live') return '1m';
          const hours = (fetchEndTime - fetchStartTime) / 3600000;
          if (hours <= 25) return '1m';
          if (hours <= 125) return '5m';     // ~5 days
          if (hours <= 375) return '15m';    // ~15 days
          return '1h';
        };
        let klineInterval = pickInterval();
        while (mode !== 'live' && (fetchEndTime - fetchStartTime) / intervalMs(klineInterval) > 1450) {
          const i = ladder.indexOf(klineInterval);
          if (i < 0 || i === ladder.length - 1) break;
          klineInterval = ladder[i + 1];
        }
        // Live stays 1m — clamp the start so it never exceeds ~1450 bars.
        if (mode === 'live') {
          const liveMaxStart = Date.now() - 1450 * 60000;
          if (fetchStartTime < liveMaxStart) fetchStartTime = liveMaxStart;
        }
        // Pad floor in display bars (visible context even on coarse intervals).
        const displayMs = intervalMs(klineInterval);
        padMs = Math.max(PAD_BARS * ltfMs, MIN_PAD_DISPLAY * displayMs);
        const padBarsDisplay = Math.ceil(padMs / displayMs);

        const baseSymbol = normalizeForBinance(activeSignal.symbol);

        // 1. Veriyi Çek
        let rawData = [];
        const urlFutures = `https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=${klineInterval}&startTime=${Math.floor(fetchStartTime)}&endTime=${Math.floor(fetchEndTime)}&limit=1500`;
        const res = await fetch(urlFutures);
        rawData = await res.json();

        // Futures yoksa Spot dene
        if (!Array.isArray(rawData)) {
            const urlSpot = `https://api.binance.com/api/v3/klines?symbol=${baseSymbol}&interval=${klineInterval}&startTime=${Math.floor(fetchStartTime)}&endTime=${Math.floor(fetchEndTime)}&limit=1500`;
            const resSpot = await fetch(urlSpot);
            rawData = await resSpot.json();
        }

        if (cancelled || !chartRef.current) return;   // modal closed / re-opened while fetching

        if (!Array.isArray(rawData) || rawData.length === 0) throw new Error('Kline verisi boş');

        let candles = rawData.map(d => ({
          time: d[0] / 1000,
          open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
        }));

        const { entry, tp, sl, dir } = activeSignal;
        const isLong = dir === 'LONG';
        // Signal fires at bar CLOSE — scan entry-fill from there (backtest parity),
        // so an intrabar touch during the signal bar isn't mistaken for a fill.
        const entryTs = Math.floor((signalOpenMs + ltfMs) / 1000);

        // Snap a target ms to the first real candle at/after it (markers must land on a bar).
        const snapBar = (targetMs) => {
          const t = Math.floor(targetMs / 1000);
          const c = candles.find(cd => cd.time >= t);
          return c ? c.time : (candles.length ? candles[candles.length - 1].time : t);
        };
        // Is the signal bar inside the loaded window? (live clamp can push it out of view.)
        const signalVisible = candles.length > 0 && entryTs >= candles[0].time;

        // --- Touch scan (both modes): entry-fill bar + the bar that closed the trade ---
        let entryFilled = false, entryFillSec = null, closeBarSec = null, closeBarIdx = -1;
        if (entry && tp && sl && signalVisible) {
          let hit = false;
          for (let idx = 0; idx < candles.length; idx++) {
            const c = candles[idx];
            if (c.time < entryTs) continue;
            const tpHit = isLong ? c.high >= tp : c.low <= tp;
            const slHit = isLong ? c.low <= sl : c.high >= sl;
            if (!hit) {
              const eHit = isLong ? c.low <= entry : c.high >= entry;
              if (!eHit && (tpHit || slHit)) { closeBarSec = c.time; closeBarIdx = idx; break; } // pre-entry iptal
              if (eHit) {
                hit = true; entryFilled = true; entryFillSec = c.time;
                if (tpHit || slHit) { closeBarSec = c.time; closeBarIdx = idx; break; }
              }
            } else if (tpHit || slHit) { closeBarSec = c.time; closeBarIdx = idx; break; }
          }
        }

        // Fallback: a closed backtest trade whose coarse re-fetch missed the exact touch —
        // anchor the close to the DB exit_time so zone/trim/dimming/marker all agree.
        const backtestClosed = mode === 'backtest' && (activeSignal.status === 'TP' || activeSignal.status === 'SL');
        if (closeBarSec == null && backtestClosed && Number.isFinite(activeSignal.exitTs)) {
          closeBarSec = snapBar(activeSignal.exitTs);
          closeBarIdx = candles.findIndex(c => c.time === closeBarSec);
        }

        // Live terminal state — computed early so the close anchor + trim can use it.
        const ctxStatus = liveStatuses[activeSignal.id]?.status;
        const liveTerminalSet = new Set(['TP Oldu', 'SL Oldu', 'TP/SL Aynı Mum']);
        const liveTerminal = !!ctxStatus && (liveTerminalSet.has(ctxStatus) || ctxStatus.startsWith('İptal'));
        const isTerminalState = mode === 'backtest'
          ? (activeSignal.status === 'TP' || activeSignal.status === 'SL')
          : liveTerminal;

        // Live entry-fill timeout ('İptal (Süre Doldu)'): never filled, no TP/SL touch.
        // The trade ends at the fill deadline — anchor the close there so the zone,
        // dimming and exit marker all stop at the timeout, not at the latest candle.
        if (closeBarSec == null && mode === 'live' && ctxStatus === 'İptal (Süre Doldu)') {
          closeBarSec = snapBar(signalOpenMs + ENTRY_EXPIRY_MINUTES * 60 * 1000);
          closeBarIdx = candles.findIndex(c => c.time === closeBarSec);
        }

        // Keep ~PAD_BARS of SONRA context past the close, then stop — for backtest AND
        // any terminal live trade, so a timed-out/closed live trade shows a little more
        // price action after the exit and then ends, instead of trailing "now".
        if (closeBarIdx >= 0 && (mode === 'backtest' || liveTerminal)) {
          candles = candles.slice(0, Math.min(candles.length, closeBarIdx + 1 + padBarsDisplay));
        }

        // The signal fires at the bar CLOSE (signal_time = bar OPEN). Anchor the
        // "Sinyal" marker + pre-signal dimming at the close so the chart shows the
        // real moment the signal formed — matching the panel's "Tarih".
        const signalSec = snapBar(signalOpenMs + ltfMs);

        // --- Per-bar dimming: pre-signal context tinted violet, post-trade ghosted gray ---
        candles = candles.map((c) => {
          if (c.time < signalSec) return { ...c, color: '#322B45', wickColor: '#7C6BB0', borderColor: '#473A66' };
          if (closeBarSec != null && c.time > closeBarSec) return { ...c, color: '#2B3139', wickColor: '#5E6673', borderColor: '#2B3139' };
          return { ...c, borderColor: c.close >= c.open ? themeConfig.upColor : themeConfig.downColor };
        });

        if (isLineChart) mainSeries.setData(candles.map((c) => ({ time: c.time, value: c.close })));
        else mainSeries.setData(candles);

        // 2. Zone right edge — ends at the real close (backtest / terminal live), else last bar.
        let endTimeForGraph = candles.length ? candles[candles.length - 1].time : entryTs;
        if (closeBarSec != null && (mode === 'backtest' || liveTerminal)) endTimeForGraph = closeBarSec;

        // Stop the live refresh once the trade has terminated.
        if (mode === 'live' && isTerminalState && intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }

        // 3. Pozisyon bölgesi (entry baz; TP yeşil / SL kırmızı yarı-saydam, kapanışta biter)
        if (isLong) {
            tpAreaSeries.applyOptions({
                topLineColor: '#0ECB81', topFillColor1: 'rgba(14, 203, 129, 0.1)', topFillColor2: 'rgba(14, 203, 129, 0.02)',
                bottomLineColor: 'transparent', bottomFillColor1: 'transparent', bottomFillColor2: 'transparent'
            });
            slAreaSeries.applyOptions({
                topLineColor: 'transparent', topFillColor1: 'transparent', topFillColor2: 'transparent',
                bottomLineColor: '#F6465D', bottomFillColor1: 'rgba(246, 70, 93, 0.1)', bottomFillColor2: 'rgba(246, 70, 93, 0.02)'
            });
        } else {
            tpAreaSeries.applyOptions({
                topLineColor: 'transparent', topFillColor1: 'transparent', topFillColor2: 'transparent',
                bottomLineColor: '#0ECB81', bottomFillColor1: 'rgba(14, 203, 129, 0.1)', bottomFillColor2: 'rgba(14, 203, 129, 0.02)'
            });
            slAreaSeries.applyOptions({
                topLineColor: '#F6465D', topFillColor1: 'rgba(246, 70, 93, 0.1)', topFillColor2: 'rgba(246, 70, 93, 0.02)',
                bottomLineColor: 'transparent', bottomFillColor1: 'transparent', bottomFillColor2: 'transparent'
            });
        }
        if (entry && tp && sl) {
          tpAreaSeries.setData([ { time: entryTs, value: tp }, { time: endTimeForGraph, value: tp } ]);
          slAreaSeries.setData([ { time: entryTs, value: sl }, { time: endTimeForGraph, value: sl } ]);
        } else {
          tpAreaSeries.setData([]);
          slAreaSeries.setData([]);
        }

        // 4. Referans çizgileri (tek sefer) — eksen etiketine fiyat/yüzde
        if (!chartRef.current._priceLinesAdded) {
          const targetPct = entry && tp ? ((tp - entry) / entry) * 100 : null;
          const riskPct = entry && sl ? ((sl - entry) / entry) * 100 : null;
          if (entry) mainSeries.createPriceLine({ price: entry, color: '#848E9C', lineWidth: 1, lineStyle: 0, title: `${t('Giriş')} ${formatPrice(entry)}`, axisLabelVisible: true });
          if (tp) mainSeries.createPriceLine({ price: tp, color: '#0ECB81', lineWidth: 1, lineStyle: 2, title: `${t('TP')}${targetPct != null ? ' +' + Math.abs(targetPct).toFixed(1) + '%' : ''}`, axisLabelVisible: true });
          if (sl) mainSeries.createPriceLine({ price: sl, color: '#F6465D', lineWidth: 1, lineStyle: 2, title: `${t('SL')}${riskPct != null ? ' -' + Math.abs(riskPct).toFixed(1) + '%' : ''}`, axisLabelVisible: true });
          if (mode === 'backtest' && activeSignal?.exitPrice) {
            mainSeries.createPriceLine({ price: activeSignal.exitPrice, color: '#F0B90B', lineWidth: 1, lineStyle: 1, title: `${t('Çıkış')} ${formatPrice(activeSignal.exitPrice)}`, axisLabelVisible: true });
          }
          chartRef.current._priceLinesAdded = true;
        }

        // 4b. ICT KARAR GEOMETRİSİ — motorun işlemi tetikleyen FVG/OB/sweep/BOS'u.
        // entry_zone zaman-sınırlı kutu (üst+alt çizgi, oluşumdan kapanışa); swept
        // likidite + yapı kırılımı referans çizgisi. activeSignal.geometry yoksa atlanır.
        if (!chartRef.current._geoAdded) {
          const geo = activeSignal.geometry;
          if (geo) {
            const firstT = candles.length ? candles[0].time : entryTs;
            const zoneEnd = endTimeForGraph;
            const ez = geo.entry_zone;
            if (ez && Number.isFinite(ez.top) && Number.isFinite(ez.bottom)) {
              let zStart = Number.isFinite(ez.from) ? ez.from : entryTs;
              zStart = Math.max(firstT, Math.min(zStart, entryTs));
              if (zStart < zoneEnd) {
                const zColor = ez.kind === 'OB' ? '#7AA2F7' : '#9D7CD8';
                for (const edge of [ez.top, ez.bottom]) {
                  const s = chart.addSeries(LineSeries, {
                    color: zColor, lineWidth: 1, lineStyle: 2,
                    lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
                  });
                  s.setData([{ time: zStart, value: edge }, { time: zoneEnd, value: edge }]);
                }
                mainSeries.createPriceLine({ price: ez.top, color: zColor, lineWidth: 1, lineStyle: 2, title: ez.kind, axisLabelVisible: false });
              }
            }
            if (geo.swept && Number.isFinite(geo.swept.price)) {
              mainSeries.createPriceLine({ price: geo.swept.price, color: '#C792EA', lineWidth: 1, lineStyle: 3, title: `SWEEP ${geo.swept.type || ''}`.trim(), axisLabelVisible: false });
            }
            if (geo.structure && Number.isFinite(geo.structure.level)) {
              mainSeries.createPriceLine({ price: geo.structure.level, color: '#56C2E6', lineWidth: 1, lineStyle: 3, title: geo.structure.type || 'BOS', axisLabelVisible: false });
            }
          }
          chartRef.current._geoAdded = true;
        }

        // 5. Zaman-bağlı işaretler: Sinyal / Giriş / Çıkış (çıkış rengi sonuca göre)
        const isTP = (mode === 'backtest' && activeSignal.status === 'TP') || (mode === 'live' && ctxStatus === 'TP Oldu');
        const isSL = (mode === 'backtest' && activeSignal.status === 'SL') || (mode === 'live' && (ctxStatus === 'SL Oldu' || ctxStatus === 'TP/SL Aynı Mum'));
        const exitColor = isTP ? '#0ECB81' : isSL ? '#F6465D' : '#F0B90B';
        const exitText = isTP ? t('TP') : isSL ? t('SL') : t('Çıkış');
        const exitSec = closeBarSec != null ? closeBarSec : (Number.isFinite(activeSignal.exitTs) ? snapBar(activeSignal.exitTs) : null);

        const markers = [];
        if (signalVisible) markers.push({ time: signalSec, position: 'aboveBar', shape: 'circle', color: '#F0B90B', text: t('Sinyal'), size: 1 });
        if (entryFilled && entryFillSec != null && entryFillSec !== signalSec) {
          markers.push({ time: entryFillSec, position: isLong ? 'belowBar' : 'aboveBar', shape: isLong ? 'arrowUp' : 'arrowDown', color: '#F5B942', text: t('Giriş'), size: 1 });
        }
        if (isTerminalState && exitSec != null) {
          markers.push({ time: exitSec, position: isLong ? 'aboveBar' : 'belowBar', shape: isLong ? 'arrowDown' : 'arrowUp', color: exitColor, text: exitText, size: 1 });
        }
        markers.sort((a, b) => a.time - b.time);   // v5 requires ascending time
        if (!chartRef.current._markersApi) {
          chartRef.current._markersApi = createSeriesMarkers(mainSeries, markers);
        } else {
          chartRef.current._markersApi.setMarkers(markers);
        }

        // 6. Çerçeveleme: ÖNCE + İŞLEM + SONRA — yalnız ilk render'da (canlı yenilemede
        // kullanıcının pan/zoom'unu ezmemek için _priceLinesAdded gibi guard'lı).
        if (!chartRef.current._framed) {
          const tsApi = chart.timeScale();
          let toTime = candles.length ? candles[candles.length - 1].time : endTimeForGraph;
          if (isTerminalState && closeBarSec != null) {
            toTime = Math.min(toTime, closeBarSec + padBarsDisplay * (displayMs / 1000));
          }
          try {
            tsApi.setVisibleRange({ from: candles[0].time, to: toTime });
          } catch {
            tsApi.fitContent();
          }
          chartRef.current._framed = true;
        }

        setChartLoading(false);

      } catch (err) {
        setChartError(t('Veri alınamadı.'));
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
      const d = param.seriesData.get(mainSeries);
      if (!d) { setHoverInfo(null); return; }
      if (d.open !== undefined) setHoverInfo({ time: param.time, open: d.open, high: d.high, low: d.low, close: d.close });
      else setHoverInfo({ time: param.time, close: d.value });
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
      cancelled = true;
      observer.disconnect();
      if (intervalRef.current) clearInterval(intervalRef.current);
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      if (chartRef.current?._markersApi) { chartRef.current._markersApi.detach(); chartRef.current._markersApi = null; }
      chart.remove();
      chartRef.current = null;
    };
  }, [activeSignal, showTv, mode, chartStyle]);

  // UI Formatters
  const formatSignalTime = (dateObj) => dateObj ? dateObj.toLocaleString(locale, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--';
  const formatHoverTime = (ts) => ts ? new Date(ts * 1000).toLocaleString(locale, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--';
  // Dynamic decimal precision (matches Dashboard's formatter)
  const formatPrice = (value) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
    const abs = Math.abs(value);
    if (abs === 0) return '0';
    if (abs >= 100)  return value.toFixed(2);
    if (abs >= 1)    return value.toFixed(4);
    if (abs >= 0.01) return value.toFixed(5);
    if (abs >= 0.0001) return value.toFixed(7);
    return value.toPrecision(4);
  };
  const activePnL = calculatePnL(activeSignal);

  // signal_time in DB = bar OPEN; the signal actually fires at bar CLOSE.
  // Use this everywhere the UI shows "Tarih" / computes "Süre".
  const intervalMsLocal = (tf) => {
    const m = String(tf || '1h').match(/^(\d+)([smhd])$/i);
    if (!m) return 60 * 60 * 1000;
    const u = { s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000 };
    return Number(m[1]) * (u[m[2].toLowerCase()] || 0);
  };
  const effectiveSignalDate = (sig) => sig?.dateObj
    ? new Date(sig.dateObj.getTime() + intervalMsLocal(sig.ltfTimeframe))
    : null;

  // Pre-trade analytics: RR, target%, risk%, duration, current-price distance
  const computeRR = (sig) => {
    if (!sig?.entry || !sig?.sl || !sig?.tp) return null;
    const risk = Math.abs(sig.entry - sig.sl);
    const reward = Math.abs(sig.tp - sig.entry);
    if (risk === 0) return null;
    return reward / risk;
  };
  const pctDist = (a, b) => (!a || !b) ? null : ((b - a) / a) * 100;
  const formatDuration = (ms) => {
    if (!Number.isFinite(ms) || ms < 0) return '--';
    const mins = Math.floor(ms / 60000);
    if (mins < 60) return `${mins} dk`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} sa ${mins % 60} dk`;
    const days = Math.floor(hrs / 24);
    return `${days} gün ${hrs % 24} sa`;
  };

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
    <div id="modal" style={{ display: 'block', backgroundColor: '#0B0E11', color: '#EAECEF' }}>
      <div id="chart-header" style={{ borderBottom: '1px solid #2a2e39', padding: '10px' }}>
        <div className="chart-header-top">
          <h2 style={{color:'white', margin:0, fontSize:'16px'}}>
            {activeSignal?.symbol} <span style={{color: activeSignal?.dir === 'LONG' ? '#0ECB81' : '#F6465D'}}>{activeSignal?.dir}</span>
          </h2>
          {!showTv && (
            <div className="chart-style-seg" role="group" aria-label="chart style">
              <button className={chartStyle === 'candles' ? 'active' : ''} onClick={() => setChartStyleP('candles')} title={t('Mum')} aria-label={t('Mum')}><IconCandles /></button>
              <button className={chartStyle === 'line' ? 'active' : ''} onClick={() => setChartStyleP('line')} title={t('Çizgi')} aria-label={t('Çizgi')}><IconLine /></button>
            </div>
          )}
        </div>
        {!showTv && hoverInfo && (
          <div className="chart-hover-info">
            {formatHoverTime(hoverInfo.time)} • {hoverInfo.open !== undefined
              ? `O ${formatPrice(hoverInfo.open)} H ${formatPrice(hoverInfo.high)} L ${formatPrice(hoverInfo.low)} C ${formatPrice(hoverInfo.close)}`
              : `C ${formatPrice(hoverInfo.close)}`}
          </div>
        )}
      </div>
      
      <button id="close-modal" className="close-modern" onClick={() => setActiveSignal(null)}>
        <span className="close-label">{t('Kapat')}</span><span className="esc-pill neo">ESC</span>
      </button>

      {!showTv && activeSignal && (() => {
        const rr = computeRR(activeSignal);
        const targetPct = pctDist(activeSignal.entry, activeSignal.tp);
        const riskPct = pctDist(activeSignal.entry, activeSignal.sl);
        const liveLastPrice = mode === 'live' ? liveStatuses[activeSignal.id]?.lastPrice : null;
        const distToEntry = mode === 'live' ? pctDist(liveLastPrice, activeSignal.entry) : null;
        const effDate = effectiveSignalDate(activeSignal);
        const ageMs = effDate ? (Date.now() - effDate.getTime()) : null;
        // For closed backtest trades, duration is bar-close → exit_time.
        const closedDurationMs = mode === 'backtest' && activeSignal.exitTs && effDate
          ? activeSignal.exitTs - effDate.getTime()
          : null;
        const exitPrice = mode === 'backtest' ? activeSignal.exitPrice : null;

        return (
        <div
          ref={panelRef}
          className={`position-panel${panelCollapsed ? ' collapsed' : ''}`}
          style={{ backgroundColor: '#181A20', borderRight: '1px solid #2B3139', ...(panelPos ? { position: 'fixed', left: panelPos.x, top: panelPos.y, right: 'auto' } : {}) }}
        >
          <div className="position-panel__bar" onPointerDown={startPanelDrag}>
            <span className="position-panel__title">
              {activeSignal.symbol} · <span style={{ color: activeSignal.dir === 'LONG' ? '#0ECB81' : '#F6465D' }}>{activeSignal.dir}</span>
            </span>
            <button
              className="position-panel__btn"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => setPanelCollapsed((c) => !c)}
              title={panelCollapsed ? t('Genişlet') : t('Daralt')}
              aria-label={panelCollapsed ? t('Genişlet') : t('Daralt')}
            >{panelCollapsed ? '▸' : '▾'}</button>
          </div>
          {!panelCollapsed && (<>
          <div className="position-row"><span>{t('Tarih')}</span><b>{formatSignalTime(effDate)}</b></div>
          <div className="position-row">
            <span>{mode === 'live' ? t('Süre (canlı)') : t('Süre')}</span>
            <b>{formatDuration(closedDurationMs ?? ageMs)}</b>
          </div>
          <div className="position-row"><span>{t('Giriş')}</span><b>{formatPrice(activeSignal.entry)}</b></div>
          <div className="position-row">
             <span>{t('Hedef')}</span>
             <b><span style={{color:'#0ECB81'}}>{formatPrice(activeSignal.tp)}</span>
               {targetPct != null && <span style={{color:'#848E9C', fontWeight:400}}> · +{targetPct.toFixed(2)}%</span>}
             </b>
          </div>
          <div className="position-row">
             <span>{t('Stop')}</span>
             <b><span style={{color:'#F6465D'}}>{formatPrice(activeSignal.sl)}</span>
               {riskPct != null && <span style={{color:'#848E9C', fontWeight:400}}> · {riskPct.toFixed(2)}%</span>}
             </b>
          </div>
          {rr != null && (
            <div className="position-row">
              <span>{t('Risk-Reward')}</span>
              <b style={{ color: '#F5B942' }}>1:{rr.toFixed(2)}</b>
            </div>
          )}
          {mode === 'live' && Number.isFinite(liveLastPrice) && (
            <>
              <div className="position-row">
                <span>{t('Anlık Fiyat')}</span>
                <b>{formatPrice(liveLastPrice)}</b>
              </div>
              {distToEntry != null && (
                <div className="position-row">
                  <span>{t("Entry'ye Uzaklık")}</span>
                  <b style={{ color: Math.abs(distToEntry) < 0.5 ? '#F5B942' : '#EAECEF' }}>
                    {distToEntry >= 0 ? '+' : ''}{distToEntry.toFixed(2)}%
                  </b>
                </div>
              )}
            </>
          )}
          {mode === 'backtest' && Number.isFinite(exitPrice) && exitPrice !== activeSignal.entry && (
            <div className="position-row">
              <span>{t('Çıkış')}</span>
              <b>{formatPrice(exitPrice)}</b>
            </div>
          )}
          <div className="position-row">
            <span>{t('PnL')}</span>
            <b style={{color: activePnL === null || activePnL >= 0 ? '#0ECB81' : '#F6465D'}}>
              {activePnL !== null ? formatPnL(activeSignal, activePnL) : '--'}
            </b>
          </div>
          {mode === 'live' && (
            <div className="position-row">
              <span>{t('Canlı Durum')}</span>
              <b className={liveDisplay ? `status-text ${liveDisplay.cls}` : ''}>
                {liveDisplay && <span className={`status-dot ${liveDisplay.cls}`}>●</span>}
                {liveTradeStatus}
              </b>
            </div>
          )}

          {(activeSignal.strategy || activeSignal.quality || Number.isFinite(activeSignal.confluenceScore) || activeSignal.htfTimeframe) && (
            <div className="position-panel__intel">
              {Number.isFinite(activeSignal.confluenceScore) && (
                <div className="position-row"><span>{t('Konfluens')}</span><b style={{ color: '#F5B942' }}>{activeSignal.confluenceScore}</b></div>
              )}
              {activeSignal.quality && (
                <div className="position-row"><span>{t('Kalite')}</span><b>{activeSignal.quality}</b></div>
              )}
              {activeSignal.strategy && (
                <div className="position-row"><span>{t('Strateji')}</span><b>{activeSignal.strategy}</b></div>
              )}
              {(activeSignal.htfTimeframe || activeSignal.ltfTimeframe) && (
                <div className="position-row"><span>HTF / LTF</span><b>{activeSignal.htfTimeframe || '—'} / {activeSignal.ltfTimeframe || '—'}</b></div>
              )}
            </div>
          )}
          </>)}
        </div>
        );
      })()}

      {showTv && activeSignal && mode === 'live' && (
        <div className="position-panel horizontal bottom-left" style={{ backgroundColor: '#1e222d', borderRight: '1px solid #2a2e39' }}>
          <div className="position-row"><span>{t('Sembol')}</span><b>{activeSignal.symbol}</b></div>
          <div className="position-row">
            <span>{t('Yön')}</span>
            <b style={{ color: activeSignal.dir === 'LONG' ? '#0ECB81' : '#F6465D' }}>
              {activeSignal.dir}
            </b>
          </div>
          <div className="position-row"><span>{t('Sinyal')}</span><b>{formatSignalTime(effectiveSignalDate(activeSignal))}</b></div>
          <div className="position-row"><span>Entry</span><b>{formatPrice(activeSignal.entry)}</b></div>
          <div className="position-row">
            <span>TP / SL</span>
            <b><span style={{color:'#0ECB81'}}>{formatPrice(activeSignal.tp)}</span> / <span style={{color:'#F6465D'}}>{formatPrice(activeSignal.sl)}</span></b>
          </div>
        </div>
      )}

      {chartError && !showTv && <div className="chart-warning" style={{color:'#F6465D'}}>{chartError}</div>}
      {chartLoading && !showTv && <div className="chart-warning">{t('Veriler yükleniyor...')}</div>}

      <div
        ref={chartContainerRef}
        id="chart-container"
        className="journal-chart"
        style={{ width: '100%', height: '100%', minHeight: '520px', display: showTv ? 'none' : 'block', backgroundColor: '#0B0E11' }}
      ></div>

      {showTv && (
        <iframe className="tv-iframe" title="TradingView" src={getTvEmbedUrl()} frameBorder="0" allowTransparency="true" allow="fullscreen; clipboard-write" loading="lazy" />
      )}
    </div>
  );
};

export default ChartModal;
