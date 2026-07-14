import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts';
import { useLang } from '../../context/LanguageContext';
import { useTheme } from '../../context/ThemeContext';
import { readChartTheme } from '../../utils/chartTheme';

// İşlem grafiği — kullanıcı modunda LivePositionModal içinde: pozisyonun ömrünü
// mum grafikte gösterir (giriş/SL/hedef çizgileri + giriş/çıkış işaretleri).
// Gizlilik: seviye etiketleri nötr (Giriş/Stop/TP1/Hedef) — R ekonomisi/strateji
// sözlüğü yok. Veri: Binance klines (fapi → spot fallback), aralık pencereye göre
// otomatik kabalaşır (≤ ~1400 bar). Best-effort: veri yoksa kısa bir not gösterir.

const LADDER = [['1m', 60e3], ['5m', 300e3], ['15m', 900e3], ['1h', 3600e3], ['4h', 14400e3]];
const norm = (s) => (s ? s.replace(/[^A-Za-z0-9]/g, '') : '');

export default function TradeChart({ pos }) {
  const { t } = useLang();
  const { theme } = useTheme();   // toggle -> efekt yeniden koşar (canvas CSS var çözemez)
  const ref = useRef(null);
  const [status, setStatus] = useState('');

  useEffect(() => {
    if (!ref.current) return undefined;
    const el = ref.current;
    const th = readChartTheme();   // CSS token'ları çözülmüş renk olarak (taze okuma)
    const chart = createChart(el, {
      layout: { background: { type: 'solid', color: th.bg }, textColor: th.text,
        fontFamily: "'JetBrains Mono', 'SF Mono', Consolas, monospace" },
      localization: { timeFormatter: (ts) => new Date(ts * 1000)
        .toLocaleString('tr-TR', { timeZone: 'UTC', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) + ' UTC' },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      width: el.clientWidth, height: el.clientHeight,
      rightPriceScale: { borderColor: th.border, scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: th.border },
      crosshair: { mode: 1 },
      handleScroll: { pressedMouseMove: true, touch: true },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: th.up, downColor: th.down, borderVisible: false,
      wickUpColor: th.up, wickDownColor: th.down,
    });

    let cancelled = false;
    (async () => {
      try {
        setStatus(t('Grafik yükleniyor…'));
        const entryMs = new Date(pos.entry_fill_time || pos.updated_at || Date.now()).getTime();
        const exitMs = pos.exit_time ? new Date(pos.exit_time).getTime() : Date.now();
        const pad = Math.max(2 * 3600e3, (exitMs - entryMs) * 0.2);
        const from = entryMs - pad;
        const to = Math.min(Date.now(), exitMs + pad);
        let interval = '1m';
        for (const [iv, ms] of LADDER) { interval = iv; if ((to - from) / ms <= 1400) break; }
        const q = `symbol=${norm(pos.symbol)}&interval=${interval}&startTime=${from}&endTime=${to}&limit=1500`;
        let raw = await (await fetch(`https://fapi.binance.com/fapi/v1/klines?${q}`)).json();
        if (!Array.isArray(raw)) raw = await (await fetch(`https://api.binance.com/api/v3/klines?${q}`)).json();
        if (cancelled) return;
        if (!Array.isArray(raw) || raw.length === 0) { setStatus(t('Grafik yüklenemedi')); return; }
        const candles = raw.map((d) => ({ time: d[0] / 1000, open: +d[1], high: +d[2], low: +d[3], close: +d[4] }));
        candle.setData(candles);

        // Seviye çizgileri — nötr etiketler (maskeye uygun)
        const line = (price, color, title, style = 2) => {
          if (price == null || !Number.isFinite(Number(price))) return;
          candle.createPriceLine({ price: Number(price), color, lineWidth: 1, lineStyle: style,
            axisLabelVisible: true, title });
        };
        line(pos.eff_entry || pos.signal_entry, th.muted, t('Giriş'), 0);
        if (pos.isGold) {
          line(pos.cur_sl || pos.signal_sl, th.accent, t('İz-Süren SL'));
        } else {
          line(pos.signal_sl, th.down, 'SL');
          line(pos.eff_tp1, th.up, 'TP1');
          line(pos.signal_cap, th.upSoft(0.55), t('Hedef'));
        }

        // Giriş/çıkış işaretleri
        const long = (pos.direction || '').toUpperCase() === 'LONG';
        const snap = (ms) => {
          const target = ms / 1000;
          let best = candles[0].time;
          for (const c of candles) { if (c.time <= target) best = c.time; else break; }
          return best;
        };
        const markers = [];
        if (pos.entry_fill_time) {
          markers.push({ time: snap(entryMs), position: long ? 'belowBar' : 'aboveBar',
            shape: long ? 'arrowUp' : 'arrowDown', color: th.accent, size: 2, text: t('Giriş') });
        }
        if (pos.exit_time) {
          const r = Number(pos.realized_r);
          markers.push({ time: snap(exitMs), position: long ? 'aboveBar' : 'belowBar',
            shape: 'circle', size: 1,
            color: Number.isFinite(r) && r < 0 ? th.down : th.up,
            text: `${t('Çıkış')}${Number.isFinite(r) ? ` ${r >= 0 ? '+' : ''}${r.toFixed(2)}R` : ''}` });
        }
        markers.sort((a, b) => a.time - b.time);
        if (markers.length) createSeriesMarkers(candle, markers);
        chart.timeScale().fitContent();
        setStatus('');
      } catch {
        if (!cancelled) setStatus(t('Grafik yüklenemedi'));
      }
    })();

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    });
    ro.observe(el);
    return () => { cancelled = true; ro.disconnect(); chart.remove(); };
  }, [pos, t, theme]);

  return (
    <div className="ush-tradechart">
      {status && <div className="ush-tradechart__status">{status}</div>}
      <div ref={ref} className="ush-tradechart__canvas" />
    </div>
  );
}
