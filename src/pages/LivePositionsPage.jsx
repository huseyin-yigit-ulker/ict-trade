import { useEffect, useState, useCallback, useRef } from 'react';
import { useLang } from '../context/LanguageContext';
import { authedFetch } from '../utils/supa';
import { useStreamDisplay } from '../utils/useStreamDisplay';
import './LivePositionsPage.css';

// Reads the live-execution layer (sync/live_exec) straight from the LIVE Supabase via PostgREST:
//   ict_trade.live_positions        — the managed scale-out positions (d30so{CAP_R}c; state machine + plan levels)
//   ict_trade.live_account_snapshot — the REAL Binance state per symbol (mark / uPnL), refreshed
//                                     by the executor every ~2 min
//   ict_trade.live_account          — wallet / available / total uPnL, one row per network
// Browser never signs a Binance request; it only reads what the executor snapshotted.

const SUPA_URL = import.meta.env.VITE_SUPABASE_URL;
const SUPA_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
const OPEN_STATES = ['PENDING_ENTRY', 'ENTRY_WORKING', 'OPEN_FULL', 'RUNNER', 'CLOSING'];
const REFRESH_MS = 30000;
// Live stream = OPUS d30so8f3h7 (.env EXEC_VERSION): books CLOSE_FRAC=0.3 (30%) at +1R, runner rides to
// RUNNER_CAP_R=8. Keep CAP_R + SO.closeFrac below in sync with .env RUNNER_CAP_R / CLOSE_FRAC.
const CAP_R = 8;

const STATE_BADGE = {
  PENDING_ENTRY: { label: 'GİRİŞ BEKLİYOR', cls: 'st-wait' },
  ENTRY_WORKING: { label: 'GİRİŞ EMRİ', cls: 'st-wait' },
  OPEN_FULL: { label: 'AÇIK (TP1 ÖNCESİ)', cls: 'st-active' },
  RUNNER: { label: 'RUNNER (TP1 SONRASI)', cls: 'st-runner' },
  CLOSING: { label: 'KAPANIYOR', cls: 'st-active' },
  CLOSED: { label: 'KAPANDI', cls: 'st-done' },
  CANCELLED: { label: 'İPTAL', cls: 'st-cancel' },
};
const EXIT_LABEL = {
  sl: 'SL −1R', tp1_be: 'TP1+BE', breakeven: 'Breakeven', cap: `CAP +${CAP_R}R`,
  time_stop: '3g Zaman', entry_expired: 'Giriş Dolmadı', reversed: 'Ters Döndü', killswitch: 'Killswitch',
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
const fmtUsdSigned = (v) => (v == null ? '—' : `${Number(v) >= 0 ? '+' : '−'}$${Math.abs(Number(v)).toFixed(2)}`);
const fmtR = (v) => (v == null ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}R`);

// Scale-out plan (d30so{CAP_R}c): book CLOSE_FRAC at +FIRST_R (locks a floor), runner rides to +CAP_R.
// ·0.5R confirmed entry => R is measured against risk_eff = (1+buf)*risk0 (executor's denom),
// so the structural +CAP_R from the breakout is +(CAP_R-buf)/(1+buf) R of the realistic risk.
const SO = { closeFrac: 0.3, firstR: 1.0, confirmBuf: 0.5, capR: CAP_R };
const CAP_R_TOTAL = SO.closeFrac * SO.firstR + (1 - SO.closeFrac) * ((SO.capR - SO.confirmBuf) / (1 + SO.confirmBuf));

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

export default function LivePositionsPage() {
  const { t } = useLang();
  const sd = useStreamDisplay();   // stream identity masked for non-admins
  // The runner-cap column/exit labels reveal the stream's R economics — admin only;
  // everyone else sees a neutral "Hedef" (they still see the raw price levels, which
  // are visible on their own Binance account anyway).
  const capLabel = sd.isAdmin ? `Cap +${CAP_R}R` : t('Hedef');
  const exitLabel = (r) => (r === 'cap' && !sd.isAdmin ? t('Hedef') : EXIT_LABEL[r] || r || '—');
  const [positions, setPositions] = useState([]);
  const [snaps, setSnaps] = useState({});
  const [account, setAccount] = useState(null);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [, forceTick] = useState(0);
  const timer = useRef(null);

  const load = useCallback(async () => {
    if (!SUPA_URL || !SUPA_KEY) { setErr(t('Supabase ayarları eksik.')); setLoading(false); return; }
    try {
      const [pos, snap, acc] = await Promise.all([
        getJSON('live_positions?select=*&order=updated_at.desc&limit=60'),
        getJSON('live_account_snapshot?select=*&network=eq.mainnet'),
        getJSON('live_account?select=*'),
      ]);
      setPositions(pos);
      setSnaps(Object.fromEntries(snap.map((s) => [s.symbol, s])));
      // OPUS is the real-money MAINNET stream. The MIDAS-X paper bridge writes a second, testnet
      // live_account row into this shared table, so prefer the mainnet row (fall back to the single
      // row on a testnet-only box) — otherwise acc[0] could be MIDAS-X's stale testnet account.
      setAccount(acc.find((a) => a.network === 'mainnet') || acc[0] || null);
      setErr('');
      setUpdatedAt(new Date());
    } catch (e) {
      setErr(e.status === 401 || e.status === 403
        ? t('Canlı tablolara erişim yok — anon SELECT grant uygulanmalı (sync/live_exec/schema.sql).')
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
  // Funding paid/received on the CURRENTLY-open positions (snapshot funding_fee summed since entry;
  // negative = we paid). Binance settles perp funding every 8h — this is the live carry cost.
  const openFunding = open.reduce((a, p) => a + (Number(snaps[p.symbol]?.funding_fee) || 0), 0);
  const net = account?.network || 'testnet';
  const stale = account && (Date.now() - new Date(account.updated_at).getTime() > 5 * 60 * 1000);

  // Per-trade live R/USD breakdown, matching the executor's R convention (realized_r =
  // realized_usd / (risk_eff × qty), risk_eff = |eff_entry − sl|). For a RUNNER (post-TP1) the
  // live snapshot uPnL is ONLY the open runner leg, so the +1R-booked floor (close_frac×first_r,
  // already realized into the wallet) is added back here to show the TOTAL trade R, not just the
  // runner's. Also derives the $ value at each profit-taking level (TP1 / cap) for the columns.
  const liveCalc = (p) => {
    const sl = Number(p.signal_sl);
    const qty = Number(p.qty) || 0;
    const risk0 = Math.abs(Number(p.signal_entry) - sl);
    // effective per-unit risk: from the real fill once known, else the intended (1+buf)*risk0
    const riskEff = p.eff_entry != null ? Math.abs(Number(p.eff_entry) - sl) : (1 + SO.confirmBuf) * risk0;
    const oneRusd = riskEff * qty;                                  // 1R in $ (executor denom)
    if (!oneRusd) return null;
    const isRunner = p.state === 'RUNNER';
    const bookedR = isRunner ? SO.closeFrac * SO.firstR : 0;        // locked TP1 floor (+0.6R)
    const bookedUsd = bookedR * oneRusd;
    const s = snaps[p.symbol];
    const runnerUsd = s && s.unrealized_pnl != null ? Number(s.unrealized_pnl) : null;  // open-leg MTM
    const totalUsd = runnerUsd == null ? null : bookedUsd + runnerUsd;
    const totalR = totalUsd == null ? (isRunner ? bookedR : null) : totalUsd / oneRusd;
    return {
      oneRusd, isRunner, bookedR, bookedUsd, runnerUsd, totalUsd, totalR,
      tp1Usd: SO.closeFrac * SO.firstR * oneRusd,                   // $ booked when 60% closes at +1R
      capUsd: CAP_R_TOTAL * oneRusd,                                // total $ if the runner reaches +cap
    };
  };

  return (
    <div className="livex">
      <div className="livex__head">
        <h1>{t('Binance Canlı')}</h1>
        <span className={`livex__net livex__net--${net}`}>{net === 'testnet' ? 'TESTNET' : 'MAINNET'}</span>
        {/* Admin sees the plan economics; everyone else just the codename. The name comes
            from useStreamDisplay so no raw stream key ships as a visible literal. */}
        <span className="livex__badge">{sd.isAdmin
          ? `${sd.name('d30so8f3h7')} · +${CAP_R}R · %${Math.round(SO.closeFrac * 100)} TP1 ·0.5R`
          : sd.name('d30so8f3h7')}</span>
        <span className="livex__upd">{updatedAt ? `${t('Güncellendi')}: ${ago(account?.updated_at, t)}` : ''}</span>
        <button className="livex__refresh" onClick={load} title={t('Yenile')}>⟳</button>
      </div>

      {stale && (
        <div className="livex__warn">{t('Snapshot 5 dk’dan eski — executor cron çalışmıyor olabilir.')}</div>
      )}
      {err && <div className="livex__err">{err}</div>}

      {/* account header */}
      <div className="livex__kpis">
        <div className="livex__kpi"><span>{t('Cüzdan')}</span><b>{fmtUsd(account?.wallet_balance)}</b></div>
        <div className="livex__kpi"><span>{t('Kullanılabilir')}</span><b>{fmtUsd(account?.available_balance)}</b></div>
        <div className="livex__kpi">
          <span>{t('Açık uPnL')}</span>
          <b className={Number(account?.total_unrealized) >= 0 ? 'pos' : 'neg'}>{fmtUsd(account?.total_unrealized)}</b>
        </div>
        <div className="livex__kpi"><span>{t('Açık Pozisyon')}</span><b>{open.length}</b></div>
        <div className="livex__kpi">
          <span>{t('Funding (açık)')}</span>
          <b className={openFunding >= 0 ? 'pos' : 'neg'}>{open.length ? fmtUsdSigned(openFunding) : '—'}</b>
        </div>
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
                <th>{t('Giriş')}</th><th>{t('Mark')}</th><th>SL</th><th>TP1</th><th>{capLabel}</th>
                <th>{t('Miktar')}</th><th>{t('Canlı K/Z')}</th><th>{t('Canlı R')}</th><th>Funding</th><th>{t('Geri Sayım')}</th>
              </tr>
            </thead>
            <tbody>
              {open.map((p) => {
                const s = snaps[p.symbol];
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
                    <td className="mono" data-label={t('Mark')}>{fmtPx(s?.mark_price)}</td>
                    <td className="mono dim" data-label="SL">{fmtPx(p.signal_sl)}</td>
                    <td className="mono dim" data-label="TP1">
                      {fmtPx(p.eff_tp1)}
                      {lc && <span className="livex__sub pos">{fmtUsdSigned(lc.tp1Usd)} {t('al')}</span>}
                    </td>
                    <td className="mono dim" data-label={capLabel}>
                      {fmtPx(p.signal_cap)}
                      {lc && <span className="livex__sub pos">{fmtUsdSigned(lc.capUsd)} {t('toplam')}</span>}
                    </td>
                    <td className="mono" data-label={t('Miktar')}>{p.qty ?? '—'}</td>
                    <td className={`mono ${Number(lc?.totalUsd) >= 0 ? 'pos' : 'neg'}`} data-label={t('Canlı K/Z')}>
                      {fmtUsd(lc?.totalUsd)}
                      {lc?.isRunner && (
                        <span className="livex__sub livex__lock">🔒 {fmtUsdSigned(lc.bookedUsd)} {t('alındı')}</span>
                      )}
                    </td>
                    <td className={`mono ${Number(lc?.totalR) >= 0 ? 'pos' : 'neg'}`} data-label={t('Canlı R')}>
                      {fmtR(lc?.totalR)}
                      {lc?.isRunner && (
                        <span className="livex__sub livex__lock">🔒 {fmtR(lc.bookedR)} {t('kilitli')}</span>
                      )}
                    </td>
                    <td className={`mono ${Number(s?.funding_fee) > 0 ? 'pos' : Number(s?.funding_fee) < 0 ? 'neg' : 'dim'}`} data-label="Funding">
                      {s?.funding_fee == null ? '—' : fmtUsdSigned(s.funding_fee)}
                    </td>
                    <td className="mono dim" data-label={t('Geri Sayım')}>{cd || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
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
                  return (
                    <tr key={p.id}>
                      <td className="mono livex__cardhead" data-label={t('Sembol')}>{p.symbol}</td>
                      <td data-label={t('Yön')}><span className={lng ? 'dir dir--long' : 'dir dir--short'}>{lng ? 'LONG' : 'SHORT'}</span></td>
                      <td data-label={t('Sonuç')}><span className={`st ${win ? 'st-done' : 'st-sl'}`}>{exitLabel(p.exit_reason)}</span></td>
                      <td className={`mono ${win ? 'pos' : 'neg'}`} data-label="R">{fmtR(p.realized_r)}</td>
                      <td className={`mono ${win ? 'pos' : 'neg'}`} data-label={t('USD')}>{fmtUsd(p.realized_usd)}</td>
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
