import { useEffect, useRef, useState, useMemo } from 'react';
import { useLang } from '../../context/LanguageContext';
import { renderCardBlob, sharePng } from '../../utils/shareCard';
import TradeChart from '../user/TradeChart';

// Bir BİNANCE pozisyonu için paylaşılabilir PUSU kartı + gerçek borsa rakamları.
// Açık pozisyonda canlı (mark/uPnL), kapananda nihai (realized). Grafik yok — kart yeterli;
// yalnız paylaşım kartındaki fiyat-yolu sparkline'ı için hafif kline çekilir.
// Kaynaklar: ict_trade.live_positions + live_account_snapshot + Binance public klines.
//
// Not: RUNNER'da snapshot uPnL yalnız AÇIK bacağı ölçer; TP1'de cebe giren +0.6R zaten realize
// olmuştur. Bu yüzden "Toplam" AÇIK'ta liveCalc'ın booked+uPnL toplamı, KAPALI'da realized_usd.

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

// showChart (2026-07-11, kullanıcı modu): kart+hücrelerin ALTINA işlem mum grafiği
// (TradeChart) ekler. Admin panoları default false ile eski davranışta kalır
// (da42fb1 "kart yeterli" kararı admin tarafında korunur).
const LivePositionModal = ({ pos, snap, calc, onClose, showChart = false }) => {
  const { t } = useLang();
  const [shareMsg, setShareMsg] = useState('');
  // Açık pozisyonun "şimdi"si bir kez yakalanır (render'da Date.now() = impure). Kapananda
  // gerekmez; exit_time kullanılır.
  const [nowMs, setNowMs] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setNowMs(Date.now()));  // Date.now() render dışında
    return () => cancelAnimationFrame(id);
  }, [pos.id]);

  const v = useMemo(() => {
    const closed = String(pos.state || '').toUpperCase() === 'CLOSED';
    const entry = n(pos.entry_fill_px) ?? n(pos.eff_entry) ?? n(pos.signal_entry);
    const qty = n(pos.qty) || 0;
    const lev = n(pos.leverage) || n(snap?.leverage) || 1;
    const margin = entry && qty ? (entry * qty) / lev : 0;
    const upnl = n(snap?.unrealized_pnl);
    const exitPx = closed ? (n(pos.exit_px) ?? n(pos.eff_cap) ?? n(pos.signal_entry)) : null;
    // Toplam: KAPALI → realized_usd (cüzdan gerçeği); AÇIK → TP1-booked + açık bacak uPnL
    const total = closed ? n(pos.realized_usd)
      : (calc?.totalUsd != null ? calc.totalUsd : upnl);
    const totalR = closed ? n(pos.realized_r) : (calc?.totalR ?? null);
    const endMs = closed
      ? new Date(pos.exit_time || pos.entry_fill_time || pos.signal_time).getTime()
      : nowMs;
    return {
      closed,
      entry,
      sl: n(pos.eff_sl) ?? n(pos.signal_sl),
      tp1: n(pos.eff_tp1),
      be: n(pos.eff_be),
      cap: n(pos.eff_cap) ?? n(pos.signal_cap),
      qty,
      lev,
      margin,
      mark: closed ? null : n(snap?.mark_price),   // canlı "Anlık" çizgisi yalnız açık pozisyonda
      exitPx,
      upnl,
      funding: n(snap?.funding_fee),
      total,
      roi: margin && total != null ? (total / margin) * 100 : null,
      totalR,
      reason: pos.exit_reason || null,
      long: String(pos.direction || '').toUpperCase() === 'LONG',
      startMs: new Date(pos.entry_fill_time || pos.signal_time).getTime(),
      endMs,
    };
  }, [pos, snap, calc, nowMs]);

  const win = v.total != null && v.total >= 0;
  const acc = win ? '#0ECB81' : '#F6465D';

  const closesRef = useRef(null);   // paylaşım kartındaki sparkline için mum kapanışları

  // Grafik YOK — yalnız paylaşım kartının fiyat-yolu sparkline'ı için mum kapanışlarını çek.
  // Best-effort: başarısız olursa kart yine gider (sparkline atlanır).
  useEffect(() => {
    if (!v.endMs || !v.startMs) return undefined;   // açıkta nowMs hazır olana kadar bekle
    let alive = true;
    (async () => {
      try {
        const spanMin = Math.max((v.endMs - v.startMs) / 60000, 30);
        const pad = spanMin * 0.15 * 60000;
        const res = await fetch(`${FAPI}?symbol=${norm(pos.symbol)}&interval=${intervalFor(spanMin)}`
          + `&startTime=${Math.floor(v.startMs - pad)}&endTime=${Math.floor(v.endMs + pad)}&limit=1000`);
        if (!res.ok || !alive) return;
        const raw = await res.json();
        if (alive && Array.isArray(raw)) closesRef.current = raw.map((k) => +k[4]);
      } catch { /* sparkline yoksa kart yine çizilir */ }
    })();
    return () => { alive = false; };
  }, [pos.symbol, v.startMs, v.endMs]);

  const REASON = {
    // OPUS scale-out
    sl: 'SL −1R', tp1_be: 'TP1+BE', breakeven: 'BE', cap: 'Cap',
    time_stop: t('Süre limiti'), reversed: t('Ters sinyal'), closed_externally: t('Borsa kapanışı'),
    // Altın (TALOS-ICHI-X / MIDAS-X) iz-süren
    'trail/stop': t('İz-süren stop'), time: t('Süre (8s)'), session: t('Seans sonu'),
    slipped: t('Fiyat kaçtı'), killswitch: 'Killswitch',
  };
  const rTxt = v.totalR == null ? '—' : `${v.totalR >= 0 ? '+' : ''}${v.totalR.toFixed(2)}R`;
  const kicker = v.closed ? t('KAPANDI') : t('AÇIK POZİSYON');
  const note = v.closed ? t('ROI = sonuç / başlangıç marjı') : t('ROI = toplam / başlangıç marjı · canlı');
  const durMs = v.endMs - v.startMs;

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
        mark: fmtPx(v.closed ? v.exitPx : v.mark),
        markLabel: v.closed ? t('Çıkış') : t('Anlık'),
        dur: fmtDur(durMs),
        r: rTxt,
        kicker,
        note,
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

  const cells = v.closed ? [
    [t('Fiili dolum'), fmtPx(v.entry)],
    [t('Çıkış'), fmtPx(v.exitPx)],
    [t('Kaldıraç'), `${v.lev}x`],
    [t('Marj'), v.margin ? `$${v.margin.toFixed(2)}` : '—'],
    [t('Sonuç'), v.reason ? (REASON[v.reason] || v.reason) : '—'],
    [t('Süre'), fmtDur(durMs)],
    [t('Toplam'), fmtUsd(v.total)],
    ['R', rTxt],
  ] : [
    [t('Fiili dolum'), fmtPx(v.entry)],
    [t('Anlık fiyat'), fmtPx(v.mark)],
    [t('Kaldıraç'), `${v.lev}x`],
    [t('Marj'), v.margin ? `$${v.margin.toFixed(2)}` : '—'],
    [t('uPnL (açık bacak)'), fmtUsd(v.upnl)],
    [t('Funding'), fmtUsd(v.funding)],
    [t('Toplam'), fmtUsd(v.total)],
    ['R', rTxt],
  ];

  return (
    <div className="lpm__backdrop" onClick={onClose} role="presentation">
      <div className="lpm" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <button className="lpm__close" onClick={onClose} aria-label={t('Kapat')}>✕</button>

        {/* PUSU kartı — açık pozisyonda canlı, kapananda nihai sonuç */}
        <div className="lpm__card" style={{ '--acc': acc }}>
          <div className="lpm__brand">
            <span className="lpm__logo">P U S U</span>
            <span className="lpm__sub">{kicker}</span>
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
          <div className="lpm__note">{note}</div>
          <div className="lpm__foot">
            <span>{fmtDur(durMs)}</span>
            <span className="lpm__motto">WAIT · TRAP · EXECUTE</span>
          </div>
          <button className="lpm__share" onClick={onShare} disabled={!!shareMsg}>
            {shareMsg || `↗ ${t('Paylaş')}`}
          </button>
        </div>

        {/* işlem grafiği (kullanıcı modu) — giriş/SL/hedef çizgileri + giriş/çıkış işaretleri */}
        {showChart && <TradeChart pos={pos} />}

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
