import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { createChart, CandlestickSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts';
import { rpc } from '../utils/supa';
import { scaleOutLiveR } from '../utils/liveR';
import PusuLogo from '../components/PusuLogo';
import './SharedTradePage.css';

// PUBLIC paylaşım sayfası (/p/:token) — login YOK. Admin bir canlı işlemi "Paylaş" ile
// 1 saatlik bir linke çevirir; link o işlemin CANLI grafiğini ve sonucunu gösterir.
//
// Veri iki parçadan gelir:
//   1) GEOMETRİ — paylaşım anında admin'in tarayıcısında dondurulup share_links.payload'a
//      yazılmış entry/sl/tp/tp1 (·0.5R confirm kaydırması ve scale-out cap'i ORADA çözülür).
//      Böylece bu sayfa strateji etiketini hiç görmez, yeniden türetmesi de gerekmez.
//   2) CANLI — get_shared_trade RPC'si (anon) her yüklemede signals.context'ten yalnız
//      trail / pos / exit_px / pnl_r beyaz-listesini çeker. Mumlar Binance'ten (herkese açık).
//
// GİZLİLİK: strateji/versiyon/kalite/konfluens/ATRX bu sayfaya ASLA gelmez (RPC göndermez).
// Panelde "Strateji" satırı bilerek yoktur — bkz. 018_share_links.sql gizlilik sözleşmesi.

const POLL_MS = 20000;
const PAD_BARS = 40;
const LADDER = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'];
const IV_MS = { '1m': 60e3, '3m': 180e3, '5m': 300e3, '15m': 900e3, '30m': 1800e3, '1h': 3600e3, '4h': 14400e3, '1d': 86400e3 };

const UP = '#0ECB81';
const DOWN = '#F6465D';
const GOLD = '#F0B90B';

const norm = (s) => (s ? s.replace(/[^A-Za-z0-9]/g, '') : '');

const fmtPrice = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '--';
  const a = Math.abs(n);
  if (a >= 100) return n.toFixed(2);
  if (a >= 1) return n.toFixed(4);
  if (a >= 0.01) return n.toFixed(5);
  if (a >= 0.0001) return n.toFixed(7);
  return n.toPrecision(4);
};
const fmtTime = (ms) => (Number.isFinite(ms)
  ? new Date(ms).toLocaleString('tr-TR', { timeZone: 'UTC', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + ' UTC'
  : '--');
const fmtDur = (ms) => {
  if (!Number.isFinite(ms) || ms < 0) return '--';
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return `${mins} dk`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} sa ${mins % 60} dk`;
  return `${Math.floor(hrs / 24)} gün ${hrs % 24} sa`;
};

// Mumlardan işlemin akıbetini çöz — ChartModal'ın touch-scan'inin sadeleştirilmiş ikizi.
// tp1 varsa scale-out geometrisi (TP1'de kısmi + stop breakeven'a), yoksa düz TP/SL.
function scanOutcome(candles, p) {
  const long = p.dir === 'LONG';
  const entryTs = Math.floor(p.signalTs / 1000);   // signalTs = bar KAPANIŞI (paylaşımda çözüldü)
  const hasT1 = Number.isFinite(p.tp1);
  const hasTp = Number.isFinite(p.tp);
  const out = { filled: false, fillT: null, partT: null, closeT: null, result: null, partial: false };
  let stop = p.sl;

  for (const c of candles) {
    if (c.time < entryTs) continue;
    const eHit = p.entryIsStop
      ? (long ? c.high >= p.entry : c.low <= p.entry)     // ·0.5R confirm: giriş bir STOP emri
      : (long ? c.low <= p.entry : c.high >= p.entry);
    const stopHit = long ? c.low <= stop : c.high >= stop;
    const tpHit = hasTp && (long ? c.high >= p.tp : c.low <= p.tp);
    const t1Hit = hasT1 && (long ? c.high >= p.tp1 : c.low <= p.tp1);

    if (!out.filled) {
      if (!eHit && (stopHit || tpHit)) { out.closeT = c.time; out.result = 'CANCEL'; break; }
      if (!eHit) continue;
      out.filled = true; out.fillT = c.time;
      if (stopHit && !(hasT1 ? t1Hit : tpHit)) { out.closeT = c.time; out.result = 'SL'; break; }
      if (hasT1 && t1Hit) { out.partial = true; out.partT = c.time; stop = p.entry; }
      else if (!hasT1 && tpHit) { out.closeT = c.time; out.result = 'TP'; break; }
      continue;
    }
    if (hasT1 && !out.partial) {
      if (stopHit) { out.closeT = c.time; out.result = 'SL'; break; }
      if (t1Hit) { out.partial = true; out.partT = c.time; stop = p.entry; }   // %X alındı, stop → BE
      continue;
    }
    if (hasT1) {                                          // runner
      if (stopHit) { out.closeT = c.time; out.result = 'BE'; break; }
      if (tpHit) { out.closeT = c.time; out.result = 'TP'; break; }
      continue;
    }
    if (stopHit) { out.closeT = c.time; out.result = 'SL'; break; }
    if (tpHit) { out.closeT = c.time; out.result = 'TP'; break; }
  }
  return out;
}

const Row = ({ k, v, color, sub }) => (
  <div className="shp-row">
    <span>{k}</span>
    <b style={color ? { color } : undefined}>
      {v}{sub && <span className="shp-sub"> · {sub}</span>}
    </b>
  </div>
);

const STATUS_TEXT = {
  CANCEL: ['İptal (giriş gelmeden)', '#848E9C'],
  SL: ['Stop oldu', DOWN],
  BE: ['Kısmi alındı · kalan breakeven', UP],
  TP: ['Hedefe ulaştı', UP],
};

export default function SharedTradePage() {
  const { token } = useParams();
  const [state, setState] = useState({ phase: 'loading' });   // loading | ok | error
  const [candles, setCandles] = useState(null);
  const [now, setNow] = useState(() => Date.now());

  const boxRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const trailRef = useRef(null);
  const linesRef = useRef([]);

  // ---- 1. Link çöz + canlı alanları tazele (POLL_MS'de bir) ----------------
  const pull = useCallback(async () => {
    try {
      const r = await rpc('get_shared_trade', { p_token: token });
      if (r?.error) { setState({ phase: 'error', code: r.error }); return; }
      if (!r?.payload?.symbol) { setState({ phase: 'error', code: 'not_found' }); return; }
      setState({ phase: 'ok', payload: r.payload, live: r.live || {}, expiresAt: r.expires_at });
    } catch {
      setState({ phase: 'error', code: 'network' });
    }
  }, [token]);

  useEffect(() => {
    pull();   // eslint-disable-line react-hooks/set-state-in-effect -- async: setState await'ten SONRA
    const id = setInterval(pull, POLL_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { clearInterval(id); clearInterval(tick); };
  }, [pull]);

  // ---- 2. Mumlar (Binance public) ----------------------------------------
  const payload = state.phase === 'ok' ? state.payload : null;
  const live = state.phase === 'ok' ? state.live : null;

  const closedTrailMs = (live?.pos === 'closed' && Array.isArray(live.trail) && live.trail.length)
    ? live.trail[live.trail.length - 1][0] * 1000 : null;

  useEffect(() => {
    if (!payload) return undefined;
    let alive = true;
    const load = async () => {
      const ltfMs = IV_MS[payload.ltf] || 60e3;
      const endMs = closedTrailMs ? closedTrailMs + PAD_BARS * ltfMs : Date.now();
      let iv = payload.ltf && IV_MS[payload.ltf] ? payload.ltf : '1m';
      let start = payload.signalTs - PAD_BARS * ltfMs;
      // ~1450 barı aşmayacak şekilde aralığı kabalaştır (ChartModal ile aynı merdiven).
      while ((endMs - start) / IV_MS[iv] > 1450) {
        const i = LADDER.indexOf(iv);
        if (i < 0 || i === LADDER.length - 1) break;
        iv = LADDER[i + 1];
      }
      const q = `symbol=${norm(payload.symbol)}&interval=${iv}&startTime=${Math.floor(start)}&endTime=${Math.floor(endMs)}&limit=1500`;
      try {
        let raw = await (await fetch(`https://fapi.binance.com/fapi/v1/klines?${q}`)).json();
        if (!Array.isArray(raw)) raw = await (await fetch(`https://api.binance.com/api/v3/klines?${q}`)).json();
        if (!alive || !Array.isArray(raw) || !raw.length) return;
        setCandles(raw.map((d) => ({
          time: d[0] / 1000, open: +d[1], high: +d[2], low: +d[3], close: +d[4],
        })));
      } catch { /* bir sonraki poll dener */ }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(id); };
  }, [payload?.symbol, payload?.ltf, payload?.signalTs, closedTrailMs]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ---- 3. Grafik ---------------------------------------------------------
  useEffect(() => {
    if (!boxRef.current || !payload || !candles?.length) return undefined;
    const el = boxRef.current;
    const chart = createChart(el, {
      layout: {
        background: { type: 'solid', color: '#0B0E11' }, textColor: '#EAECEF',
        fontFamily: "'JetBrains Mono', 'SF Mono', Consolas, monospace",
      },
      localization: {
        timeFormatter: (ts) => new Date(ts * 1000).toLocaleString('tr-TR', {
          timeZone: 'UTC', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
        }) + ' UTC',
      },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      width: el.clientWidth, height: el.clientHeight,
      rightPriceScale: { borderColor: '#2B3139', scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2B3139' },
      crosshair: { mode: 1 },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP, wickDownColor: DOWN,
    });
    candle.setData(candles);
    chartRef.current = chart;
    seriesRef.current = candle;

    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }));
    ro.observe(el);
    chart.timeScale().fitContent();
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; seriesRef.current = null; trailRef.current = null; linesRef.current = []; };
  }, [payload?.symbol, candles?.length ? candles[0].time : null]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Mum verisi tazelendiğinde seriyi güncelle (grafiği yeniden kurmadan).
  useEffect(() => {
    if (seriesRef.current && candles?.length) seriesRef.current.setData(candles);
  }, [candles]);

  // Seviye çizgileri + iz-süren stop + giriş/çıkış işaretleri.
  const outcome = (payload && candles?.length && payload.kind !== 'trailing')
    ? scanOutcome(candles, payload) : null;

  useEffect(() => {
    const candle = seriesRef.current;
    if (!candle || !payload || !candles?.length) return;

    linesRef.current.forEach((l) => { try { candle.removePriceLine(l); } catch { /* zaten gitti */ } });
    linesRef.current = [];
    const line = (price, color, title, style = 2) => {
      const n = Number(price);
      if (!Number.isFinite(n)) return;
      linesRef.current.push(candle.createPriceLine({
        price: n, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title,
      }));
    };

    const trailing = payload.kind === 'trailing';
    line(payload.entry, '#848E9C', 'Giriş', 0);
    line(payload.sl, DOWN, trailing ? 'Stop (1R)' : 'Stop', 2);
    if (!trailing) {
      if (Number.isFinite(payload.tp1)) line(payload.tp1, UP, 'TP1', 2);
      line(payload.tp, 'rgba(14,203,129,0.75)', 'Hedef', 2);
    }

    // İz süren stop — basamaklı çizgi (canlı: her poll'de uzar).
    const trail = Array.isArray(live?.trail) ? live.trail : null;
    if (trailing && trail?.length) {
      if (!trailRef.current) {
        trailRef.current = chartRef.current.addSeries(LineSeries, {
          color: GOLD, lineWidth: 2, lineStyle: 0, lineType: 1,   // stepped
          priceLineVisible: false, lastValueVisible: true, title: 'İz süren stop',
        });
      }
      const pts = trail
        .map(([ts, px]) => ({ time: Math.floor(ts), value: Number(px) }))
        .filter((p) => Number.isFinite(p.value))
        .sort((a, b) => a.time - b.time);
      const dedup = pts.filter((p, i) => i === 0 || p.time !== pts[i - 1].time);
      if (dedup.length) trailRef.current.setData(dedup);
    }

    // İşaretler
    const long = payload.dir === 'LONG';
    const snap = (ms) => {
      const target = ms / 1000;
      let best = candles[0].time;
      for (const c of candles) { if (c.time <= target) best = c.time; else break; }
      return best;
    };
    const markers = [];
    const fillMs = trailing ? payload.signalTs : (outcome?.fillT ? outcome.fillT * 1000 : null);
    if (fillMs && (trailing || outcome?.filled)) {
      markers.push({
        time: snap(fillMs), position: long ? 'belowBar' : 'aboveBar',
        shape: long ? 'arrowUp' : 'arrowDown', color: GOLD, size: 2, text: 'Giriş',
      });
    }
    if (outcome?.partT) {
      markers.push({
        time: outcome.partT, position: long ? 'aboveBar' : 'belowBar',
        shape: 'circle', size: 1, color: GOLD, text: 'Kısmi alındı · stop girişe',
      });
    }
    const exitMs = trailing ? closedTrailMs : (outcome?.closeT ? outcome.closeT * 1000 : null);
    if (exitMs) {
      const r = Number(trailing ? live?.pnl_r : NaN);
      const win = trailing ? (Number.isFinite(r) ? r >= 0 : true) : (outcome.result === 'TP' || outcome.result === 'BE');
      markers.push({
        time: snap(exitMs), position: long ? 'aboveBar' : 'belowBar',
        shape: 'circle', size: 1, color: win ? UP : DOWN, text: 'Çıkış',
      });
    }
    markers.sort((a, b) => a.time - b.time);
    createSeriesMarkers(candle, markers);
  }, [payload, candles, live, outcome, closedTrailMs]);

  // ---- 4. Panel değerleri -------------------------------------------------
  if (state.phase === 'loading') {
    return <div className="shp shp--center"><PusuLogo size={56} animated /></div>;
  }
  if (state.phase === 'error') {
    const MSG = {
      expired: ['Linkin süresi doldu', 'Bu paylaşım bağlantısı 1 saatlik geçerlilik süresini doldurdu.'],
      revoked: ['Link iptal edildi', 'Bu paylaşım bağlantısı yayından kaldırıldı.'],
      not_found: ['Link bulunamadı', 'Bağlantı hatalı veya artık mevcut değil.'],
      network: ['Bağlantı hatası', 'Sunucuya ulaşılamadı. Sayfayı yenilemeyi deneyin.'],
    };
    const [title, body] = MSG[state.code] || MSG.not_found;
    return (
      <div className="shp shp--center">
        <div className="shp-empty">
          <PusuLogo size={44} />
          <h1>{title}</h1>
          <p>{body}</p>
        </div>
      </div>
    );
  }

  const long = payload.dir === 'LONG';
  const trailing = payload.kind === 'trailing';
  const last = candles?.length ? candles[candles.length - 1].close : null;
  const risk = Math.abs(payload.entry - payload.sl) || null;
  const sign = long ? 1 : -1;

  const trail = Array.isArray(live?.trail) ? live.trail : null;
  const trailPx = trail?.length ? Number(trail[trail.length - 1][1]) : null;
  const closedR = trailing ? Number(live?.pnl_r) : NaN;
  const exitPx = trailing ? Number(live?.exit_px) : null;
  const closed = trailing ? live?.pos === 'closed' : !!outcome?.closeT;
  const exitMs = trailing ? closedTrailMs : (outcome?.closeT ? outcome.closeT * 1000 : null);

  // Durum + R. Trailing: DB'den (canli cron yazar). Diğerleri: mum taramasından, R modeli
  // scaleOutLiveR (dashboard ile TEK kaynak) — scale-out'ta kısmi + runner ekonomisi.
  let statusText = 'Açık';
  let statusColor = GOLD;
  let rVal = null;
  let rFloor = false;

  if (trailing) {
    if (closed) {
      statusText = Number.isFinite(closedR) && closedR >= 0 ? 'Kapandı · kâr' : 'Kapandı · zarar';
      statusColor = Number.isFinite(closedR) && closedR >= 0 ? UP : DOWN;
      rVal = Number.isFinite(closedR) ? closedR : null;
    } else if (Number.isFinite(last) && risk) {
      statusText = 'Aktif';
      rVal = ((last - payload.entry) / risk) * sign;
    }
  } else if (outcome) {
    const hasT1 = Number.isFinite(payload.tp1);
    if (outcome.result) {
      const [txt, col] = STATUS_TEXT[outcome.result] || ['Açık', GOLD];
      statusText = txt; statusColor = col;
      if (hasT1) {
        const map = { SL: 'SL Oldu', BE: 'BE Oldu', TP: 'TP Oldu' };
        rVal = scaleOutLiveR(payload.entry, payload.sl, map[outcome.result],
          payload.capR ?? 4, payload.entryIsStop !== false, payload.bookFrac ?? 0.6);
      } else if (outcome.result === 'TP' && risk) {
        rVal = Math.abs(payload.tp - payload.entry) / risk;
      } else if (outcome.result === 'SL') {
        rVal = -1;
      }
      if (outcome.result === 'CANCEL') rVal = 0;
    } else if (outcome.filled) {
      if (outcome.partial) {
        statusText = 'Aktif · kısmi alındı, kalan koşuyor';
        rVal = scaleOutLiveR(payload.entry, payload.sl, 'İşlem Aktif (+1R Alındı · Runner)',
          payload.capR ?? 4, payload.entryIsStop !== false, payload.bookFrac ?? 0.6);
        rFloor = true;
      } else {
        statusText = 'Aktif';
        if (Number.isFinite(last) && risk) rVal = ((last - payload.entry) / risk) * sign;
      }
    } else {
      statusText = 'Giriş bekleniyor';
      statusColor = '#848E9C';
    }
  }

  const pnlPct = (closed && Number.isFinite(exitPx) && payload.entry)
    ? ((exitPx - payload.entry) / payload.entry) * 100 * sign
    : (Number.isFinite(last) && payload.entry && (trailing || outcome?.filled))
      ? ((last - payload.entry) / payload.entry) * 100 * sign
      : null;

  const durMs = exitMs ? exitMs - payload.signalTs : now - payload.signalTs;
  const leftMs = new Date(state.expiresAt).getTime() - now;
  const leftMin = Math.max(0, Math.floor(leftMs / 60000));
  const pnlColor = rVal == null ? '#EAECEF' : rVal >= 0 ? UP : DOWN;

  return (
    <div className="shp">
      <header className="shp-head">
        <div className="shp-head__id">
          <PusuLogo size={26} />
          <h1>
            {payload.symbol} <span style={{ color: long ? UP : DOWN }}>{payload.dir}</span>
          </h1>
        </div>
        <div className="shp-head__ttl" title="Bu bağlantının kalan geçerlilik süresi">
          {leftMs > 0 ? `Link ${leftMin} dk sonra kapanır` : 'Süre doldu'}
        </div>
      </header>

      <div className="shp-body">
        <aside className="shp-panel">
          <Row k="Sinyal (UTC)" v={fmtTime(payload.signalTs)} />
          <Row k={closed ? 'Süre' : 'Süre (canlı)'} v={fmtDur(durMs)} />
          <Row k="Giriş" v={fmtPrice(payload.entry)} />
          {!trailing && Number.isFinite(payload.tp1) && <Row k="TP1 (kısmi)" v={fmtPrice(payload.tp1)} color={UP} />}
          {!trailing && <Row k="Hedef" v={fmtPrice(payload.tp)} color={UP} />}
          <Row k={trailing ? 'Stop (1R)' : 'Stop'} v={fmtPrice(payload.sl)} color={DOWN} />
          {trailing && Number.isFinite(trailPx) && <Row k="İz süren stop" v={fmtPrice(trailPx)} color={GOLD} />}
          {!closed && Number.isFinite(last) && <Row k="Anlık fiyat" v={fmtPrice(last)} />}
          {closed && Number.isFinite(exitPx) && <Row k="Çıkış" v={fmtPrice(exitPx)} />}
          <Row
            k="PnL"
            color={pnlColor}
            v={rVal == null ? '--' : `${rFloor ? '≥' : ''}${rVal >= 0 ? '+' : ''}${rVal.toFixed(2)}R`}
            sub={pnlPct == null ? null : `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`}
          />
          <Row k="Durum" v={statusText} color={statusColor} />
        </aside>

        <div className="shp-chart">
          {!candles?.length && <div className="shp-chart__status">Grafik yükleniyor…</div>}
          <div ref={boxRef} className="shp-chart__canvas" />
          <div className="shp-legend">
            <span><i className="shp-l shp-l--entry" />Giriş fiyatı</span>
            {trailing
              ? <span><i className="shp-l shp-l--trail" />İz süren stop — kâr kilitlenir</span>
              : <span><i className="shp-l shp-l--tp" />Hedef (kâr al)</span>}
            <span><i className="shp-l shp-l--sl" />Stop (zararı kes)</span>
          </div>
        </div>
      </div>

      <footer className="shp-foot">
        PUSU · Bu sayfa yalnızca bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.
      </footer>
    </div>
  );
}
