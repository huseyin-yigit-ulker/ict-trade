import { useEffect, useState, useCallback, useRef } from 'react';
import { useLang } from '../context/LanguageContext';
import { authedFetch } from '../utils/supa';
import { useStreamDisplay } from '../utils/useStreamDisplay';
import './LivePositionsPage.css';

// MIDAS-X — the gold (XAUUSDT) VWAP-trend executor (sync/midas_exec), read straight from the LIVE
// Supabase via PostgREST. This is the PAPER/TESTNET sibling of the real-money OPUS "Binance Canlı" page:
//   ict_trade.midas_positions        — the managed MIDAS positions (state machine + chandelier stop)
//   ict_trade.live_account_snapshot  — the real Binance XAUUSDT mark / uPnL, refreshed by the executor
//   ict_trade.live_account           — wallet / available / total uPnL, one row per network (testnet)
// Browser never signs a Binance request; it only reads what the executor snapshotted. No fixed TP —
// MIDAS-X rides a 3.5*ATR chandelier trailing stop to an 8h / session exit (cur_sl ratchets in profit).

const SUPA_URL = import.meta.env.VITE_SUPABASE_URL;
const SUPA_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
const OPEN_STATES = ['PENDING_ENTRY', 'ENTRY_WORKING', 'OPEN'];
const REFRESH_MS = 30000;

const STATE_BADGE = {
  PENDING_ENTRY: { label: 'GİRİŞ BEKLİYOR', cls: 'st-wait' },
  ENTRY_WORKING: { label: 'GİRİŞ EMRİ', cls: 'st-wait' },   // order-type detail is admin-only knowledge
  OPEN: { label: 'AÇIK · İZ-SÜREN', cls: 'st-active' },
  CLOSED: { label: 'KAPANDI', cls: 'st-done' },
  CANCELLED: { label: 'İPTAL', cls: 'st-cancel' },
};
const EXIT_LABEL = {
  'trail/stop': 'İz-Süren Stop', time: '8s Zaman', session: 'Seans Sonu',
  slipped: 'Fiyat Kaçtı', unfilled: 'Dolmadı', closed_externally: 'Borsa Kapanışı', killswitch: 'Killswitch',
};

// User-JWT fetch (utils/supa authedFetch) — RLS scopes the rows to the logged-in user.
async function getJSON(path) {
  const res = await authedFetch(path);
  if (!res.ok) {
    const body = await res.text();
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json();
}

const fmtPx = (v) => {
  if (v == null) return '—';
  const n = Number(v);
  return n >= 1000 ? n.toLocaleString('en-US', { maximumFractionDigits: 2 })
    : n.toLocaleString('en-US', { maximumFractionDigits: n >= 1 ? 4 : 6 });
};
const fmtUsd = (v) => (v == null ? '—' : `$${Number(v).toFixed(2)}`);
const fmtR = (v) => (v == null ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}R`);

function ago(iso, t) {
  if (!iso) return '—';
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s} ${t('sn önce')}`;
  if (s < 3600) return `${Math.floor(s / 60)} ${t('dk önce')}`;
  return `${Math.floor(s / 3600)} ${t('sa önce')}`;
}
function countdown(iso, t) {
  if (!iso) return null;
  const s = Math.floor((new Date(iso).getTime() - Date.now()) / 1000);
  if (s <= 0) return t('doldu');
  if (s < 3600) return `${Math.floor(s / 60)}dk`;
  const h = Math.floor(s / 3600);
  return h < 24 ? `${h}sa ${Math.floor((s % 3600) / 60)}dk` : `${Math.floor(h / 24)}g ${h % 24}sa`;
}

export default function MidasXLivePage() {
  const { t } = useLang();
  const sd = useStreamDisplay();   // stream identity masked for non-admins
  const [positions, setPositions] = useState([]);
  const [snap, setSnap] = useState(null);      // the XAUUSDT snapshot row
  const [account, setAccount] = useState(null);
  const [gateSigs, setGateSigs] = useState([]); // recent paper signals + exec_gate decisions
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [, forceTick] = useState(0);
  const timer = useRef(null);

  const load = useCallback(async () => {
    if (!SUPA_URL || !SUPA_KEY) { setErr(t('Supabase ayarları eksik.')); setLoading(false); return; }
    try {
      const [pos, snaps, acc, sigs] = await Promise.all([
        getJSON('midas_positions?select=*&order=updated_at.desc&limit=60'),
        getJSON('live_account_snapshot?select=*&symbol=eq.XAUUSDT'),
        getJSON('live_account?select=*'),
        // Paper signals + the executor's AFTER-LOSS gate verdict (context.exec_gate, written by
        // sync/midas_exec/executor._mark_gate). Shows WHY a paper signal did/didn't become an order.
        getJSON('signals?select=signal_time,direction,entry,context&mode=eq.midas&order=signal_time.desc&limit=10'),
      ]);
      const xau = snaps[0] || null;
      const net = xau?.network || 'testnet';
      setPositions(pos);
      setSnap(xau);
      setGateSigs(sigs);
      setAccount(acc.find((a) => a.network === net) || acc[0] || null);
      setErr('');
      setUpdatedAt(new Date());
    } catch (e) {
      setErr(e.status === 401 || e.status === 403
        ? t('Canlı tablolara erişim yok — anon SELECT grant uygulanmalı (sync/midas_exec/schema.sql).')
        : `${t('Veri alınamadı')}: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, REFRESH_MS);
    const tick = setInterval(() => forceTick((x) => x + 1), 1000); // live countdowns/ago
    return () => { clearInterval(timer.current); clearInterval(tick); };
  }, [load]);

  const open = positions.filter((p) => OPEN_STATES.includes(p.state));
  const closed = positions.filter((p) => p.state === 'CLOSED' || p.state === 'CANCELLED').slice(0, 12);
  const net = snap?.network || account?.network || 'testnet';
  const stale = snap && (Date.now() - new Date(snap.updated_at).getTime() > 5 * 60 * 1000);

  // Live R/USD for a MIDAS-X trailing position: risk0 = |signal_entry − signal_sl| (no confirm buf,
  // no TP1 booking — a single position rides one ratcheting stop). liveR = open uPnL / (risk0×qty);
  // lockedR = (cur_sl − entry)/risk0, the R already locked if the trailing stop were hit now.
  const liveCalc = (p) => {
    const qty = Number(p.qty) || 0;
    const risk0 = Number(p.risk0) || Math.abs(Number(p.signal_entry) - Number(p.signal_sl));
    const oneRusd = risk0 * qty;
    const upnl = snap && snap.symbol === p.symbol && snap.unrealized_pnl != null ? Number(snap.unrealized_pnl) : null;
    return {
      oneRusd,
      upnl,
      liveR: (upnl == null || !oneRusd) ? null : upnl / oneRusd,
      lockedR: p.locked_r != null ? Number(p.locked_r) : null,
    };
  };

  return (
    <div className="livex">
      <div className="livex__head">
        <h1>{t('Binance Paper · Altın')}</h1>
        <span className={`livex__net livex__net--${net}`}>{net === 'testnet' ? 'TESTNET' : 'MAINNET'}</span>
        {/* Admin sees the executor detail; everyone else just the codename. */}
        <span className="livex__badge">{sd.isAdmin
          ? `${sd.name('midas')}-X · XAU 1m · iz-süren · PAPER`
          : `${sd.name('midas')} · PAPER`}</span>
        <span className="livex__badge" title={t('Yalnız aynı fx-gününün önceki işlemi zararla kapandıysa emir açılır; günün ilk sinyali ve kazanç-sonrası sinyaller atlanır. Sinyal akışı etkilenmez.')}>
          🚧 {t('Kayıp-sonrası kapı')}
        </span>
        <span className="livex__upd">{updatedAt ? `${t('Güncellendi')}: ${ago(snap?.updated_at, t)}` : ''}</span>
        <button className="livex__refresh" onClick={load} title={t('Yenile')}>⟳</button>
      </div>

      <div className="livex__warn">
        {t('{name} altın akışı — Binance testnet (paper, gerçek para DEĞİL).', { name: sd.name('midas') })}
      </div>
      {stale && (
        <div className="livex__warn">{t('Snapshot 5 dk’dan eski — executor cron çalışmıyor olabilir.')}</div>
      )}
      {err && <div className="livex__err">{err}</div>}

      {/* account header (testnet) */}
      <div className="livex__kpis">
        <div className="livex__kpi"><span>{t('Cüzdan')}</span><b>{fmtUsd(account?.wallet_balance)}</b></div>
        <div className="livex__kpi"><span>{t('Kullanılabilir')}</span><b>{fmtUsd(account?.available_balance)}</b></div>
        <div className="livex__kpi">
          <span>{t('Açık uPnL')}</span>
          <b className={Number(account?.total_unrealized) >= 0 ? 'pos' : 'neg'}>{fmtUsd(account?.total_unrealized)}</b>
        </div>
        <div className="livex__kpi"><span>{t('Açık Pozisyon')}</span><b>{open.length}</b></div>
      </div>

      {/* open positions */}
      <h2 className="livex__h2">{t('Açık Pozisyonlar')}</h2>
      {loading ? <div className="livex__empty">{t('Yükleniyor…')}</div>
        : open.length === 0 ? <div className="livex__empty">{t('Açık pozisyon yok — sinyal bekleniyor.')}</div>
        : (
        <div className="livex__tablewrap">
          <table className="livex__table">
            <thead>
              <tr>
                <th>{t('Sembol')}</th><th>{t('Yön')}</th><th>{t('Durum')}</th>
                <th>{t('Giriş')}</th><th>{t('Mark')}</th><th>{t('İlk SL')}</th><th>{t('İz-Süren SL')}</th>
                <th>{t('Kilitli R')}</th><th>{t('Miktar')}</th><th>{t('Canlı K/Z')}</th><th>{t('Canlı R')}</th><th>Funding</th><th>{t('Geri Sayım')}</th>
              </tr>
            </thead>
            <tbody>
              {open.map((p) => {
                const lng = (p.direction || '').toUpperCase() === 'LONG';
                const sb = STATE_BADGE[p.state] || { label: p.state, cls: 'st-wait' };
                const pre = p.state === 'PENDING_ENTRY' || p.state === 'ENTRY_WORKING';
                const cd = countdown(pre ? p.entry_deadline : p.time_stop_at, t);
                const lc = liveCalc(p);
                return (
                  <tr key={p.id}>
                    <td className="mono livex__cardhead" data-label={t('Sembol')}>{p.symbol}</td>
                    <td data-label={t('Yön')}><span className={lng ? 'dir dir--long' : 'dir dir--short'}>{lng ? 'LONG' : 'SHORT'}</span></td>
                    <td data-label={t('Durum')}><span className={`st ${sb.cls}`}>{sb.label}</span></td>
                    <td className="mono" data-label={t('Giriş')}>{fmtPx(p.eff_entry || p.signal_entry)}</td>
                    <td className="mono" data-label={t('Mark')}>{fmtPx(snap?.mark_price)}</td>
                    <td className="mono dim" data-label={t('İlk SL')}>{fmtPx(p.signal_sl)}</td>
                    <td className="mono" data-label={t('İz-Süren SL')}>{fmtPx(p.cur_sl || p.signal_sl)}</td>
                    <td className={`mono ${Number(lc?.lockedR) >= 0 ? 'pos' : 'dim'}`} data-label={t('Kilitli R')}>{fmtR(lc?.lockedR)}</td>
                    <td className="mono" data-label={t('Miktar')}>{p.qty ?? '—'}</td>
                    <td className={`mono ${Number(lc?.upnl) >= 0 ? 'pos' : 'neg'}`} data-label={t('Canlı K/Z')}>{fmtUsd(lc?.upnl)}</td>
                    <td className={`mono ${Number(lc?.liveR) >= 0 ? 'pos' : 'neg'}`} data-label={t('Canlı R')}>{fmtR(lc?.liveR)}</td>
                    <td className={`mono ${Number(snap?.funding_fee) > 0 ? 'pos' : Number(snap?.funding_fee) < 0 ? 'neg' : 'dim'}`} data-label="Funding">
                      {snap?.funding_fee == null ? '—' : (Number(snap.funding_fee) >= 0 ? '+' : '−') + '$' + Math.abs(Number(snap.funding_fee)).toFixed(2)}
                    </td>
                    <td className="mono dim" data-label={t('Geri Sayım')}>{cd || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* paper signals + AFTER-LOSS gate verdicts (context.exec_gate, executor._mark_gate) */}
      {gateSigs.length > 0 && (
        <>
          <h2 className="livex__h2">{t('Sinyaller · Kapı Kararları')}</h2>
          <div className="livex__tablewrap">
            <table className="livex__table">
              <thead>
                <tr>
                  <th>{t('Sinyal')}</th><th>{t('Yön')}</th><th>{t('Giriş')}</th>
                  <th>{t('Kapı')}</th><th>{t('Sebep')}</th><th>{t('Paper Sonucu')}</th>
                </tr>
              </thead>
              <tbody>
                {gateSigs.map((s) => {
                  const ctx = s.context || {};
                  const g = ctx.exec_gate;
                  const lng = (s.direction || '').toUpperCase() === 'LONG';
                  const paperR = ctx.pos === 'closed' ? ctx.pnl_r : null;
                  return (
                    <tr key={s.signal_time}>
                      <td className="mono livex__cardhead" data-label={t('Sinyal')}>{ago(s.signal_time, t)}</td>
                      <td data-label={t('Yön')}><span className={lng ? 'dir dir--long' : 'dir dir--short'}>{lng ? 'LONG' : 'SHORT'}</span></td>
                      <td className="mono" data-label={t('Giriş')}>{fmtPx(s.entry)}</td>
                      <td data-label={t('Kapı')}>
                        {g == null
                          ? <span className="st st-wait">{t('kapı öncesi')}</span>
                          : g.skipped
                            ? <span className="st st-cancel">{t('AÇILMADI')}</span>
                            : <span className="st st-active">{t('EMİR AÇILDI')}</span>}
                      </td>
                      <td className="dim" data-label={t('Sebep')}>
                        {g?.skipped ? (g.reason || '').replace('after-loss gate: ', '') : '—'}
                      </td>
                      <td className={`mono ${paperR == null ? 'dim' : Number(paperR) >= 0 ? 'pos' : 'neg'}`} data-label={t('Paper Sonucu')}>
                        {paperR == null ? (ctx.pos === 'closed' ? '—' : t('açık')) : fmtR(paperR)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* recently closed */}
      {closed.length > 0 && (
        <>
          <h2 className="livex__h2">{t('Son Kapananlar')}</h2>
          <div className="livex__tablewrap">
            <table className="livex__table">
              <thead>
                <tr>
                  <th>{t('Sembol')}</th><th>{t('Yön')}</th><th>{t('Sonuç')}</th>
                  <th>R</th><th>{t('USD')}</th><th>{t('Çıkış')}</th>
                </tr>
              </thead>
              <tbody>
                {closed.map((p) => {
                  const lng = (p.direction || '').toUpperCase() === 'LONG';
                  const win = Number(p.realized_r) >= 0;
                  const cancelled = p.state === 'CANCELLED';
                  return (
                    <tr key={p.id}>
                      <td className="mono livex__cardhead" data-label={t('Sembol')}>{p.symbol}</td>
                      <td data-label={t('Yön')}><span className={lng ? 'dir dir--long' : 'dir dir--short'}>{lng ? 'LONG' : 'SHORT'}</span></td>
                      <td data-label={t('Sonuç')}><span className={`st ${cancelled ? 'st-cancel' : (win ? 'st-done' : 'st-sl')}`}>{EXIT_LABEL[p.exit_reason] || p.exit_reason || '—'}</span></td>
                      <td className={`mono ${win ? 'pos' : 'neg'}`} data-label="R">{p.realized_r == null ? '—' : fmtR(p.realized_r)}</td>
                      <td className={`mono ${win ? 'pos' : 'neg'}`} data-label={t('USD')}>{p.realized_usd == null ? '—' : fmtUsd(p.realized_usd)}</td>
                      <td className="mono dim" data-label={t('Çıkış')}>{ago(p.exit_time, t)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
