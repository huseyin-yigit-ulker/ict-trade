import { useEffect, useRef, useState, useMemo } from 'react';
import { createChart, CandlestickSeries, LineStyle, createSeriesMarkers } from 'lightweight-charts';
import { useLang } from '../../context/LanguageContext';
import { renderCardBlob, sharePng } from '../../utils/shareCard';

// Açık BİNANCE pozisyonu için grafik + gerçek borsa rakamları + paylaşılabilir canlı PUSU kartı.
// Kaynaklar: ict_trade.live_positions (plan seviyeleri) + live_account_snapshot (mark / uPnL /
// funding — executor'ün Binance'ten yazdığı GERÇEK durum) + Binance public klines (mumlar).
//
// Not: RUNNER'da snapshot uPnL yalnız AÇIK bacağı ölçer; TP1'de cebe giren +0.6R zaten realize
// olmuştur. Bu yüzden "Toplam" satırı LivePositionsPage.liveCalc'ın booked+uPnL toplamını kullanır.

const FAPI = 'https://fapi.binance.com/fapi/v1/klines';
const norm = (s) => (s ? s.replace(/[^A-Za-z0-9]/g, '') : '');
const n = (v) => (v == null || v === '' ? null : Number(v));

const intervalFor = (mins) => (mins <= 360 ? '1m' : mins <= 2880 ? '5m' : mins <= 14400 ? '15m' : '1h');
const fmtUsd = (v) => (v == null || !Number.isFinite(v) ? '—' : `${v >= 0 ? '+' : '−'}$${Math.abs(v).toFixed(2)}`);
// Eksende okunur kalsın: küçük fiyatlarda 5 anlamlı basamak yeter (0.0788779036 → 0.078878).
const fmtPx = (v) => (v == null || !Number.isFinite(v) ? '—' : String(Number(v.toPrecision(5))));
const fmtDur = (ms) => {
  if (!Number.isFinite(ms) || ms < 0) return '—';
  const m = Math.floor(ms / 60000);
  const d = Math.floor(m / 1440);
  const h = Math.floor((m % 1440) / 60);
  return `${d ? `${d}g ` : ''}${d || h ? `${h}s ` : ''}${m % 60}dk`;
};

const LivePositionModal = ({ pos, snap, calc, onClose }) => {
  const { t } = useLang();
  const boxRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [shareMsg, setShareMsg] = useState('');

  const v = useMemo(() => {
    const entry = n(pos.entry_fill_px) ?? n(pos.eff_entry) ?? n(pos.signal_entry);
    const qty = n(pos.qty) || 0;
    const lev = n(pos.leverage) || n(snap?.leverage) || 1;
    const margin = entry && qty ? (entry * qty) / lev : 0;
    const upnl = n(snap?.unrealized_pnl);
    // Toplam = TP1'de realize olan (varsa) + açık bacağın uPnL'i
    const total = calc?.totalUsd != null ? calc.totalUsd : upnl;
    return {
      entry,
      sl: n(pos.eff_sl) ?? n(pos.signal_sl),
      tp1: n(pos.eff_tp1),
      be: n(pos.eff_be),
      cap: n(pos.eff_cap) ?? n(pos.signal_cap),
      qty,
      lev,
      margin,
      mark: n(snap?.mark_price),
      upnl,
      funding: n(snap?.funding_fee),
      total,
      roi: margin && total != null ? (total / margin) * 100 : null,
      totalR: calc?.totalR ?? null,
      long: String(pos.direction || '').toUpperCase() === 'LONG',
      startMs: new Date(pos.entry_fill_time || pos.signal_time).getTime(),
    };
  }, [pos, snap, calc]);

  const win = v.total != null && v.total >= 0;
  const acc = win ? '#0ECB81' : '#F6465D';

  const seriesRef = useRef(null);
  const markLineRef = useRef(null);
  const closesRef = useRef(null);   // paylaşım kartındaki sparkline için mum kapanışları

  // Grafik YALNIZ pozisyon/plan seviyeleri değişince kurulur. Bağımlılıklar bilinçli olarak
  // primitif: `v` her render'da yeni obje (sayfadaki 1sn'lik tick yüzünden) — obje kimliğine
  // bağlansaydı grafik saniyede bir yıkılıp yeniden kurulur, "yükleniyor"da takılırdı.
  // Anlık mark ayrı efektte güncellenir; yoksa her yenilemede grafik sıfırlanırdı.
  useEffect(() => {
    let alive = true;
    let chart;
    (async () => {
      setLoading(true);
      setErr('');
      try {
        const spanMin = Math.max((Date.now() - v.startMs) / 60000, 30);
        const pad = spanMin * 0.15 * 60000;
        const res = await fetch(`${FAPI}?symbol=${norm(pos.symbol)}&interval=${intervalFor(spanMin)}`
          + `&startTime=${Math.floor(v.startMs - pad)}&limit=1000`);
        if (!res.ok) throw new Error(`klines ${res.status}`);
        const raw = await res.json();
        if (!alive || !boxRef.current) return;
        const bars = raw.map((k) => ({
          time: Math.floor(k[0] / 1000), open: +k[1], high: +k[2], low: +k[3], close: +k[4],
        }));
        if (!bars.length) throw new Error('mum yok');

        chart = createChart(boxRef.current, {
          layout: { background: { color: 'transparent' }, textColor: '#848E9C', attributionLogo: false },
          grid: { vertLines: { color: 'rgba(42,47,58,0.5)' }, horzLines: { color: 'rgba(42,47,58,0.5)' } },
          rightPriceScale: { borderColor: '#2a2f3a' },
          timeScale: { borderColor: '#2a2f3a', timeVisible: true },
          height: 300,
          autoSize: true,
        });
        const series = chart.addSeries(CandlestickSeries, {
          upColor: '#0ECB81', downColor: '#F6465D', borderVisible: false,
          wickUpColor: '#0ECB81', wickDownColor: '#F6465D',
        });
        series.setData(bars);
        seriesRef.current = series;
        closesRef.current = bars.map((x) => x.close);

        // Aynı fiyata düşen seviyeler birleştirilir — RUNNER'da BE == Giriş olur ve iki
        // eksen etiketi üst üste binerdi. Tolerans: fiyatın binde biri.
        const levels = [
          { p: v.cap, c: '#0ECB81', s: LineStyle.Dashed, l: 'Cap' },
          { p: v.tp1, c: '#0ECB81', s: LineStyle.Solid, l: 'TP1' },
          { p: v.entry, c: '#e8eaed', s: LineStyle.Dashed, l: t('Giriş') },
          { p: v.be, c: '#848E9C', s: LineStyle.Dotted, l: 'BE' },
          { p: v.sl, c: '#F6465D', s: LineStyle.Solid, l: 'SL' },
        ].filter((x) => x.p != null && Number.isFinite(x.p));

        const merged = [];
        levels.forEach((x) => {
          const hit = merged.find((m) => Math.abs(m.p - x.p) <= Math.abs(x.p) * 1e-3);
          if (hit) hit.l += `·${x.l}`;
          else merged.push({ ...x });
        });
        merged.forEach((m) => series.createPriceLine({
          price: m.p, color: m.c, lineWidth: 1, lineStyle: m.s,
          axisLabelVisible: true, title: `${m.l} ${fmtPx(m.p)}`,
        }));

        const entryBar = bars.find((b) => b.time * 1000 >= v.startMs) || bars[0];
        createSeriesMarkers(series, [{
          time: entryBar.time, position: v.long ? 'belowBar' : 'aboveBar',
          color: '#F5B942', shape: v.long ? 'arrowUp' : 'arrowDown', text: t('Giriş'),
        }]);
        chart.timeScale().fitContent();
        setLoading(false);
      } catch (e) {
        if (alive) { setErr(String(e.message || e)); setLoading(false); }
      }
    })();
    return () => {
      alive = false;
      seriesRef.current = null;
      markLineRef.current = null;
      if (chart) chart.remove();
    };
  }, [pos.id, pos.symbol, v.startMs, v.entry, v.sl, v.tp1, v.be, v.cap, v.long, t]);

  // Anlık mark fiyatı: grafiği yeniden kurmadan çizgiyi taşı (her yenilemede zoom kaybolmasın).
  useEffect(() => {
    const s = seriesRef.current;
    if (!s || v.mark == null || !Number.isFinite(v.mark)) return;
    if (markLineRef.current) s.removePriceLine(markLineRef.current);
    markLineRef.current = s.createPriceLine({
      price: v.mark, color: '#5C93FF', lineWidth: 1, lineStyle: LineStyle.Solid,
      axisLabelVisible: true, title: `${t('Anlık')} ${fmtPx(v.mark)}`,
    });
  }, [v.mark, t, loading]);

  const onShare = async () => {
    setShareMsg(t('Hazırlanıyor…'));
    try {
      const blob = await renderCardBlob({
        t,
        symbol: pos.symbol,
        long: v.long,
        lev: v.lev,
        roi: v.roi,
        total: v.total,
        margin: v.margin,
        entry: fmtPx(v.entry),
        mark: fmtPx(v.mark),
        dur: fmtDur(Date.now() - v.startMs),
        r: v.totalR == null ? '—' : `${v.totalR >= 0 ? '+' : ''}${v.totalR.toFixed(2)}R`,
        kicker: t('AÇIK POZİSYON'),
        note: t('ROI = toplam / başlangıç marjı · canlı'),
        footer: new Date().toLocaleString(),
        closes: closesRef.current,
        entryPx: v.entry,
      });
      const res = await sharePng(blob, `pusu-${pos.symbol}-${pos.id}.png`, `PUSU · ${pos.symbol}`);
      setShareMsg(res === 'shared' ? '' : res === 'downloaded' ? t('Görsel indirildi')
        : res === 'cancelled' ? '' : t('Paylaşılamadı'));
    } catch {
      setShareMsg(t('Paylaşılamadı'));
    }
    setTimeout(() => setShareMsg(''), 2500);
  };

  const cells = [
    [t('Fiili dolum'), fmtPx(v.entry)],
    [t('Anlık fiyat'), fmtPx(v.mark)],
    [t('Kaldıraç'), `${v.lev}x`],
    [t('Marj'), v.margin ? `$${v.margin.toFixed(2)}` : '—'],
    [t('uPnL (açık bacak)'), fmtUsd(v.upnl)],
    [t('Funding'), fmtUsd(v.funding)],
    [t('Toplam'), fmtUsd(v.total)],
    ['R', v.totalR == null ? '—' : `${v.totalR >= 0 ? '+' : ''}${v.totalR.toFixed(2)}R`],
  ];

  return (
    <div className="lpm__backdrop" onClick={onClose} role="presentation">
      <div className="lpm" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <button className="lpm__close" onClick={onClose} aria-label={t('Kapat')}>✕</button>

        {/* canlı PUSU kartı — Telegram kapanış kartının açık-pozisyon sürümü */}
        <div className="lpm__card" style={{ '--acc': acc }}>
          <div className="lpm__brand">
            <span className="lpm__logo">P U S U</span>
            <span className="lpm__sub">{t('AÇIK POZİSYON')}</span>
          </div>
          <div className="lpm__sym">
            <b>{pos.symbol}</b>
            <span className={v.long ? 'lpm__dir lpm__dir--long' : 'lpm__dir lpm__dir--short'}>
              {v.long ? 'LONG' : 'SHORT'} · {v.lev}x
            </span>
          </div>
          <div className="lpm__roi">{v.roi == null ? '—' : `${v.roi >= 0 ? '+' : ''}${v.roi.toFixed(1)}%`}</div>
          <div className="lpm__usd">
            {fmtUsd(v.total)}
            {v.margin ? <span className="lpm__margin"> · {t('marj')} ${v.margin.toFixed(2)}</span> : null}
          </div>
          <div className="lpm__note">{t('ROI = toplam / başlangıç marjı · canlı')}</div>
          <div className="lpm__foot">
            <span>{fmtDur(Date.now() - v.startMs)}</span>
            <span className="lpm__motto">WAIT · TRAP · EXECUTE</span>
          </div>
          <button className="lpm__share" onClick={onShare} disabled={!!shareMsg}>
            {shareMsg || `↗ ${t('Paylaş')}`}
          </button>
        </div>

        {/* mumlar + plan seviyeleri + anlık mark */}
        <div className="lpm__chartwrap">
          {loading && <div className="lpm__msg">{t('Grafik yükleniyor…')}</div>}
          {err && <div className="lpm__msg lpm__msg--err">{t('Grafik yüklenemedi')}: {err}</div>}
          <div ref={boxRef} className="lpm__chart" />
        </div>

        {/* gerçek Binance rakamları */}
        <div className="lpm__grid">
          {cells.map(([k, val]) => (
            <div key={k} className="lpm__cell">
              <span className="lpm__k">{k}</span>
              <b className="lpm__v">{val}</b>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default LivePositionModal;
