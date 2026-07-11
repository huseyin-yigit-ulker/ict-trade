import { useCallback, useEffect, useRef, useState } from 'react';
import { authedFetch } from './supa';

// Kullanıcı modu canlı-işlem verisi — LivePositionsPage'in fetch/hesap mantığının
// İKİ AĞI BİRLEŞTİREN hook hali (admin sayfası ağ-başına ayrı pano ister, kullanıcı
// tek "Portföy" görür). RLS satırları oturumdaki kullanıcıya kilitler; burada ağ
// filtresi YOK — kullanıcının mainnet + testnet her şeyi tek listede toplanır.
//   live_positions        — OPUS scale-out pozisyonları (mainnet)
//   talos_ichi_positions  — altın mainnet (TALOS-ICHI-X, iz-süren)
//   midas_positions       — altın testnet/paper (MIDAS-X, iz-süren)
//   live_account(+snapshot) — cüzdan / uPnL / sembol-başına mark
// Sabitler ve R-matematiği LivePositionsPage ile AYNI kalmalı (kaynağı orası).

export const OPEN_STATES = ['PENDING_ENTRY', 'ENTRY_WORKING', 'OPEN_FULL', 'RUNNER', 'CLOSING'];
export const GOLD_OPEN_STATES = ['PENDING_ENTRY', 'ENTRY_WORKING', 'OPEN'];
const REFRESH_MS = 30000;
export const CAP_R = 8;   // .env RUNNER_CAP_R ile senkron (LivePositionsPage.CAP_R)

export const STATE_BADGE = {
  PENDING_ENTRY: { label: 'GİRİŞ BEKLİYOR', cls: 'st-wait' },
  ENTRY_WORKING: { label: 'GİRİŞ EMRİ', cls: 'st-wait' },
  OPEN_FULL: { label: 'AÇIK', cls: 'st-active' },
  RUNNER: { label: 'RUNNER', cls: 'st-runner' },
  CLOSING: { label: 'KAPANIYOR', cls: 'st-active' },
  CLOSED: { label: 'KAPANDI', cls: 'st-done' },
  CANCELLED: { label: 'İPTAL', cls: 'st-cancel' },
};
export const GOLD_BADGE = {
  PENDING_ENTRY: { label: 'GİRİŞ BEKLİYOR', cls: 'st-wait' },
  ENTRY_WORKING: { label: 'GİRİŞ EMRİ', cls: 'st-wait' },
  OPEN: { label: 'AÇIK · İZ-SÜREN', cls: 'st-active' },
};
// Çıkış etiketleri — 'cap' KULLANICIYA MASKELİ verilmeli (R ekonomisi admin-only);
// PositionCard exitLabel() çağırırken maskeyi kendisi uygular.
export const EXIT_LABEL = {
  sl: 'Stop', tp1_be: 'TP1+BE', breakeven: 'Breakeven', cap: 'Hedef',
  time_stop: 'Zaman', entry_expired: 'Giriş Dolmadı', reversed: 'Ters Döndü', killswitch: 'Acil Kapama',
};
export const GOLD_EXIT = {
  'trail/stop': 'İz-Süren Stop', time: 'Zaman', session: 'Seans Sonu',
  slipped: 'Fiyat Kaçtı', unfilled: 'Dolmadı', closed_externally: 'Borsa Kapanışı', killswitch: 'Acil Kapama',
};

export const fmtPx = (v) => {
  if (v == null) return '—';
  const n = Number(v);
  return n >= 1000 ? n.toLocaleString('en-US', { maximumFractionDigits: 2 })
    : n.toLocaleString('en-US', { maximumFractionDigits: n >= 1 ? 4 : 6 });
};
export const fmtUsd = (v) => (v == null ? '—' : `$${Number(v).toFixed(2)}`);
export const fmtUsdSigned = (v) => (v == null ? '—' : `${Number(v) >= 0 ? '+' : '−'}$${Math.abs(Number(v)).toFixed(2)}`);
export const fmtR = (v) => (v == null ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}R`);

export function ago(iso, t) {
  if (!iso) return '—';
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s} ${t('sn önce')}`;
  if (s < 3600) return `${Math.floor(s / 60)} ${t('dk önce')}`;
  if (s < 86400) return `${Math.floor(s / 3600)} ${t('sa önce')}`;
  return `${Math.floor(s / 86400)} ${t('gün önce')}`;
}
export function countdown(iso, t) {
  if (!iso) return null;
  const s = Math.floor((new Date(iso).getTime() - Date.now()) / 1000);
  if (s <= 0) return t('doldu');
  if (s < 3600) return `${Math.floor(s / 60)}dk`;
  const h = Math.floor(s / 3600);
  return h < 24 ? `${h}sa ${Math.floor((s % 3600) / 60)}dk` : `${Math.floor(h / 24)}g ${h % 24}sa`;
}

// Scale-out planı (LivePositionsPage SO/CAP_R_TOTAL ile birebir).
const SO = { closeFrac: 0.3, firstR: 1.0, confirmBuf: 0.5, capR: CAP_R };
const CAP_R_TOTAL = SO.closeFrac * SO.firstR + (1 - SO.closeFrac) * ((SO.capR - SO.confirmBuf) / (1 + SO.confirmBuf));

/** OPUS scale-out canlı R/USD dökümü — executor R-konvansiyonunun aynası. */
export const liveCalc = (p, snap) => {
  const sl = Number(p.signal_sl);
  const qty = Number(p.qty) || 0;
  const risk0 = Math.abs(Number(p.signal_entry) - sl);
  const riskEff = p.eff_entry != null ? Math.abs(Number(p.eff_entry) - sl) : (1 + SO.confirmBuf) * risk0;
  const oneRusd = riskEff * qty;
  if (!oneRusd) return null;
  const isRunner = p.state === 'RUNNER';
  const bookedR = isRunner ? SO.closeFrac * SO.firstR : 0;
  const bookedUsd = bookedR * oneRusd;
  const runnerUsd = snap && snap.unrealized_pnl != null ? Number(snap.unrealized_pnl) : null;
  const totalUsd = runnerUsd == null ? null : bookedUsd + runnerUsd;
  const totalR = totalUsd == null ? (isRunner ? bookedR : null) : totalUsd / oneRusd;
  return {
    oneRusd, isRunner, bookedR, bookedUsd, runnerUsd, totalUsd, totalR,
    tp1Usd: SO.closeFrac * SO.firstR * oneRusd,
    capUsd: CAP_R_TOTAL * oneRusd,
  };
};

/** Altın iz-süren canlı R — tek pozisyon, risk0=|entry−sl|, kilitli R dahil. */
export const goldCalc = (p, snap) => {
  const qty = Number(p.qty) || 0;
  const risk0 = Number(p.risk0) || Math.abs(Number(p.signal_entry) - Number(p.signal_sl));
  const oneR = risk0 * qty;
  const upnl = snap && snap.unrealized_pnl != null ? Number(snap.unrealized_pnl) : null;
  return {
    upnl,
    liveR: upnl == null || !oneR ? null : upnl / oneR,
    lockedR: p.locked_r != null ? Number(p.locked_r) : null,
    // LivePositionModal'ın beklediği shape (LivePositionsPage'teki gold seçimiyle aynı):
    totalUsd: upnl, totalR: upnl == null || !oneR ? null : upnl / oneR,
  };
};

async function getJSON(path) {
  const res = await authedFetch(path);
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/**
 * Kullanıcının TÜM canlı-işlem verisi (iki ağ birleşik, RLS kullanıcıya kilitli).
 * open/closed öğeleri { ...row, isGold } taşır; snapFor(pos) doğru ağın snapshot'ını verir.
 */
export function useLiveExec() {
  const [positions, setPositions] = useState([]);
  const [gold, setGold] = useState([]);
  const [snaps, setSnaps] = useState({});          // `${network}|${symbol}` → snapshot satırı
  const [accounts, setAccounts] = useState([]);    // live_account satırları (ağ başına 1)
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [updatedAt, setUpdatedAt] = useState(null);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const [pos, snap, acc, gMain, gPaper] = await Promise.all([
        getJSON('live_positions?select=*&order=updated_at.desc&limit=60').catch(() => []),
        getJSON('live_account_snapshot?select=*').catch(() => []),
        getJSON('live_account?select=*').catch(() => []),
        getJSON('talos_ichi_positions?select=*&order=updated_at.desc&limit=20').catch(() => []),
        getJSON('midas_positions?select=*&order=updated_at.desc&limit=20').catch(() => []),
      ]);
      setPositions(pos);
      setGold([...gMain, ...gPaper]);
      setSnaps(Object.fromEntries(snap.map((s) => [`${s.network}|${s.symbol}`, s])));
      setAccounts(acc);
      setErr('');
      setUpdatedAt(new Date());
    } catch (e) {
      setErr(e.message || 'fetch');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    timer.current = setInterval(load, REFRESH_MS);
    const onVisible = () => { if (document.visibilityState === 'visible') load(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer.current);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [load]);

  const snapFor = useCallback(
    (p) => snaps[`${p.network}|${p.symbol}`],
    [snaps],
  );
  const calcFor = useCallback(
    (p) => (p.isGold ? goldCalc(p, snapFor(p)) : liveCalc(p, snapFor(p))),
    [snapFor],
  );

  const tagged = [
    ...positions.map((p) => ({ ...p, isGold: false })),
    ...gold.map((p) => ({ ...p, isGold: true })),
  ];
  const openOf = (p) => (p.isGold ? GOLD_OPEN_STATES : OPEN_STATES).includes(p.state);
  const open = tagged.filter(openOf)
    .sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0));
  const closed = tagged.filter((p) => p.state === 'CLOSED' || p.state === 'CANCELLED')
    .sort((a, b) => new Date(b.exit_time || b.updated_at || 0) - new Date(a.exit_time || a.updated_at || 0));

  // Toplamlar — live_account tüm ağların satırlarını taşır (kullanıcının kaç ağı varsa).
  const totalWallet = accounts.length ? accounts.reduce((a, r) => a + (Number(r.wallet_balance) || 0), 0) : null;
  const totalUpnl = accounts.length ? accounts.reduce((a, r) => a + (Number(r.total_unrealized) || 0), 0) : null;

  return {
    loading, err, refresh: load, updatedAt,
    accounts, open, closed, snaps, snapFor, calcFor,
    totalWallet, totalUpnl,
  };
}
