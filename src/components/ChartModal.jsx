import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, LineSeries, BaselineSeries, createSeriesMarkers } from 'lightweight-charts';
import { useTradeContext, isHalfFor } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { scaleOutLiveR } from '../utils/liveR';
import { useSwipeDownClose } from '../utils/useSwipeDownClose';

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

// Session kline cache for STATIC chart datasets (backtest trades — their klines never change).
// Keyed by symbol|interval|start|end (minute-floored). Lets re-opening the same trade, the
// candle↔line toggle, and StrictMode double-mounts reuse data instead of re-hitting Binance.
// Live (active) trades skip this — their window grows every tick. Bounded LRU (~80 entries).
const CHART_KLINE_CACHE = new Map();
const KLINE_CACHE_MAX = 80;
const cacheGet = (k) => {
  if (!CHART_KLINE_CACHE.has(k)) return null;
  const v = CHART_KLINE_CACHE.get(k);            // refresh LRU order
  CHART_KLINE_CACHE.delete(k); CHART_KLINE_CACHE.set(k, v);
  return v;
};
const cacheSet = (k, v) => {
  CHART_KLINE_CACHE.set(k, v);
  if (CHART_KLINE_CACHE.size > KLINE_CACHE_MAX) CHART_KLINE_CACHE.delete(CHART_KLINE_CACHE.keys().next().value);
};

const ChartModal = () => {
  const { activeSignal, setActiveSignal, chartView, setChartView, mode, liveStatuses, strategy } = useTradeContext();
  const { t, locale } = useLang();
  // Mobile: swipe down on the header/handle to dismiss the chart sheet (inert on desktop).
  const { dragY, handlers: swipeHandlers } = useSwipeDownClose(() => setActiveSignal(null));
  // ½TP modules: the chart annotates the partial-TP + breakeven lifecycle —
  // TP/2 dashed line, "%50 kapandı, SL→Entry" marker, BE stop segment.
  // karma: ½TP'lik sembol bazında (KARMA_MAP) — isHalfFor iki durumu da çözer.
  const isHalf = isHalfFor(strategy, activeSignal?.symbol);
  // Scale-out stream (d30_4h_so): same 30m+4h entry + −1R stop as dch30_4h, but the exit
  // scales out — book 60% at +1R (first target), pull the runner's stop to breakeven; the runner
  // then exits at its +4R cap (== the signal's own TP), breakeven, or a 3-day time exit. The chart
  // surfaces the +1R partial level, the +4R runner cap, the breakeven runner segment, and how much
  // of the position is still open.
  // 30m+4h scale-out (d30_4h_so / d30so{N}c) AND 1h scale-out (d1h_so{N}c) — same exit geometry.
  const isScaleOut = !!strategy && (strategy.startsWith('d30_4h_so') || strategy.startsWith('d30so') || strategy.startsWith('d1h_so'));
  // Runner cap in R, by version: d30_4h_so(c)/4R, d30so6c/d1h_so6c = 6R, d30so8c/d1h_so8c = 8R, ...
  const soCapR = (() => {
    const m = strategy && strategy.match(/so(\d+)/);   // d30so8c / d30so8cm / d30so8f3 -> 8; d30_4h_soc -> 4
    return m ? Number(m[1]) : 4;
  })();
  // Booked fraction at TP1: the 'f3' variants book 30% (ride 70% on the runner); the rest book 60%.
  const soBookPct = (strategy && /f3/.test(strategy)) ? 30 : 60;
  const soRunPct = 100 - soBookPct;
  // Whole-trade time-stop in days (mark-to-market exit if neither cap/BE/SL): 'h7' variants = 7d, else 3d.
  const soHorizD = (strategy && /(h7|vg)/.test(strategy)) ? 7 : 3;   // 'vg' twin is h7-based
  // Realistic-entry twins (·0.5R, version *c): the entry IS the +0.5R confirmation level, so the
  // fill is a STOP — price must RISE (long) / FALL (short) TO the entry, not pull back to it.
  // Realistic-entry (·0.5R confirm) twins: a trailing 'c', OR the cm/f3 variants (all confirm-entry).
  // Without this, d30so8f3h7 (ends '7') was drawn with RAW breakout levels — wrong entry/TP1.
  const isConfirmEntry = !!strategy && (strategy.endsWith('c') || /(cm|f3)/.test(strategy));
  // MIDAS (trailing-stop, NO fixed TP/SL R:R): the exit is a 3.5×ATR trailing stop, not a planned
  // target. Render ENTRY + EXIT + the realised result only — no phantom green-TP / red-SL target
  // lines, no Hedef / Stop / Risk-Reward rows, no Sinyal marker. The zone spans entry→actual exit.
  const isTrailing = strategy === 'midas';

  // Use the CURRENT DB row for this trade (pnl_r / exit / status) rather than the possibly-stale
  // bulk-loaded backtest set — so a re-backfill is reflected the moment the chart opens, without a
  // full dashboard reload. Keyed on (version=strategy, symbol, direction, signal_time).
  const [dbFresh, setDbFresh] = useState(null);
  useEffect(() => {
    setDbFresh(null);
    if (mode !== 'backtest' || !activeSignal?.symbol || !activeSignal?.dateObj || !strategy) return undefined;
    const url = import.meta.env.BACKTESTING_VITE_SUPABASE_URL;
    const key = import.meta.env.BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
    if (!url || !key) return undefined;
    const raw = (import.meta.env.BACKTESTING_DB_TABLE || 'ict_trade.trading_signals').toString().trim().replace(/^["']|["']$/g, '');
    const [schema, table] = raw.includes('.') ? raw.split('.') : ['ict_trade', raw];
    let alive = true;
    const p = new URLSearchParams({ select: 'pnl_r,exit_price,exit_time,real_entry_time,status' });
    p.append('version', `eq.${strategy}`);
    p.append('symbol', `eq.${activeSignal.symbol}`);
    p.append('direction', `eq.${activeSignal.dir}`);
    p.append('signal_time', `eq.${activeSignal.dateObj.toISOString()}`);
    fetch(`${url}/rest/v1/${table}?${p.toString()}`, {
      headers: { apikey: key, Authorization: `Bearer ${key}`, 'Accept-Profile': schema },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((rows) => { if (alive && Array.isArray(rows) && rows[0]) setDbFresh(rows[0]); })
      .catch(() => { /* keep the loaded values on failure */ });
    return () => { alive = false; };
  }, [activeSignal?.symbol, activeSignal?.dir, activeSignal?.dateObj, mode, strategy]);

  // MIDAS LIVE: poll the live row's context every 15s so the trailing-stop line keeps GROWING on the
  // chart as canli (cron, every 1 min) ratchets it — without reopening the modal. Held in a ref so the
  // 3s render loop reads the freshest trail without re-subscribing.
  const liveTrailRef = useRef(null);
  useEffect(() => {
    liveTrailRef.current = null;
    if (mode !== 'live' || strategy !== 'midas' || !activeSignal?.id) return undefined;
    const url = import.meta.env.VITE_SUPABASE_URL;
    const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
    if (!url || !key) return undefined;
    let alive = true;
    const pull = () => {
      fetch(`${url}/rest/v1/signals?id=eq.${activeSignal.id}&select=context`, {
        headers: { apikey: key, Authorization: `Bearer ${key}`, 'Accept-Profile': 'ict_trade' },
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((rows) => {
          if (!alive || !Array.isArray(rows) || !rows[0]?.context) return;
          const tr = rows[0].context.trail;
          if (Array.isArray(tr) && tr.length) liveTrailRef.current = tr;
        })
        .catch(() => {});
    };
    pull();
    const id = setInterval(pull, 15000);
    return () => { alive = false; clearInterval(id); };
  }, [mode, strategy, activeSignal?.id]);

  // The signal the chart/panel actually renders: the loaded row with its outcome (pnl_r / exit /
  // status) overridden by the fresh DB read when available.
  const sig = (activeSignal && dbFresh) ? {
    ...activeSignal,
    pnlR: Number.isFinite(Number(dbFresh.pnl_r)) ? Number(dbFresh.pnl_r) : activeSignal.pnlR,
    exitPrice: Number.isFinite(Number(dbFresh.exit_price)) ? Number(dbFresh.exit_price) : activeSignal.exitPrice,
    exitTs: dbFresh.exit_time ? new Date(dbFresh.exit_time).getTime() : activeSignal.exitTs,
    entryFillTs: dbFresh.real_entry_time ? new Date(dbFresh.real_entry_time).getTime() : null,
    status: (() => {
      const s = (dbFresh.status || '').toLowerCase();
      return s.includes('cancel') ? 'NOFILL' : s.includes('tp') ? 'TP' : s.includes('sl') ? 'SL' : activeSignal.status;
    })(),
  } : activeSignal;

  // Realistic +0.5R entry / structural runner cap for confirm-entry (·0.5R) streams in LIVE — the
  // panel reads these so it matches the chart (which shifts entry to the +0.5R confirmation level).
  // Backtest rows already store the 0.5R entry + the real cap, so disp* == sig values there.
  const dispRawRisk = (sig && Number.isFinite(sig.entry) && Number.isFinite(sig.sl)) ? Math.abs(sig.entry - sig.sl) : null;
  const dispLiveConfirm = isConfirmEntry && mode === 'live' && !!dispRawRisk;
  const dispEntry = dispLiveConfirm ? (sig.dir === 'LONG' ? sig.entry + 0.5 * dispRawRisk : sig.entry - 0.5 * dispRawRisk) : sig?.entry;
  const dispTp = (dispLiveConfirm && isScaleOut)
    ? (sig.dir === 'LONG' ? sig.entry + soCapR * dispRawRisk : sig.entry - soCapR * dispRawRisk)
    : sig?.tp;
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
    'BE Oldu':                      { label: 'BE',       cls: 'st-tp' },      // ½TP: breakeven close
    'TP/SL Aynı Mum':               { label: 'TP+SL',    cls: 'st-mixed' },
    'İşlem Aktif (Entry Geldi)':    { label: 'AKTİF',    cls: 'st-active' },
    'İşlem Aktif (Kısmi ½TP Alındı)': { label: '½TP·BE',  cls: 'st-active' }, // ½TP: 50% banked, stop at entry
    'İşlem Aktif (+1R Alındı · Runner)': { label: 'AKTİF·+1R', cls: 'st-active' }, // scale-out: 60% booked, runner rides
    'İptal (Entry Gelmeden TP/SL)': { label: 'İPTAL',    cls: 'st-cancel' },
    'İptal (Süre Doldu)':           { label: 'İPTAL',    cls: 'st-cancel' },
    'İptal (Ters Yön)':             { label: 'İPTAL·YÖN', cls: 'st-cancel' }, // dir-confirm: opened toward SL -> skipped
    'Sinyal Bekliyor':              { label: 'BEKLİYOR', cls: 'st-wait' },
  };
  const ctxLiveStatus = (mode === 'live' && activeSignal) ? liveStatuses[activeSignal.id]?.status : null;
  const liveDisplay = LIVE_STATUS_DISPLAY[ctxLiveStatus] || (ctxLiveStatus ? null : null);
  const liveTradeStatus = liveDisplay ? liveDisplay.label : (mode === 'live' ? t('Hesaplanıyor...') : '');

  // Scale-out live R (mirror of Dashboard.liveOutcomeR for d30_4h_so): 60% booked at +1R, the
  // runner (40%) is risk-free at breakeven. A partial-active or BE close secures ~0.6−fee R
  // (a FLOOR — the runner can add more, resolved by the nightly sync); a pre-+1R stop is −1R.
  const soLiveR = (isScaleOut && mode === 'live' && activeSignal)
    ? scaleOutLiveR(activeSignal.entry, activeSignal.sl, ctxLiveStatus, soCapR, isConfirmEntry, soBookPct / 100)
    : null;
  // Floor (partial still riding) vs realised (BE/SL terminal).
  const soLiveRFloor = ctxLiveStatus === 'İşlem Aktif (+1R Alındı · Runner)';

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
        // All chart times are shown in UTC (the timeframe the signals/klines live in),
        // independent of the viewer's browser timezone.
        timeFormatter: (timestamp) => {
            const date = new Date(timestamp * 1000);
            return date.toLocaleString(locale, { timeZone: 'UTC', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) + ' UTC';
        }
      },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      width, height,
      rightPriceScale: { borderColor: '#2B3139', scaleMargins: { top: 0.2, bottom: 0.2 } },
      timeScale: {
        timeVisible: true, secondsVisible: false, borderColor: '#2B3139',
        tickMarkFormatter: (time, tickMarkType) => {
            const date = new Date(time * 1000);   // axis labels in UTC
            if (tickMarkType < 3) return date.toLocaleDateString(locale, { timeZone: 'UTC', day: 'numeric', month: 'short' });
            return date.toLocaleTimeString(locale, { timeZone: 'UTC', hour: '2-digit', minute: '2-digit' });
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
        baseValue: { type: 'price', price: dispEntry ?? activeSignal.entry },
        lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        priceFormat: { type: 'price', precision: 5, minMove: 0.00001 }
    });

    // SL Bölgesi (Kırmızı Alan için)
    const slAreaSeries = chart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: dispEntry ?? activeSignal.entry },
        lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        priceFormat: { type: 'price', precision: 5, minMove: 0.00001 }
    });

    // Scale-out RUNNER bölgesi (+1R → +4R cap): +1R partial alınınca YEŞİLE döner — böylece iki
    // hedef de tek bakışta okunur (önce +1R bandı, sonra gerçekleşince +4R runner bandı). baseline
    // = +1R; render bloğunda partial seviyesine göre güncellenir.
    const runnerZoneSeries = chart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: dispEntry ?? activeSignal.entry },
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
        const backtestExitTsMs = Number.isFinite(sig?.exitTs) ? sig.exitTs : fallbackBacktestEnd;
        const intervalMs = (tf) => {
          const m = String(tf || '1h').match(/^(\d+)([smhd])$/i);
          if (!m) return 60 * 60 * 1000;
          const units = { s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000 };
          return Number(m[1]) * units[m[2].toLowerCase()];
        };

        // --- Context window: PAD_BARS before the signal, POST_CLOSE_BARS after the close ---
        // Once a trade is resolved we fetch only ~30 more bars past the close and STOP — no
        // point streaming price action long after the outcome (and live polling halts too).
        const PAD_BARS = 6;            // context bars BEFORE the signal
        const POST_CLOSE_BARS = 30;    // context bars AFTER the close, then stop fetching
        const ltfMs = intervalMs(activeSignal.ltfTimeframe);
        const tradeSpanMs = Math.max(backtestExitTsMs - signalOpenMs, 60 * 1000);

        // Resolution: LIVE = 1m (intrabar precision while the trade is open). BACKTEST = coarser
        // by trade duration, starting at 5m — far fewer bars to fetch/parse/render than 1m, and
        // the outcome (entry/TP/SL/exit) is already known from the DB so 5m visuals suffice.
        const ladder = ['1m', '5m', '15m', '1h', '4h', '1d', '1w'];
        const pickInterval = () => {
          if (mode === 'live') return '1m';
          const hours = tradeSpanMs / 3600000;
          if (hours <= 60)   return '5m';    // <= 2.5 days
          if (hours <= 250)  return '15m';   // <= ~10 days
          if (hours <= 1000) return '1h';
          return '4h';
        };
        let klineInterval = pickInterval();
        let displayMs = intervalMs(klineInterval);

        // Window: PAD_BARS before signal; backtest ends POST_CLOSE_BARS past the exit, live = now.
        const computeWindow = () => {
          const start = signalOpenMs - Math.max(PAD_BARS * ltfMs, PAD_BARS * displayMs);
          const end = mode === 'live' ? Date.now()
            : Math.max(backtestExitTsMs + POST_CLOSE_BARS * displayMs, signalOpenMs + 60 * 1000);
          return { start, end };
        };
        let { start: fetchStartTime, end: fetchEndTime } = computeWindow();
        // Safety: keep the fetched span <= ~1450 bars (coarsen the interval if needed). Applies to
        // LIVE too: a trade older than ~24h exceeds 1450 1m bars, so it steps up to 5m/15m/… — this
        // keeps the SIGNAL bar in view (the entry/partial touch-scan + Sinyal/Giriş/TP1 markers need
        // it) instead of clamping the window start past the signal, which dropped every marker (and
        // the +4R runner band) on live trades older than ~24h.
        while ((fetchEndTime - fetchStartTime) / displayMs > 1450) {
          const i = ladder.indexOf(klineInterval);
          if (i < 0 || i === ladder.length - 1) break;
          klineInterval = ladder[i + 1]; displayMs = intervalMs(klineInterval);
          ({ start: fetchStartTime, end: fetchEndTime } = computeWindow());
        }
        const baseSymbol = normalizeForBinance(activeSignal.symbol);

        // 1. Veriyi Çek — backtest datasets are static, so cache them (re-open / style toggle /
        //    StrictMode reuse without a refetch). Live is never cached (its window grows live).
        const cacheable = mode === 'backtest';
        const cacheKey = `${baseSymbol}|${klineInterval}|${Math.floor(fetchStartTime / 60000)}|${Math.floor(fetchEndTime / 60000)}`;
        let rawData = cacheable ? cacheGet(cacheKey) : null;
        if (!Array.isArray(rawData)) {
          const urlFutures = `https://fapi.binance.com/fapi/v1/klines?symbol=${baseSymbol}&interval=${klineInterval}&startTime=${Math.floor(fetchStartTime)}&endTime=${Math.floor(fetchEndTime)}&limit=1500`;
          const res = await fetch(urlFutures);
          rawData = await res.json();
          // Futures yoksa Spot dene
          if (!Array.isArray(rawData)) {
            const urlSpot = `https://api.binance.com/api/v3/klines?symbol=${baseSymbol}&interval=${klineInterval}&startTime=${Math.floor(fetchStartTime)}&endTime=${Math.floor(fetchEndTime)}&limit=1500`;
            const resSpot = await fetch(urlSpot);
            rawData = await resSpot.json();
          }
          if (cacheable && Array.isArray(rawData) && rawData.length) cacheSet(cacheKey, rawData);
        }

        if (cancelled || !chartRef.current) return;   // modal closed / re-opened while fetching

        if (!Array.isArray(rawData) || rawData.length === 0) throw new Error('Kline verisi boş');

        let candles = rawData.map(d => ({
          time: d[0] / 1000,
          open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
        }));

        const { entry: sigEntry, tp: sigTp, sl, dir } = activeSignal;
        const isLong = dir === 'LONG';
        // LIVE confirm-entry (·0.5R) streams read the RAW dch30_4h signal (entry = breakout close);
        // the backtest DB already stores the realistic +0.5R entry. Mirror it live: shift the entry
        // to the +0.5R confirmation level and (scale-out) put the runner cap at its STRUCTURAL
        // +{soCapR}R from the breakout. risk / partialLevel(TP1) / BE / the fill-scan all derive
        // from `entry` and `tp`, so they follow automatically. (Backtest: entry/tp already correct.)
        const sigRisk = (sigEntry != null && sl != null) ? Math.abs(sigEntry - sl) : null;
        const liveConfirm = isConfirmEntry && mode === 'live' && !!sigRisk;
        const entry = liveConfirm ? (isLong ? sigEntry + 0.5 * sigRisk : sigEntry - 0.5 * sigRisk) : sigEntry;
        const tp = (liveConfirm && isScaleOut)
          ? (isLong ? sigEntry + soCapR * sigRisk : sigEntry - soCapR * sigRisk)
          : sigTp;
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
        // ½TP modules additionally track the partial scale-out: at TP/2 the position
        // halves and the stop moves to entry (BE) — so the close after a partial is
        // detected against ENTRY, not the original SL (mirror of _resolve_partial).
        // Partial-take level: ½TP books 50% at HALF the distance to TP1; scale-out books 60%
        // at +1R (= one risk unit from entry). After the partial the stop moves to breakeven and
        // the remainder rides — ½TP toward the original TP1, scale-out's runner to its +4R cap
        // (== signal TP) / breakeven / a 3-day time exit. The runner geometry is what the chart surfaces.
        const risk = (entry != null && sl != null) ? Math.abs(entry - sl) : null;
        const partialLevel = isScaleOut && risk
          ? (isLong ? entry + risk : entry - risk)
          : (isHalf && entry && tp ? entry + (tp - entry) / 2 : null);
        const isPartial = isHalf || isScaleOut;
        let entryFilled = false, entryFillSec = null, closeBarSec = null, closeBarIdx = -1;
        let partialBarSec = null, beClose = false;

        if (isScaleOut && entry && sl && partialLevel != null && signalVisible) {
          // scale-out: entry fill -> +1R partial (60%, SL→BE) -> runner exits at its +4R cap
          // (== signal TP), breakeven, or a 3-day time exit. If none lands in-window it falls
          // through to the DB exit anchor, shown as a neutral "Çıkış".
          let hit = false, partial = false, stop = sl;
          for (let idx = 0; idx < candles.length; idx++) {
            const c = candles[idx];
            if (c.time < entryTs) continue;
            const soHit = isLong ? c.high >= partialLevel : c.low <= partialLevel;
            const stopHit = isLong ? c.low <= stop : c.high >= stop;
            if (!hit) {
              const eHit = isConfirmEntry
                ? (isLong ? c.high >= entry : c.low <= entry)   // ·0.5R: STOP entry at the confirm level
                : (isLong ? c.low <= entry : c.high >= entry);
              if (!eHit && stopHit) { closeBarSec = c.time; closeBarIdx = idx; break; }   // pre-entry cancel
              if (eHit) {
                hit = true; entryFilled = true; entryFillSec = c.time;
                if (stopHit && !soHit) { closeBarSec = c.time; closeBarIdx = idx; break; } // immediate -1R
                if (soHit) { partial = true; partialBarSec = c.time; stop = entry; }       // +1R, arm BE
              }
            } else if (!partial) {
              if (stopHit) { closeBarSec = c.time; closeBarIdx = idx; break; }            // -1R before +1R
              if (soHit) { partial = true; partialBarSec = c.time; stop = entry; }         // +1R, arm BE
            } else {                                                                       // runner riding
              const capHit = isLong ? c.high >= tp : c.low <= tp;                           // +4R cap (== signal TP)
              if (stopHit) { beClose = true; closeBarSec = c.time; closeBarIdx = idx; break; }  // runner back to BE (0R)
              if (capHit) { closeBarSec = c.time; closeBarIdx = idx; break; }                    // runner +4R cap (win)
            }
          }
        } else if (entry && tp && sl && signalVisible && !isTrailing) {
          const halfLevel = partialLevel;   // ½TP partial (null for the base full-TP stream)
          let hit = false, partial = false, stop = sl;
          for (let idx = 0; idx < candles.length; idx++) {
            const c = candles[idx];
            if (c.time < entryTs) continue;
            const tpHit = isLong ? c.high >= tp : c.low <= tp;
            const stopHit = isLong ? c.low <= stop : c.high >= stop;
            if (!hit) {
              // ·0.5R twins: STOP entry at the +0.5R confirm level (price reaches it from below/above);
              // otherwise the legacy limit/market fill at the breakout close.
              const eHit = isConfirmEntry
                ? (isLong ? c.high >= entry : c.low <= entry)
                : (isLong ? c.low <= entry : c.high >= entry);
              if (!eHit && (tpHit || stopHit)) { closeBarSec = c.time; closeBarIdx = idx; break; } // pre-entry iptal
              if (eHit) {
                hit = true; entryFilled = true; entryFillSec = c.time;
                if (tpHit || stopHit) { closeBarSec = c.time; closeBarIdx = idx; break; }
                if (halfLevel != null) {
                  const hHit = isLong ? c.high >= halfLevel : c.low <= halfLevel;
                  if (hHit) { partial = true; partialBarSec = c.time; stop = entry; } // BE from next bar
                }
              }
            } else if (halfLevel != null && !partial) {
              if (stopHit) { closeBarSec = c.time; closeBarIdx = idx; break; }        // SL first (worst case)
              if (tpHit) { partialBarSec = c.time; closeBarSec = c.time; closeBarIdx = idx; break; } // gap through ½+TP
              const hHit = isLong ? c.high >= halfLevel : c.low <= halfLevel;
              if (hHit) { partial = true; partialBarSec = c.time; stop = entry; }     // scale out, arm BE
            } else if (tpHit || stopHit) {
              if (partial && stopHit && !tpHit) beClose = true;                       // BE stop hit
              closeBarSec = c.time; closeBarIdx = idx; break;
            }
          }
        }
        // Partial backtest rows whose coarse re-fetch missed the BE touch — recover BE from the
        // DB exit price parked at entry (½TP and the scale-out runner both close BE at entry).
        if (isPartial && !beClose && mode === 'backtest' && sig.status === 'TP'
            && Number.isFinite(sig.exitPrice) && entry
            && Math.abs(sig.exitPrice - entry) / entry < 1e-6) {
          beClose = true;
        }

        // Fallback: a closed backtest trade whose coarse re-fetch missed the exact touch —
        // anchor the close to the DB exit_time so zone/trim/dimming/marker all agree.
        const backtestClosed = mode === 'backtest' && (sig.status === 'TP' || sig.status === 'SL');
        if (backtestClosed && Number.isFinite(sig.exitTs)) {
          closeBarSec = snapBar(sig.exitTs);   // anchor the exit to the DB (1m-resolved), not the coarse-candle scan
          closeBarIdx = candles.findIndex(c => c.time === closeBarSec);
        }
        // Anchor the ENTRY marker to the DB real_entry_time too (backtest) — visualize the DB's
        // entry/exit timestamps, don't re-derive the fill from coarse candles.
        if (mode === 'backtest' && Number.isFinite(sig.entryFillTs)) {
          entryFilled = true;
          entryFillSec = snapBar(sig.entryFillTs);
        }
        // MIDAS LIVE (trailing): no nominal-tp/sl scan ran — the entry fills at the signal bar and the
        // position stays OPEN (closeBarSec=null -> nothing ghosted, candles keep their green/red). Only
        // when canli marks it closed (context.pos) do we anchor the close at the last trailing-stop point.
        if (mode === 'live' && isTrailing) {
          entryFilled = true;
          // snapBar expects MS: entryTs is already SECONDS (line ~438) and the trail timestamps are
          // UNIX SECONDS — pass ms so we don't divide a seconds value by 1000 (which snaps every
          // target back to candles[0], collapsing entry+exit onto the first bar).
          entryFillSec = entryFillSec ?? snapBar(signalOpenMs + ltfMs);
          if (activeSignal?.context?.pos === 'closed'
              && Array.isArray(activeSignal.trail) && activeSignal.trail.length) {
            closeBarSec = snapBar(activeSignal.trail[activeSignal.trail.length - 1][0] * 1000);
            closeBarIdx = candles.findIndex((c) => c.time === closeBarSec);
          }
        }

        // Live terminal state — computed early so the close anchor + trim can use it.
        const ctxStatus = liveStatuses[activeSignal.id]?.status;
        const liveTerminalSet = new Set(['TP Oldu', 'SL Oldu', 'BE Oldu', 'TP/SL Aynı Mum']);
        const liveTerminal = !!ctxStatus && (liveTerminalSet.has(ctxStatus) || ctxStatus.startsWith('İptal'));
        const isTerminalState = mode === 'backtest'
          ? (sig.status === 'TP' || sig.status === 'SL')
          : liveTerminal;

        // CANCELLED live signal (directional confirm failed = 'İptal (Ters Yön)', or fill timed
        // out = 'İptal (Süre Doldu)'): the trade was NEVER taken. The touch-scan above ignores the
        // confirm gate, so it would draw a PHANTOM Giriş/TP1/Çıkış on a trade that didn't open.
        // Suppress those + the zones, and anchor the close at the cancel point (the adverse-0.5R
        // touch that vetoed it, else the fill deadline).
        const isCancelled = mode === 'live' && !!ctxStatus && ctxStatus.startsWith('İptal');
        if (isCancelled) {
          entryFilled = false; entryFillSec = null; partialBarSec = null; beClose = false;
          // Adverse-0.5R veto level is measured from the SIGNAL (breakout close) + its raw risk —
          // NOT the +0.5R-shifted entry — so the confirm gate mirrors the backtest exactly.
          const risk0 = Number.isFinite(sigRisk) ? sigRisk : 0;
          const advLvl = isLong ? sigEntry - 0.5 * risk0 : sigEntry + 0.5 * risk0;   // mirror ENTRY_CONFIRM_BUF=0.5
          let cb = null;
          if (risk0 > 0) {
            for (const c of candles) {
              if (c.time < entryTs) continue;
              if (isLong ? c.low <= advLvl : c.high >= advLvl) { cb = c.time; break; }
            }
          }
          closeBarSec = cb != null ? cb : snapBar(signalOpenMs + ENTRY_EXPIRY_MINUTES * 60 * 1000);
          closeBarIdx = candles.findIndex(c => c.time === closeBarSec);
        }

        // Live entry-fill timeout ('İptal (Süre Doldu)'): never filled, no TP/SL touch.
        // The trade ends at the fill deadline — anchor the close there so the zone,
        // dimming and exit marker all stop at the timeout, not at the latest candle.
        if (closeBarSec == null && mode === 'live' && ctxStatus === 'İptal (Süre Doldu)') {
          closeBarSec = snapBar(signalOpenMs + ENTRY_EXPIRY_MINUTES * 60 * 1000);
          closeBarIdx = candles.findIndex(c => c.time === closeBarSec);
        }

        // Once the trade is resolved, keep POST_CLOSE_BARS (~30) of context past the close, then
        // stop — for backtest AND any terminal live trade. No price action is streamed long
        // after the outcome; the live 3s poll is also halted below once terminal.
        if (closeBarIdx >= 0 && (mode === 'backtest' || liveTerminal)) {
          candles = candles.slice(0, Math.min(candles.length, closeBarIdx + 1 + POST_CLOSE_BARS));
        }

        // The signal fires at the bar CLOSE (signal_time = bar OPEN). Anchor the
        // "Sinyal" marker + pre-signal dimming at the close so the chart shows the
        // real moment the signal formed — matching the panel's "Tarih".
        const signalSec = snapBar(signalOpenMs + ltfMs);

        // --- Per-bar dimming: pre-signal context tinted violet, post-trade ghosted gray ---
        // CANCELLED live trade: tint the signal→cancel span AMBER (the attempted-but-vetoed
        // window) so it reads distinctly from the violet pre-signal / gray post-close context.
        candles = candles.map((c) => {
          if (c.time < signalSec) return { ...c, color: '#322B45', wickColor: '#7C6BB0', borderColor: '#473A66' };
          if (closeBarSec != null && c.time > closeBarSec) return { ...c, color: '#2B3139', wickColor: '#5E6673', borderColor: '#2B3139' };
          if (isCancelled && closeBarSec != null) return { ...c, color: '#3D331C', wickColor: '#C99A3E', borderColor: '#5C4B28' };
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
        if (entry && tp && sl && !isCancelled) {
          // Guard the zone span: lightweight-charts setData requires strictly-ascending
          // unique times. For a freshly-emitted signal the entry-bar close (entryTs) can
          // equal or exceed the latest loaded 1m candle (endTimeForGraph) — most often on
          // the 30m stream, whose :00/:30 closes land exactly on 1m boundaries. Two equal
          // (or descending) points would throw → "Veri alınamadı". Fall back to a single
          // point until the candle window advances past the entry bar (next 3s refresh).
          // Green zone spans entry → target. Scale-out's real first target is +1R (the booked
          // 60% band), NOT the 4R tp — so cap the zone at +1R there to read honestly.
          // The trade visualisation (zones) begins at the ENTRY FILL, not the signal bar — for the
          // ·0.5R streams the position opens only once price reaches the +0.5R confirmation level.
          const tradeStartSec = (entryFilled && entryFillSec != null) ? entryFillSec : entryTs;
          // MIDAS (trailing): the zone spans entry → the ACTUAL exit (closed) or → the CURRENT
          // trailing-stop level (live open = the locked-in zone). Everyone else: entry → tp / +1R band.
          const trailLast = (Array.isArray(activeSignal.trail) && activeSignal.trail.length)
            ? activeSignal.trail[activeSignal.trail.length - 1][1] : null;
          const lastClose = candles.length ? candles[candles.length - 1].close : null;
          const zoneTop = isTrailing
            ? (Number.isFinite(sig.exitPrice) ? sig.exitPrice                 // closed -> realised exit
               : (mode === 'live' && Number.isFinite(lastClose)) ? lastClose  // live open -> current price (grows)
               : (Number.isFinite(trailLast) ? trailLast : tp))
            : (isScaleOut && partialLevel != null) ? partialLevel : tp;
          tpAreaSeries.setData(endTimeForGraph > tradeStartSec
            ? [ { time: tradeStartSec, value: zoneTop }, { time: endTimeForGraph, value: zoneTop } ]
            : [ { time: tradeStartSec, value: zoneTop } ]);
          // The original SL dies at the partial (stop → entry) for BOTH partial models — end its
          // zone there so the chart reads "risk removed from this bar on". MIDAS has no fixed-SL
          // zone (the stop trails) — draw none.
          const slZoneEnd = (isPartial && partialBarSec != null) ? Math.min(partialBarSec, endTimeForGraph) : endTimeForGraph;
          if (isTrailing) {
            slAreaSeries.setData([]);
          } else {
            slAreaSeries.setData(slZoneEnd > tradeStartSec
              ? [ { time: tradeStartSec, value: sl }, { time: slZoneEnd, value: sl } ]
              : [ { time: tradeStartSec, value: sl } ]);
          }
        } else {
          tpAreaSeries.setData([]);
          slAreaSeries.setData([]);
        }

        // Scale-out RUNNER band (+1R → +4R cap): turns GREEN from the bar the +1R partial fired
        // (both live & backtest), showing the open runner's profit zone up to its cap. Before the
        // partial it's empty — so the chart reads "first +1R, then the +4R part goes green".
        if (isScaleOut && partialLevel != null && tp && partialBarSec != null) {
          runnerZoneSeries.applyOptions(isLong ? {
            baseValue: { type: 'price', price: partialLevel },
            topLineColor: '#0ECB81', topFillColor1: 'rgba(14, 203, 129, 0.22)', topFillColor2: 'rgba(14, 203, 129, 0.05)',
            bottomLineColor: 'transparent', bottomFillColor1: 'transparent', bottomFillColor2: 'transparent'
          } : {
            baseValue: { type: 'price', price: partialLevel },
            bottomLineColor: '#0ECB81', bottomFillColor1: 'rgba(14, 203, 129, 0.22)', bottomFillColor2: 'rgba(14, 203, 129, 0.05)',
            topLineColor: 'transparent', topFillColor1: 'transparent', topFillColor2: 'transparent'
          });
          runnerZoneSeries.setData(endTimeForGraph > partialBarSec
            ? [ { time: partialBarSec, value: tp }, { time: endTimeForGraph, value: tp } ]
            : [ { time: partialBarSec, value: tp } ]);
        } else {
          runnerZoneSeries.setData([]);
        }

        // ½TP: breakeven stop segment — a yellow dashed line AT entry from the partial
        // bar to the close, marking the new risk-free stop. Created once, refreshed
        // every pass (live refresh re-runs this block every 3s).
        if (isPartial && !chartRef.current._beSeries) {
          chartRef.current._beSeries = chart.addSeries(LineSeries, {
            color: '#F0B90B', lineWidth: 2, lineStyle: 2,
            lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
            priceFormat: { type: 'price', precision: 5, minMove: 0.00001 }
          });
        }
        if (chartRef.current._beSeries) {
          chartRef.current._beSeries.setData(
            (partialBarSec != null && entry && endTimeForGraph > partialBarSec)
              ? [ { time: partialBarSec, value: entry }, { time: endTimeForGraph, value: entry } ]
              : (partialBarSec != null && entry ? [ { time: partialBarSec, value: entry } ] : [])
          );
        }

        // 4. Referans çizgileri (tek sefer) — eksen etiketine fiyat/yüzde
        if (!chartRef.current._priceLinesAdded) {
          const targetPct = entry && tp ? ((tp - entry) / entry) * 100 : null;
          const riskPct = entry && sl ? ((sl - entry) / entry) * 100 : null;
          if (entry) mainSeries.createPriceLine({ price: entry, color: '#848E9C', lineWidth: 1, lineStyle: 0, title: `${t('Giriş')}${isConfirmEntry ? ' ·0.5R' : ''} ${formatPrice(entry)}`, axisLabelVisible: true });
          // LIVE confirm-entry: the realistic entry sits +0.5R above the breakout, so mark the
          // SIGNAL (breakout) level too — they coincide in backtest (entry already == 0.5R level).
          if (liveConfirm && Number.isFinite(sigEntry) && Math.abs(sigEntry - entry) > 1e-9) {
            mainSeries.createPriceLine({ price: sigEntry, color: '#5E6673', lineWidth: 1, lineStyle: 3, title: `${t('Sinyal')} ${formatPrice(sigEntry)}`, axisLabelVisible: true });
          }
          // 4R line: for scale-out it is the RUNNER CAP (runner takes profit at +4R == the
          // signal's own TP); for every other stream it is the full take-profit. Drawn for both.
          // The green TP / green ½TP / red SL lines are TRADE levels — drawn only for a trade that
          // was actually taken. A CANCELLED signal (directional veto / timeout) never opened, so
          // suppress them (no phantom green/red); only the entry/signal + the -0.5R veto show.
          if (tp && !isCancelled && !isTrailing) mainSeries.createPriceLine({ price: tp, color: '#0ECB81', lineWidth: 1, lineStyle: 2, title: `${isScaleOut ? t('Runner Cap +{cap}R', { cap: soCapR }) : t('TP')}${targetPct != null ? ' +' + Math.abs(targetPct).toFixed(1) + '%' : ''}`, axisLabelVisible: true });
          // Partial-take line (dashed): ½TP closes 50% here (SL→entry); scale-out closes 60% at
          // +1R and the runner then rides with a breakeven stop.
          if (partialLevel != null && !isCancelled && !isTrailing) {
            const partialPct = entry ? ((partialLevel - entry) / entry) * 100 : null;
            const partialTitle = isScaleOut ? `TP1 +1R · %${soBookPct}` : '½TP %50';
            mainSeries.createPriceLine({ price: partialLevel, color: '#0ECB81', lineWidth: 1, lineStyle: 2, title: `${partialTitle}${partialPct != null ? ' +' + Math.abs(partialPct).toFixed(1) + '%' : ''}`, axisLabelVisible: true });
          }
          if (sl && !isCancelled && !isTrailing) mainSeries.createPriceLine({ price: sl, color: '#F6465D', lineWidth: 1, lineStyle: 2, title: `${t('SL')}${riskPct != null ? ' -' + Math.abs(riskPct).toFixed(1) + '%' : ''}`, axisLabelVisible: true });
          // MIDAS: the FIXED initial stop = 1R risk, set at entry, NEVER changes (dashed). The
          // variable trailing stop is drawn as a stepped LINE below (its path to the exit).
          if (sl && !isCancelled && isTrailing) mainSeries.createPriceLine({ price: sl, color: '#F6465D', lineWidth: 1, lineStyle: 3, title: `${t('SL')} (1R) ${formatPrice(sl)}`, axisLabelVisible: true });
          // Adverse-0.5R confirmation level (SL side): the directional gate (ENTRY_CONFIRM_BUF=0.5)
          // line. Drawn on EVERY live signal — for 'İptal (Ters Yön)' it marks WHERE the breakout
          // went adverse first and got vetoed; for trades that DID open (SL/TP/active) it shows the
          // threshold the breakout confirmed PAST. Measured from the SIGNAL (breakout close) + raw
          // risk, mirroring the backtest gate. (mode-keyed, not status-keyed, so it draws on the
          // first render before the live status has polled.)
          // MIDAS has no +0.5R directional-confirm gate (not a confirm-entry stream) -> no adverse line.
          if (mode === 'live' && !isTrailing && Number.isFinite(sigRisk) && sigRisk > 0) {
            const advLvl = isLong ? sigEntry - 0.5 * sigRisk : sigEntry + 0.5 * sigRisk;
            mainSeries.createPriceLine({ price: advLvl, color: '#F0B90B', lineWidth: 1, lineStyle: 2, title: `${t('Ters Onay')} −0.5R`, axisLabelVisible: true });
          }
          if (mode === 'backtest' && activeSignal?.exitPrice) {
            mainSeries.createPriceLine({ price: sig.exitPrice, color: '#F0B90B', lineWidth: 1, lineStyle: 1, title: `${t('Çıkış')} ${formatPrice(sig.exitPrice)}`, axisLabelVisible: true });
          }
          chartRef.current._priceLinesAdded = true;
        }

        // 4a. MIDAS — TRAILING-STOP PATH (the VARIABLE "TP"): a stepped line that starts at the
        // fixed initial SL and ratchets toward price (down for a short, up for a long), ending where
        // it got hit (= the exit). Visualises that the stop is dynamic while the 1R risk is fixed.
        // LIVE: prefer the freshly-polled trail (liveTrailRef, updated every 15s) so the line GROWS
        // as canli ratchets the stop each minute; backtest uses the loaded row's trail.
        const trailSrc = (mode === 'live' && Array.isArray(liveTrailRef.current) && liveTrailRef.current.length > 1)
          ? liveTrailRef.current : activeSignal.trail;
        if (isTrailing && Array.isArray(trailSrc) && trailSrc.length > 1) {
          if (!chartRef.current._trailSeries) {
            chartRef.current._trailSeries = chart.addSeries(LineSeries, {
              color: '#F0B90B', lineWidth: 2, lineStyle: 0, lineType: 1,   // lineType 1 = stepped
              lastValueVisible: true, priceLineVisible: false, crosshairMarkerVisible: false,
              title: t('İz Süren Stop'),
              priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
            });
          }
          const seen = new Set();
          const trailData = trailSrc
            .map((pt) => ({ time: Math.floor(Number(pt[0])), value: Number(pt[1]) }))
            .filter((p) => Number.isFinite(p.time) && Number.isFinite(p.value))
            .sort((a, b) => a.time - b.time)
            .filter((p) => (seen.has(p.time) ? false : (seen.add(p.time), true)));
          // LIVE open: extend the stop FLAT to the current bar so the line reaches the right edge (it
          // only changes on new highs/lows; between canli updates it holds its level — not "behind").
          const lastBar = candles.length ? candles[candles.length - 1] : null;
          if (!Number.isFinite(sig.exitPrice) && trailData.length && lastBar
              && lastBar.time > trailData[trailData.length - 1].time) {
            trailData.push({ time: lastBar.time, value: trailData[trailData.length - 1].value });
          }
          if (trailData.length > 1) chartRef.current._trailSeries.setData(trailData);
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

        // 5. Zaman-bağlı işaretler: Sinyal / Giriş / ½TP Kısmi / Çıkış (renk sonuca göre).
        // ½TP'de BE kapanışı ayrı etiketlenir (sarı 'BE') — TP/SL ile karışmasın.
        const isBE = isPartial && (beClose || (mode === 'live' && ctxStatus === 'BE Oldu'));
        const isTP = !isBE && ((mode === 'backtest' && sig.status === 'TP') || (mode === 'live' && ctxStatus === 'TP Oldu'));
        const isSL = (mode === 'backtest' && sig.status === 'SL') || (mode === 'live' && (ctxStatus === 'SL Oldu' || ctxStatus === 'TP/SL Aynı Mum'));
        const exitColor = isCancelled ? '#848E9C' : isTP ? '#0ECB81' : isSL ? '#F6465D' : '#F0B90B';
        // Scale-out has NO single "TP": the runner exits at its +4R cap, breakeven, or a
        // mark (3-day / data-edge). Label the exit marker accordingly so it isn't a misleading
        // "TP" (the real +1R take-profit is the separate partial marker). A cancelled signal
        // gets a neutral "İptal" marker (no trade was taken).
        const soRunnerCap = isScaleOut && isTP && (mode === 'live'
          ? true   // live 'TP Oldu' == runner reached its +4R cap
          : (Number.isFinite(sig.exitPrice) && sig.tp
             && Math.abs(sig.exitPrice - sig.tp) / sig.tp < 1e-4));
        const exitText = isCancelled ? t('İptal')
          : isTrailing ? t('Çıkış')   // trailing exit — not a fixed TP/SL
          : (isScaleOut && isTP) ? (soRunnerCap ? t('Runner +{cap}R', { cap: soCapR }) : t('Mark'))
          : (isTP ? t('TP') : isSL ? t('SL') : isBE ? 'BE' : t('Çıkış'));
        const exitSec = closeBarSec != null ? closeBarSec : (Number.isFinite(sig.exitTs) ? snapBar(sig.exitTs) : null);

        const markers = [];
        if (signalVisible && !isTrailing) markers.push({ time: signalSec, position: 'aboveBar', shape: 'circle', color: '#F0B90B', text: t('Sinyal'), size: 1 });
        // Entry-fill marker — shown whenever the entry fills, INCLUDING on the signal bar itself
        // (breakouts enter at the bar close, so entryFillSec usually == signalSec). Sinyal is an
        // aboveBar circle and Giriş is a belowBar arrow (long), so they don't collide on one bar.
        if (entryFilled && entryFillSec != null) {
          markers.push({ time: entryFillSec, position: isLong ? 'belowBar' : 'aboveBar', shape: isLong ? 'arrowUp' : 'arrowDown', color: '#F5B942', text: isConfirmEntry ? `${t('Giriş')} ·0.5R` : t('Giriş'), size: 1 });
        }
        // Kısmi kâr işareti: ½TP'de fiyat TP/2'ye değdi (%50 kapandı); scale-out'ta +1R'ye
        // değdi (%60 kapandı). Her ikisinde de SL → Entry (breakeven).
        if (isPartial && partialBarSec != null && (partialBarSec !== exitSec || !isTerminalState)) {
          const partialText = isScaleOut ? `TP1 +1R · %${soBookPct} → BE` : '½TP %50 · SL→BE';
          markers.push({ time: partialBarSec, position: isLong ? 'aboveBar' : 'belowBar', shape: 'circle', color: '#F5B942', text: partialText, size: 1 });
        }
        if (isTerminalState && exitSec != null) {
          markers.push({ time: exitSec, position: isLong ? 'aboveBar' : 'belowBar',
            shape: isCancelled ? 'circle' : (isLong ? 'arrowDown' : 'arrowUp'),
            color: exitColor, text: exitText, size: 1 });
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
            toTime = Math.min(toTime, closeBarSec + POST_CLOSE_BARS * (displayMs / 1000));
          }
          // LIVE: start the view AT the signal (no pre-signal context) — the live chart opens
          // from the moment the signal fired. BACKTEST keeps the pre-signal run-up (violet) for
          // context. Guard from < to (a freshly-fired signal can sit at the latest bar).
          // MIDAS (isTrailing): keep the pre-entry context (like backtest) so the run-up into the
          // VWAP-pullback entry is visible; other live streams open AT the signal.
          const liveFrom = Math.max(candles[0].time, signalSec);
          const fromTime = (mode === 'live' && !isTrailing && liveFrom < toTime) ? liveFrom : candles[0].time;
          try {
            tsApi.setVisibleRange({ from: fromTime, to: toTime });
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
  }, [activeSignal, dbFresh, showTv, mode, chartStyle, isHalf, isScaleOut]);

  // UI Formatters
  // Signal/hover times in UTC (the data's native zone), labelled so it's unambiguous
  // regardless of the viewer's browser timezone.
  const formatSignalTime = (dateObj) => dateObj ? dateObj.toLocaleString(locale, { timeZone: 'UTC', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + ' UTC' : '--';
  const formatHoverTime = (ts) => ts ? new Date(ts * 1000).toLocaleString(locale, { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) + ' UTC' : '--';
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
  const activePnL = calculatePnL(sig);

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

  // Pre-trade analytics: RR, target%, risk%, duration, current-price distance.
  // RR uses the DISPLAYED entry/tp — in LIVE the realistic +0.5R entry; SL & TP stay at the signal
  // levels — so the ratio reflects the collapse (entry moves toward TP, away from SL: 4 → ~2.33).
  const computeRR = () => {
    if (!Number.isFinite(dispEntry) || !sig?.sl || !Number.isFinite(dispTp)) return null;
    const risk = Math.abs(dispEntry - sig.sl);
    const reward = Math.abs(dispTp - dispEntry);
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
    <div
      id="modal"
      style={{
        display: 'block', backgroundColor: '#0B0E11', color: '#EAECEF',
        transform: dragY ? `translateY(${dragY}px)` : undefined,
        transition: dragY ? 'none' : 'transform 0.22s cubic-bezier(0.22, 0.61, 0.36, 1)',
      }}
    >
      <div id="chart-header" {...swipeHandlers} style={{ borderBottom: '1px solid #2a2e39', padding: '10px', paddingRight: '104px' }}>
        <div className="sheet-handle" aria-hidden="true" />
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
          {/* TradingView-style OHLC legend: inline next to the symbol (NOT pushed right under the
              close button, where it used to get clipped), values tinted by the hovered bar's direction. */}
          {!showTv && hoverInfo && (() => {
            const up = hoverInfo.open === undefined || hoverInfo.close >= hoverInfo.open;
            const vc = up ? '#0ECB81' : '#F6465D';
            return (
              <div className="chart-hover-info">
                <span className="ohlc-time">{formatHoverTime(hoverInfo.time)}</span>
                {hoverInfo.open !== undefined ? (
                  <>
                    <span className="ohlc-pair"><i>O</i><b style={{ color: vc }}>{formatPrice(hoverInfo.open)}</b></span>
                    <span className="ohlc-pair"><i>H</i><b style={{ color: vc }}>{formatPrice(hoverInfo.high)}</b></span>
                    <span className="ohlc-pair"><i>L</i><b style={{ color: vc }}>{formatPrice(hoverInfo.low)}</b></span>
                    <span className="ohlc-pair"><i>C</i><b style={{ color: vc }}>{formatPrice(hoverInfo.close)}</b></span>
                  </>
                ) : (
                  <span className="ohlc-pair"><i>C</i><b style={{ color: vc }}>{formatPrice(hoverInfo.close)}</b></span>
                )}
              </div>
            );
          })()}
        </div>
      </div>

      <button id="close-modal" className="close-modern" onClick={() => setActiveSignal(null)}>
        <span className="close-label">{t('Kapat')}</span>
      </button>

      {!showTv && activeSignal && (() => {
        const rr = computeRR();
        const targetPct = pctDist(dispEntry, dispTp);
        const riskPct = pctDist(dispEntry, activeSignal.sl);
        const liveLastPrice = mode === 'live' ? liveStatuses[activeSignal.id]?.lastPrice : null;
        const distToEntry = mode === 'live' ? pctDist(liveLastPrice, dispEntry) : null;
        const effDate = effectiveSignalDate(activeSignal);
        const ageMs = effDate ? (Date.now() - effDate.getTime()) : null;
        // MIDAS live CLOSED (context.pos, set by canli): the exit time is the last trailing-stop point,
        // the realised R + exit price come from context — so a closed trade shows Süre/Çıkış/R (not a
        // live-ticking duration + 0% PnL).
        const midasClosedLive = mode === 'live' && isTrailing && activeSignal.context?.pos === 'closed';
        const midasExitMs = (midasClosedLive && Array.isArray(activeSignal.trail) && activeSignal.trail.length)
          ? activeSignal.trail[activeSignal.trail.length - 1][0] * 1000 : null;
        const midasR = midasClosedLive ? Number(activeSignal.context?.pnl_r) : null;
        const midasExitPx = midasClosedLive ? Number(activeSignal.context?.exit_px) : null;
        // For closed trades, duration is signal → exit (backtest exit_time, or the MIDAS-live exit).
        const closedDurationMs = (mode === 'backtest' && sig.exitTs && effDate)
          ? sig.exitTs - effDate.getTime()
          : (midasExitMs && effDate ? midasExitMs - effDate.getTime() : null);
        const exitPrice = mode === 'backtest' ? sig.exitPrice : null;

        // Scale-out (d30_4h_so): first target +1R (60% booked), runner (40%) rides to breakeven
        // / a 20-day time exit. Compute the +1R level and a plain-language runner state so the
        // panel shows what the 4R "Hedef" row can't: where the partial is and how much is open.
        const soRisk = isScaleOut && Number.isFinite(dispEntry) && Number.isFinite(activeSignal.sl)
          ? Math.abs(dispEntry - activeSignal.sl) : null;
        const so1R = soRisk ? (activeSignal.dir === 'LONG' ? dispEntry + soRisk : dispEntry - soRisk) : null;
        const so1Rpct = so1R ? pctDist(dispEntry, so1R) : null;
        let soState = null, soStateColor = '#EAECEF';
        if (isScaleOut) {
          if (mode === 'backtest') {
            if (sig.status === 'SL') {
              // A reverse/early close (opposite signal closed the position before it reached +1R or
              // −1R) is stored as closed_sl too (status = R-sign), but it exits at the reverse PRICE,
              // not the SL. Only a TRUE full stop exits AT the SL — distinguish them so a −0.2R
              // reverse isn't shown as a −1R "full SL".
              const fullSL = Number.isFinite(exitPrice) && Number.isFinite(activeSignal.sl)
                && Math.abs(exitPrice - activeSignal.sl) / activeSignal.sl < 1e-4;
              soState = fullSL ? t('SL · tüm pozisyon (+1R görülmedi)') : t('Ters sinyal · erken kapanış (+1R yok)');
              soStateColor = '#F6465D';
            }
            else if (sig.status === 'TP') {
              const beRunner = Number.isFinite(exitPrice) && dispEntry
                && Math.abs(exitPrice - dispEntry) / dispEntry < 1e-6;
              const capRunner = Number.isFinite(exitPrice) && dispTp
                && Math.abs(exitPrice - dispTp) / dispTp < 1e-6;
              // distinguish a TRUE 3-day mark from a data-edge mark (runner window cut short by
              // the backtest data/window end — e.g. a signal in the last ~3 days of the window).
              const runnerDays = (effDate && Number.isFinite(sig.exitTs))
                ? (sig.exitTs - effDate.getTime()) / 86400000 : 99;
              soState = beRunner ? t('%{book} +1R alındı · %{run} runner BE (0R)', { book: soBookPct, run: soRunPct })
                : capRunner ? t('%{book} +1R alındı · %{run} runner +{cap}R cap', { book: soBookPct, run: soRunPct, cap: soCapR })
                : runnerDays >= (soHorizD - 0.1) ? t('%{book} +1R alındı · %{run} runner mark ({hor}g)', { book: soBookPct, run: soRunPct, hor: soHorizD })
                : t('%{book} +1R alındı · %{run} runner mark (veri sonu, <{hor}g)', { book: soBookPct, run: soRunPct, hor: soHorizD });
              soStateColor = '#0ECB81';
            } else { soState = t('Açık'); soStateColor = '#F5B942'; }
          } else {
            // live: mirror the backtest runner breakdown from the live status, so the live panel
            // reads as richly as backtest (not just a bare status string).
            const s = liveTradeStatus;
            if (s === 'SL Oldu' || s === 'TP/SL Aynı Mum') { soState = t('SL · tüm pozisyon (+1R görülmedi)'); soStateColor = '#F6465D'; }
            else if (s === 'BE Oldu') { soState = t('%{book} +1R alındı · %{run} runner BE (0R)', { book: soBookPct, run: soRunPct }); soStateColor = '#0ECB81'; }
            else if (s === 'TP Oldu') { soState = t('%{book} +1R alındı · %{run} runner +{cap}R cap', { book: soBookPct, run: soRunPct, cap: soCapR }); soStateColor = '#0ECB81'; }
            else if (s === 'İşlem Aktif (+1R Alındı · Runner)') { soState = t('%{book} +1R alındı · %{run} runner aktif (≤+{cap}R / {hor}g)', { book: soBookPct, run: soRunPct, cap: soCapR, hor: soHorizD }); soStateColor = '#F5B942'; }
            else { soState = s; soStateColor = '#F5B942'; }   // Entry Geldi / Sinyal Bekliyor / İptal
          }
        }

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
          <div className="position-row" title={t('Sinyalin üretildiği an (1h bar kapanışı), UTC')}>
            <span>{t('Sinyal (UTC)')}</span><b>{formatSignalTime(effDate)}</b>
          </div>
          <div className="position-row">
            <span>{(mode === 'live' && !midasClosedLive) ? t('Süre (canlı)') : t('Süre')}</span>
            <b>{formatDuration(closedDurationMs ?? ageMs)}</b>
          </div>
          <div className="position-row"><span>{t('Giriş')}{isConfirmEntry ? ' ·0.5R' : ''}</span><b>{formatPrice(dispEntry)}</b></div>
          {isTrailing ? null : !isScaleOut ? (
            <div className="position-row">
               <span>{t('Hedef')}</span>
               <b><span style={{color:'#0ECB81'}}>{formatPrice(dispTp)}</span>
                 {targetPct != null && <span style={{color:'#848E9C', fontWeight:400}}> · +{targetPct.toFixed(2)}%</span>}
               </b>
            </div>
          ) : (<>
            <div className="position-row">
               <span>{`TP1 (+1R · %${soBookPct})`}</span>
               <b><span style={{color:'#0ECB81'}}>{formatPrice(so1R)}</span>
                 {so1Rpct != null && <span style={{color:'#848E9C', fontWeight:400}}> · +{Math.abs(so1Rpct).toFixed(2)}%</span>}
               </b>
            </div>
            <div className="position-row">
               <span>{t('Runner Cap (+{cap}R)', { cap: soCapR })}</span>
               <b><span style={{color:'#0ECB81'}}>{formatPrice(dispTp)}</span>
                 {targetPct != null && <span style={{color:'#848E9C', fontWeight:400}}> · +{targetPct.toFixed(2)}%</span>}
               </b>
            </div>
            <div className="position-row">
               <span>{`Runner (%${soRunPct})`}</span>
               <b style={{color:'#F5B942', fontWeight:500}}>{t('+{cap}R cap · breakeven · {hor}g', { cap: soCapR, hor: soHorizD })}</b>
            </div>
            {soState && (
              <div className="position-row">
                <span>{t('Pozisyon Durumu')}</span>
                <b style={{color: soStateColor, fontWeight:500, textAlign:'right'}}>{soState}</b>
              </div>
            )}
          </>)}
          {isHalf && Number.isFinite(activeSignal.entry) && Number.isFinite(activeSignal.tp) && (() => {
            const halfLevelP = activeSignal.entry + (activeSignal.tp - activeSignal.entry) / 2;
            const halfPctP = pctDist(activeSignal.entry, halfLevelP);
            return (
              <div className="position-row">
                <span>½TP ({t('Kısmi')})</span>
                <b><span style={{color:'#F5B942'}}>{formatPrice(halfLevelP)}</span>
                  {halfPctP != null && <span style={{color:'#848E9C', fontWeight:400}}> · +{Math.abs(halfPctP).toFixed(2)}%</span>}
                </b>
              </div>
            );
          })()}
          {!isTrailing && (
          <div className="position-row">
             <span>{t('Stop')}</span>
             <b><span style={{color:'#F6465D'}}>{formatPrice(activeSignal.sl)}</span>
               {riskPct != null && <span style={{color:'#848E9C', fontWeight:400}}> · -{Math.abs(riskPct).toFixed(2)}%</span>}
             </b>
          </div>
          )}
          {rr != null && !isScaleOut && !isTrailing && (
            <div className="position-row">
              <span>{t('Risk-Reward')}</span>
              <b style={{ color: '#F5B942' }}>1:{rr.toFixed(2)}
                {isHalf && <span style={{color:'#848E9C', fontWeight:400}}> · ½TP maks +{(0.75 * rr).toFixed(2)}R</span>}
              </b>
            </div>
          )}
          {isScaleOut && (
            <div className="position-row">
              <span>{t('Risk-Reward')}</span>
              <b style={{ color: '#F5B942' }}>1:1 (TP1)<span style={{color:'#848E9C', fontWeight:400}}> · runner ≤+{soCapR}R / {soHorizD}g</span></b>
            </div>
          )}
          {mode === 'live' && !midasClosedLive && Number.isFinite(liveLastPrice) && (
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
          {((mode === 'backtest' && Number.isFinite(exitPrice) && exitPrice !== activeSignal.entry)
            || (midasClosedLive && Number.isFinite(midasExitPx))) && (
            <div className="position-row">
              <span>{t('Çıkış')}</span>
              <b>{formatPrice(midasClosedLive ? midasExitPx : exitPrice)}</b>
            </div>
          )}
          <div className="position-row">
            <span>{t('PnL')}</span>
            {midasClosedLive && Number.isFinite(midasR) ? (
              <b style={{ color: midasR >= 0 ? '#0ECB81' : '#F6465D' }}>{midasR >= 0 ? '+' : ''}{midasR.toFixed(2)}R</b>
            ) : Number.isFinite(soLiveR) ? (
              // scale-out LIVE R: +0.6−fee secured at the +1R partial / BE (floor while the
              // runner rides), −1R for a pre-+1R stop. Realised R comes from the nightly sync.
              <b style={{color: soLiveR >= 0 ? '#0ECB81' : '#F6465D'}}>
                {soLiveRFloor ? '≥' : ''}{soLiveR >= 0 ? '+' : ''}{soLiveR.toFixed(2)}R
              </b>
            ) : (
              <b style={{color: activePnL === null || activePnL >= 0 ? '#0ECB81' : '#F6465D'}}>
                {activePnL !== null ? formatPnL(activeSignal, activePnL) : '--'}
              </b>
            )}
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
              {Number.isFinite(activeSignal.confluenceScore) && !isTrailing && (
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
          <div className="position-row"><span>Entry{isConfirmEntry ? ' ·0.5R' : ''}</span><b>{formatPrice(dispEntry)}</b></div>
          <div className="position-row">
            <span>TP / SL</span>
            <b><span style={{color:'#0ECB81'}}>{formatPrice(dispTp)}</span> / <span style={{color:'#F6465D'}}>{formatPrice(activeSignal.sl)}</span></b>
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
        <iframe
          className="tv-iframe" title="TradingView" src={getTvEmbedUrl()}
          frameBorder="0" allowTransparency="true" allow="fullscreen; clipboard-write" loading="lazy"
          referrerPolicy="no-referrer"
          sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        />
      )}
    </div>
  );
};

export default ChartModal;
