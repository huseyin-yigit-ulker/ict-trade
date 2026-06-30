import { useEffect, useMemo, useState } from 'react';
import { useTradeContext, isHalfFor } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { scaleOutLiveR, isScaleOutStrategy, soCapFromStrategy, isConfirmStrategy, soBookFromStrategy } from '../utils/liveR';
import Sparkline from './viz/Sparkline';
import PusuLogo from './PusuLogo';
import StrategyIntro from './StrategyIntro';
import MidasLiveChart from './MidasLiveChart';

// Click-to-copy price value — copies the RAW value (full precision, ready to
// paste into an order ticket) and flashes a ✓. Stops propagation so the card's
// own click (open chart) doesn't fire.
const CopyVal = ({ value, className = '', title, children }) => {
  const [copied, setCopied] = useState(false);
  const copy = (e) => {
    e.stopPropagation();
    if (value == null || !navigator.clipboard) return;
    navigator.clipboard.writeText(String(value)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1100);
    }).catch(() => { /* clipboard denied — ignore */ });
  };
  return (
    <button type="button" className={`copy-val ${className}${copied ? ' copied' : ''}`} onClick={copy} title={title}>
      {children}
      <span className="copy-val__tick" aria-hidden="true">✓</span>
    </button>
  );
};

// Tiny TP-vs-SL ratio bar for day/group headers — instant win/loss read.
const WinLossBar = ({ tp, sl }) => {
  const total = tp + sl;
  if (!total) return null;
  return (
    <span className="wl-bar" title={`TP ${tp} · SL ${sl}`}>
      <span className="wl-bar__tp" style={{ width: `${(tp / total) * 100}%` }} />
    </span>
  );
};

// Stride-sample a long series down to ~max points so a several-thousand-trade
// bucket doesn't collapse into an unreadable smear in a tiny sparkline.
const downsample = (arr, max = 60) => {
  if (arr.length <= max) return arr;
  const out = [];
  const step = arr.length / max;
  for (let i = 0; i < max; i++) out.push(arr[Math.floor(i * step)]);
  out.push(arr[arr.length - 1]);
  return out;
};

// Time-ascending cumulative-R series for a list of signals (uses caller's pnl fn).
const cumulativeR = (list, pnl) => {
  const asc = [...list].sort((a, b) => a.dateObj - b.dateObj);
  let c = 0;
  return asc.map((s) => (c += Number(pnl(s)) || 0));
};

// 5-bin R distribution — losses, 0–1, 1–2, 2–4, 4+. Zero/non-finite (unfilled) ignored.
const rHistogram = (rs) => {
  const bins = [0, 0, 0, 0, 0];
  rs.forEach((r) => {
    if (!Number.isFinite(r) || r === 0) return;
    if (r < 0) bins[0] += 1;
    else if (r < 1) bins[1] += 1;
    else if (r < 2) bins[2] += 1;
    else if (r < 4) bins[3] += 1;
    else bins[4] += 1;
  });
  return bins;
};

// Dynamic decimal precision: small-cap tokens (PEPE, SHIB, ...) have many
// significant digits below the decimal — `toFixed(4)` would round them to 0.
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

// Risk-reward ratio from entry/SL/TP (pre-trade, what the engine targeted). `entry` defaults to the
// signal entry but the card passes the realistic +0.5R entry in live (TP/SL fixed → R:R collapses).
const computeRR = (sig, entry = sig?.entry) => {
  if (!entry || !sig?.sl || !sig?.tp) return null;
  const risk = Math.abs(entry - sig.sl);
  const reward = Math.abs(sig.tp - entry);
  if (risk === 0) return null;
  return reward / risk;
};

// Risk % and reward % relative to entry price.
const pctDist = (a, b) => {
  if (!a || !b) return null;
  return ((b - a) / a) * 100;
};

// Compact status display for live trades — short label + colored icon.
// Each variant has its own dot color so the dashboard reads at-a-glance.
const LIVE_STATUS_DISPLAY = {
  'TP Oldu':                      { label: 'TP',       icon: '●', cls: 'st-tp' },
  'SL Oldu':                      { label: 'SL',       icon: '●', cls: 'st-sl' },
  'BE Oldu':                      { label: 'BE',       icon: '●', cls: 'st-tp' },     // ½TP: breakeven close, partial banked
  'TP/SL Aynı Mum':               { label: 'TP+SL',    icon: '●', cls: 'st-mixed' },
  'İşlem Aktif (Entry Geldi)':    { label: 'AKTİF',    icon: '●', cls: 'st-active' },
  'İşlem Aktif (Kısmi ½TP Alındı)': { label: '½TP·BE',  icon: '●', cls: 'st-active' }, // ½TP: 50% out, stop at entry
  'İşlem Aktif (+1R Alındı · Runner)': { label: 'AKTİF·+1R', icon: '●', cls: 'st-active' }, // scale-out: 60% booked, runner rides
  'İptal (Entry Gelmeden TP/SL)': { label: 'İPTAL',    icon: '●', cls: 'st-cancel' },
  'İptal (Süre Doldu)':           { label: 'İPTAL',    icon: '●', cls: 'st-cancel' },
  'İptal (Ters Yön)':             { label: 'İPTAL·YÖN', icon: '●', cls: 'st-cancel' }, // dir-confirm: opened toward SL -> skipped
  'Sinyal Bekliyor':              { label: 'BEKLİYOR', icon: '●', cls: 'st-wait' },
};
const liveStatusDisplay = (s) => LIVE_STATUS_DISPLAY[s] || LIVE_STATUS_DISPLAY['Sinyal Bekliyor'];

// signal_time in DB is the OPEN of the trigger bar; the signal actually
// fires at bar CLOSE (engine runs after the bar closes). Shift the
// "effective signal time" forward by the LTF duration so all UI labels
// (Tarih, Süre, "X dk önce") reflect the real emission moment.
const intervalMs = (tf) => {
  const m = String(tf || '1h').match(/^(\d+)([smhd])$/i);
  if (!m) return 60 * 60 * 1000;
  const u = { s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000 };
  return Number(m[1]) * (u[m[2].toLowerCase()] || 0);
};
const effectiveSignalTime = (sig) => {
  if (!sig?.dateObj) return null;
  return new Date(sig.dateObj.getTime() + intervalMs(sig.ltfTimeframe));
};

// "5 dk önce" / "2 sa 14 dk" / "3 gün önce" — relative time label.
const timeAgo = (date, t) => {
  if (!(date instanceof Date)) return '--';
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return t('şimdi');
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1)  return t('az önce');
  if (mins < 60) return t('{n} dk önce', { n: mins });
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return t('{h} sa {m} dk', { h: hrs, m: mins % 60 });
  const days = Math.floor(hrs / 24);
  return t('{d} gün {h} sa', { d: days, h: hrs % 24 });
};

// Compute the realised R-multiple for a live trade outcome from its
// entry/tp/sl. Replaces the hard-coded "2R for TP" assumption.
// ½TP modules (half=true): 50% banked at half distance (¼ RR) + 50% to TP
// (½ RR) → TP = 0.75×RR; a breakeven close keeps only the banked ¼ RR.
// Scale-out (so=true): 60% booked at +1R, 40% runner CAPPED at +4R (==signal TP) with a 3-day
// time-exit. BE close = 0.60×(+1R) + 0.40×0; runner to +4R cap = 0.60×1 + 0.40×4 = 2.2R; a -1R
// stop before +1R = full -1R. Fees (0.1% round-trip, in R) are subtracted so the live R matches
// the backtest resolver. The rare 3-day mark-to-market tail is resolved by the nightly sync.
const liveOutcomeR = (sig, status, half = false, so = false, capR = 4, conservative = true, bookFrac = 0.6) => {
  if (!sig?.entry || !sig?.tp || !sig?.sl) return 0;
  if (so) {   // scale-out: delegate to the shared model so the list matches the chart panel exactly
    const r = scaleOutLiveR(sig.entry, sig.sl, status, capR, conservative, bookFrac);
    return r == null ? 0 : r;
  }
  const risk = Math.abs(sig.entry - sig.sl);
  if (risk === 0) return 0;
  const rr = Math.abs(sig.tp - sig.entry) / risk;
  if (status === 'TP Oldu') return half ? 0.75 * rr : rr;
  if (status === 'BE Oldu') return half ? 0.25 * rr : 0;
  if (status === 'SL Oldu' || status === 'TP/SL Aynı Mum') return -1;
  return 0;
};

const Dashboard = () => {
  const {
    filteredSignals,
    setActiveSignal,
    setChartView,
    mode,
    liveStatuses,
    statusFilter,
    isLoaded,
    liveError,
    strategy,
  } = useTradeContext();
  const { t, locale } = useLang();
  // ½TP per signal — *_half modules always; karma decides per SYMBOL (KARMA_MAP).
  const halfFor = (sig) => isHalfFor(strategy, sig?.symbol);
  // Scale-out streams (d30_4h_so + the ·0.5R twins d30_4h_soc / d30so{N}c): 60% booked at +1R +
  // breakeven runner — shared live R model (matches the chart panel). cap & conservative from the tag.
  const isSO = isScaleOutStrategy(strategy);
  const soCapR = soCapFromStrategy(strategy);
  const soConservative = isConfirmStrategy(strategy);
  const soBookFrac = soBookFromStrategy(strategy);
  // MIDAS (trailing-stop, no fixed TP/SL R:R): cards show Entry + Exit + the realised result only —
  // no R:R pill, no Hedef/Risk row, no risk/reward bar (those imply a fixed target that doesn't exist).
  const isTrailing = strategy === 'midas';

  // Shimmer placeholders while the first fetch is in flight — prevents the
  // misleading "Sinyal yok." flash before data arrives.
  const renderSkeleton = () => (
    <div className="skeleton-grid" aria-hidden="true">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="skeleton-card">
          <div className="skeleton-line w40" />
          <div className="skeleton-line w70" />
          <div className="skeleton-line w55" />
          <div className="skeleton-line w85" />
        </div>
      ))}
    </div>
  );

  // Data-source failures (Supabase config / fetch errors) were previously
  // swallowed — the shell never showed them. Surface them inline.
  const renderError = () => liveError ? (
    <div className="dash-error" role="alert">⚠ {t(liveError)}</div>
  ) : null;

  // Status filter (statusFilter from context; chips live in the Topbar). Maps each
  // trade to tp/sl/cancelled/open/active so the same control filters either source.
  const statusOf = (sig) => {
    if (mode === 'live') {
      const s = liveStatuses[sig.id]?.status || '';
      if (s === 'TP Oldu' || s === 'BE Oldu') return 'tp';   // BE = small ½TP winner (banked partial)
      if (s === 'SL Oldu' || s === 'TP/SL Aynı Mum') return 'sl';
      if (s.startsWith('İptal')) return 'cancelled';
      if (s.startsWith('İşlem Aktif')) return 'active'; // entry filled, position open (incl. ½TP BE mode)
      return 'open';
    }
    if (sig.status === 'TP') return 'tp';
    if (sig.status === 'SL') return 'sl';
    return 'cancelled'; // backtest WAITING = entry never filled → cancelled
  };
  const matchesStatus = (sig) => statusFilter === 'all' || statusOf(sig) === statusFilter;

  const calculatePnL = (sig) => {
    if (Number.isFinite(sig?.pnlR)) return sig.pnlR;
    if (sig.status !== 'TP' && sig.status !== 'SL') return 0;
    const diff = sig.dir === 'LONG' ? (sig.exitPrice - sig.entry) : (sig.entry - sig.exitPrice);
    return (diff / sig.entry) * 100;
  };

  const formatBacktestPnl = (sig, pnl) => (
    Number.isFinite(sig?.pnlR) ? `${pnl.toFixed(2)}R` : `${pnl.toFixed(2)}%`
  );

  const resolveLiveMeta = (status) => {
    if (!status) return { label: 'BEKLEMEDE', cls: 'waiting', terminal: false };
    if (status === 'TP Oldu') return { label: 'TP', cls: 'win', terminal: true };
    if (status === 'BE Oldu') return { label: 'BE', cls: 'win', terminal: true };   // ½TP breakeven close
    if (status === 'SL Oldu') return { label: 'SL', cls: 'loss', terminal: true };
    if (status === 'TP/SL Aynı Mum') return { label: 'TP/SL', cls: 'loss', terminal: true };
    if (status.startsWith('İptal')) return { label: 'İPTAL', cls: 'waiting', terminal: true };
    if (status === 'İşlem Aktif (Kısmi ½TP Alındı)') return { label: '½TP·BE', cls: 'win', terminal: false };
    if (status === 'İşlem Aktif (+1R Alındı · Runner)') return { label: 'AKTİF·+1R', cls: 'win', terminal: false };
    if (status.startsWith('İşlem Aktif')) return { label: 'AKTIF', cls: 'waiting', terminal: false };
    return { label: 'BEKLEMEDE', cls: 'waiting', terminal: false };
  };

  const formatLiveDelta = (sig, lastPrice, entry = sig?.entry) => {
    if (!entry || typeof lastPrice !== 'number') return '--';
    const diff = sig.dir === 'LONG' ? (lastPrice - entry) : (entry - lastPrice);
    const pct = (diff / entry) * 100;
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
  };

  const formatLivePrice = (value) => formatPrice(value);

  // Live INSTANTANEOUS R for a scale-out trade that has booked TP1 and is riding the runner:
  // the +0.6R secured floor PLUS the runner's current unrealised contribution (40% of its gain in
  // R, clamped to [0, cap] — stop is at breakeven, ceiling at the +cap). lastPrice is the latest
  // live mark; without it (or pre-TP1) we fall back to the secured floor. R is in the same risk_eff
  // convention as scaleOutLiveR (the +1R first target and the cap are of the effective/·0.5R risk).
  const liveRunnerR = (sig, lastPrice) => {
    const floor = liveOutcomeR(sig, 'BE Oldu', false, true, soCapR, soConservative, soBookFrac);  // 0.6 − fee
    if (!isSO || !Number.isFinite(lastPrice) || !sig?.entry || !sig?.sl) return floor;
    const risk0 = Math.abs(sig.entry - sig.sl);
    if (!risk0) return floor;
    const buf = soConservative ? 0.5 : 0;
    const effEntry = sig.dir === 'LONG' ? sig.entry + buf * risk0 : sig.entry - buf * risk0;
    const riskEff = (1 + buf) * risk0;
    const capRunnerR = soConservative ? (soCapR - 0.5) / 1.5 : soCapR;               // runner cap, in R
    const cur = (sig.dir === 'LONG' ? lastPrice - effEntry : effEntry - lastPrice) / riskEff;
    const runnerNow = Math.min(capRunnerR, Math.max(0, cur));                         // BE floor ↔ cap ceiling
    return floor + 0.4 * runnerNow;                                                   // 0.6 + 0.4×runner − fee
  };

  const getLiveRLabel = (sig, status, lastPrice = null) => {
    if (!status) return { label: '--', cls: 'waiting' };
    if (status === 'TP Oldu' || status === 'BE Oldu') {
      const r = liveOutcomeR(sig, status, halfFor(sig), isSO, soCapR, soConservative, soBookFrac);
      return { label: `${r >= 0 ? '+' : ''}${r.toFixed(2)}R`, cls: r >= 0 ? 'win' : 'loss' };
    }
    if (status === 'SL Oldu' || status === 'TP/SL Aynı Mum') {
      if (isSO) return { label: `${liveOutcomeR(sig, status, false, true, soCapR, soConservative, soBookFrac).toFixed(2)}R`, cls: 'loss' };
      return { label: '-1R', cls: 'loss' };
    }
    if (status === 'İşlem Aktif (Kısmi ½TP Alındı)') {
      // partial banked (¼ RR), remainder risk-free at BE — show the floor.
      const banked = liveOutcomeR(sig, 'BE Oldu', true);
      return { label: `≥+${banked.toFixed(2)}R`, cls: 'win' };
    }
    if (status === 'İşlem Aktif (+1R Alındı · Runner)') {
      // scale-out TP1 booked: show the LIVE total R (floor +0.6R + the runner's current gain). When
      // the runner hasn't moved past breakeven yet, fall back to the secured floor with a ≥.
      const floor = liveOutcomeR(sig, 'BE Oldu', false, true, soCapR, soConservative, soBookFrac);
      const r = liveRunnerR(sig, lastPrice);
      return r > floor + 1e-9
        ? { label: `+${r.toFixed(2)}R`, cls: 'win' }
        : { label: `≥+${floor.toFixed(2)}R`, cls: 'win' };
    }
    if (status.startsWith('İptal')) return { label: '0', cls: 'waiting' };
    return { label: '--', cls: 'waiting' };
  };

  // Sum the realised R across live trades, computed from each signal's actual
  // RR (not a hard-coded 2R like before).
  const summarizeLiveCounts = (list) => {
    let tp = 0;
    let sl = 0;
    let rScore = 0;
    list.forEach((sig) => {
      const status = liveStatuses[sig.id]?.status;
      const meta = resolveLiveMeta(status);
      if (meta.label === 'TP' || meta.label === 'BE') {
        tp += 1;
        rScore += liveOutcomeR(sig, status, halfFor(sig), isSO, soCapR, soConservative, soBookFrac);
      } else if (meta.label === 'SL' || meta.label === 'TP/SL') {
        sl += 1;
        rScore += liveOutcomeR(sig, status, halfFor(sig), isSO, soCapR, soConservative, soBookFrac);   // -1 (−1−fee for scale-out)
      }
    });
    return { tp, sl, rScore };
  };

  // Scale-out only: aggregate the trades that REACHED TP1 (booked 60% at +1R) — every active
  // runner plus the terminal TP/BE closes; an SL before +1R is excluded. Returns the count and
  // the summed live R (instantaneous floor+runner for actives, realised R for terminals).
  const summarizeTp1 = (list) => {
    let count = 0;
    let sumR = 0;
    list.forEach((sig) => {
      const st = liveStatuses[sig.id]?.status;
      if (st === 'İşlem Aktif (+1R Alındı · Runner)') {
        count += 1;
        sumR += liveRunnerR(sig, liveStatuses[sig.id]?.lastPrice);
      } else if (st === 'TP Oldu' || st === 'BE Oldu') {
        count += 1;
        sumR += liveOutcomeR(sig, st, halfFor(sig), isSO, soCapR, soConservative, soBookFrac);
      }
    });
    return { count, sumR };
  };

  const summarizeBacktestCounts = (list) => {
    let tp = 0;
    let sl = 0;
    list.forEach((sig) => {
      if (sig.status === 'TP') tp += 1;
      else if (sig.status === 'SL') sl += 1;
    });
    return { tp, sl, rScore: (2 * tp) - sl };
  };

  const getTotalR = (list) => list.reduce((sum, s) => sum + (Number.isFinite(s?.pnlR) ? s.pnlR : calculatePnL(s)), 0);

  // All dashboard dates/times are in UTC (the data's native zone — same as the chart), so the
  // cards never disagree with the chart's "Sinyal (UTC)". Day/month/year buckets use UTC too.
  const formatLocalIso = (date) => {
    const y = date.getUTCFullYear();
    const m = String(date.getUTCMonth() + 1).padStart(2, '0');
    const d = String(date.getUTCDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  };

  const parseIsoDate = (isoString) => {
    const [year, month, day] = isoString.split('-').map(Number);
    return new Date(Date.UTC(year, month - 1, day));
  };

  // Live görünümü için mevcut günlük grup. Gruplama, kartta gösterilen gerçek
  // sinyal anına (bar KAPANIŞI) göre yapılır — bar AÇILIŞI ile gruplanırsa
  // 23:00 açılışlı bir bar 00:00'da yayınlanan sinyalini önceki güne koyar.
  const groupedLive = useMemo(() => {
    if (mode !== 'live') return {};
    return filteredSignals.reduce((acc, sig) => {
      const effDate = effectiveSignalTime(sig) || sig.dateObj;
      const dateKey = effDate.toLocaleDateString(locale, {
        timeZone: 'UTC', year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'
      });
      if (!acc[dateKey]) acc[dateKey] = [];
      acc[dateKey].push(sig);
      return acc;
    }, {});
  }, [filteredSignals, mode, locale]);

  // Backtest hiyerarşik veri seti
  const backtestSignals = useMemo(() => {
    if (mode !== 'backtest') return [];
    return [...filteredSignals].sort((a, b) => b.dateObj - a.dateObj);
  }, [mode, filteredSignals]);

  const yearBuckets = useMemo(() => {
    const byYear = backtestSignals.reduce((acc, sig) => {
      const year = sig.dateObj.getUTCFullYear();
      if (!acc[year]) acc[year] = [];
      acc[year].push(sig);
      return acc;
    }, {});

    return Object.entries(byYear)
      .map(([year, list]) => {
        const counts = summarizeBacktestCounts(list);
        const totalR = getTotalR(list);
        return {
          year: Number(year),
          list,
          count: list.length,
          tp: counts.tp,
          sl: counts.sl,
          totalR
        };
      })
      .sort((a, b) => b.year - a.year);
  }, [backtestSignals]);

  const [selectedYear, setSelectedYear] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [selectedDay, setSelectedDay] = useState('');

  useEffect(() => {
    if (mode !== 'backtest') {
      setSelectedYear(null);
      setSelectedMonth('');
      setSelectedDay('');
      return;
    }
    if (selectedYear !== null && !yearBuckets.some((y) => y.year === selectedYear)) {
      setSelectedYear(null);
      setSelectedMonth('');
      setSelectedDay('');
    }
  }, [mode, selectedYear, yearBuckets]);

  const monthBuckets = useMemo(() => {
    if (!selectedYear) return [];
    const yearData = yearBuckets.find((y) => y.year === selectedYear);
    const list = yearData?.list || [];

    const byMonth = list.reduce((acc, sig) => {
      const monthKey = `${sig.dateObj.getUTCFullYear()}-${String(sig.dateObj.getUTCMonth() + 1).padStart(2, '0')}`;
      if (!acc[monthKey]) acc[monthKey] = [];
      acc[monthKey].push(sig);
      return acc;
    }, {});

    return Object.entries(byMonth)
      .map(([monthKey, monthList]) => {
        const counts = summarizeBacktestCounts(monthList);
        const totalR = getTotalR(monthList);
        const label = parseIsoDate(`${monthKey}-01`).toLocaleDateString(locale, { timeZone: 'UTC', month: 'long', year: 'numeric' });
        return {
          monthKey,
          label,
          list: monthList,
          count: monthList.length,
          tp: counts.tp,
          sl: counts.sl,
          totalR
        };
      })
      .sort((a, b) => b.monthKey.localeCompare(a.monthKey));
  }, [selectedYear, yearBuckets, locale]);

  useEffect(() => {
    if (!selectedMonth) return;
    if (!monthBuckets.some((m) => m.monthKey === selectedMonth)) {
      setSelectedMonth('');
      setSelectedDay('');
    }
  }, [selectedMonth, monthBuckets]);

  const dayBuckets = useMemo(() => {
    if (!selectedMonth) return [];
    const monthData = monthBuckets.find((m) => m.monthKey === selectedMonth);
    const list = monthData?.list || [];

    const byDay = list.reduce((acc, sig) => {
      const dayKey = formatLocalIso(sig.dateObj);
      if (!acc[dayKey]) acc[dayKey] = [];
      acc[dayKey].push(sig);
      return acc;
    }, {});

    return Object.entries(byDay)
      .map(([dayKey, dayList]) => {
        const counts = summarizeBacktestCounts(dayList);
        const totalR = getTotalR(dayList);
        const label = parseIsoDate(dayKey).toLocaleDateString(locale, { timeZone: 'UTC', weekday: 'short', day: '2-digit', month: 'short' });
        return {
          dayKey,
          label,
          list: dayList,
          count: dayList.length,
          tp: counts.tp,
          sl: counts.sl,
          totalR
        };
      })
      .sort((a, b) => b.dayKey.localeCompare(a.dayKey));
  }, [selectedMonth, monthBuckets, locale]);

  useEffect(() => {
    if (!selectedMonth) return;
    if (dayBuckets.length === 0) {
      setSelectedDay('');
      return;
    }
    if (!selectedDay || !dayBuckets.some((d) => d.dayKey === selectedDay)) {
      setSelectedDay(dayBuckets[0].dayKey);
    }
  }, [selectedMonth, selectedDay, dayBuckets]);

  const selectedDayTrades = useMemo(() => {
    if (!selectedDay) return [];
    return dayBuckets.find((d) => d.dayKey === selectedDay)?.list || [];
  }, [selectedDay, dayBuckets]);

  const selectedDayLabel = useMemo(() => {
    if (!selectedDay) return '';
    return parseIsoDate(selectedDay).toLocaleDateString(locale, {
      timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });
  }, [selectedDay, locale]);

  // Always-visible "edge cockpit" strip. Backtest pulls authoritative numbers
  // from the SQL summary RPC; live derives them from the per-signal live status.
  // Deliberately NO win-rate ring — a 17.9% arc misreads as "failing" on a
  // healthy +428R book; the rising Toplam-R spark carries the real story.
  const renderKpiHero = () => {
    let winRate, totalR, pf, exp, totalTrades, closedTrades, cum, hist;
    let tp1Agg = null;   // scale-out live: { count, sumR } of TP1-reached trades (set in the live branch)
    if (mode === 'backtest') {
      // Derive everything from the SAME filtered, in-view set as the spark/histogram,
      // so headline + curve + bins stay consistent and react to symbol/date filters.
      if (!filteredSignals.length) return null;
      const closedList = filteredSignals.filter((x) => x.status === 'TP' || x.status === 'SL');
      const closedR = closedList.map((x) => (Number.isFinite(x.pnlR) ? x.pnlR : 0));
      const sumPos = closedR.reduce((a, r) => a + (r > 0 ? r : 0), 0);
      const sumNeg = closedR.reduce((a, r) => a + (r < 0 ? r : 0), 0);
      const wins = closedList.filter((x) => x.status === 'TP').length;
      closedTrades = closedList.length;
      totalTrades = filteredSignals.length;
      winRate = closedTrades ? (wins / closedTrades) * 100 : 0;
      totalR = closedR.reduce((a, r) => a + r, 0);
      exp = closedTrades ? totalR / closedTrades : 0;
      pf = sumNeg !== 0 ? sumPos / Math.abs(sumNeg) : null;
      cum = downsample(cumulativeR(filteredSignals, calculatePnL), 80);
      hist = rHistogram(filteredSignals.map((x) => x.pnlR));
    } else {
      if (!filteredSignals.length) return null;
      const c = summarizeLiveCounts(filteredSignals);
      if (isSO) tp1Agg = summarizeTp1(filteredSignals);   // TP1-reached count + summed live R
      const denom = c.tp + c.sl;
      winRate = denom ? (c.tp / denom) * 100 : 0;
      totalR = c.rScore;
      pf = null;
      exp = denom ? c.rScore / denom : 0;
      totalTrades = filteredSignals.length;
      closedTrades = denom;
      const asc = [...filteredSignals].sort((a, b) => a.dateObj - b.dateObj);
      const rs = asc.map((sig) => liveOutcomeR(sig, liveStatuses[sig.id]?.status, halfFor(sig), isSO, soCapR, soConservative, soBookFrac));
      let cc = 0;
      cum = downsample(rs.map((r) => (cc += r)), 80);
      hist = rHistogram(rs);
    }
    const histMax = Math.max(1, ...hist);
    const HIST_LABELS = ['<0', '0-1', '1-2', '2-4', '4+'];

    return (
      <div className="kpi-hero">
        <div className="kpi-cell">
          <div className="kpi-cell__label">{t('Win Rate')}</div>
          <div className="kpi-cell__value">{winRate.toFixed(1)}%</div>
          <div className="kpi-cell__sub">{closedTrades} {t('kapanan')}</div>
        </div>
        <div className="kpi-cell kpi-cell--wide">
          <div className="kpi-cell__label">{t('Toplam R')}</div>
          <div className={`kpi-cell__value ${totalR >= 0 ? 'win' : 'loss'}`}>
            {totalR >= 0 ? '+' : ''}{totalR.toFixed(1)}R
          </div>
          <div className="kpi-spark">
            {cum.length >= 2 && <Sparkline values={cum} width={120} height={22} variant="area" />}
          </div>
        </div>
        {pf != null && (
          <div className="kpi-cell">
            <div className="kpi-cell__label">{t('Profit Factor')}</div>
            <div className="kpi-cell__value">{Number.isFinite(pf) ? pf.toFixed(2) : '--'}</div>
            <div className="kpi-cell__sub">
              {pf >= 1.3 ? <span className="win">{t('sağlıklı')}</span>
                : pf >= 1 ? t('pozitif') : <span className="loss">{t('negatif')}</span>}
            </div>
          </div>
        )}
        <div className="kpi-cell">
          <div className="kpi-cell__label">{t('Beklenti')}</div>
          <div className={`kpi-cell__value ${exp >= 0 ? 'win' : 'loss'}`}>
            {exp >= 0 ? '+' : ''}{exp.toFixed(2)}R
          </div>
          <div className="kpi-cell__sub">{t('işlem başına')}</div>
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell__label">{t('İşlem')}</div>
          <div className="kpi-cell__value">{totalTrades}</div>
          <div className="kpi-cell__sub">{mode === 'backtest' ? t('sinyal') : t('canlı')}</div>
        </div>
        {tp1Agg && (
          <div className="kpi-cell">
            <div className="kpi-cell__label">{t('TP1 Gelen')}</div>
            <div className="kpi-cell__value">{tp1Agg.count}</div>
            <div className={`kpi-cell__sub ${tp1Agg.sumR >= 0 ? 'win' : 'loss'}`}>
              {t('toplam')} {tp1Agg.sumR >= 0 ? '+' : ''}{tp1Agg.sumR.toFixed(2)}R
            </div>
          </div>
        )}
        <div className="kpi-cell kpi-cell--hist">
          <div className="kpi-cell__label">{t('R Dağılımı')}</div>
          <div className="r-hist">
            {hist.map((cnt, i) => (
              <div key={i} className="r-hist__col" title={`${HIST_LABELS[i]}R: ${cnt}`}>
                {cnt > 0 && (
                  <div className={`r-hist__bar ${i === 0 ? 'r-hist__bar--loss' : 'r-hist__bar--win'}`}
                       style={{ height: `${(cnt / histMax) * 100}%` }} />
                )}
              </div>
            ))}
          </div>
          <div className="r-hist__axis">
            {HIST_LABELS.map((l) => <span key={l}>{l}</span>)}
          </div>
        </div>
      </div>
    );
  };

  // MIDAS-only: which intraday SESSIONS (UTC) the strategy takes trades in + the live distribution
  // of the loaded trades. Mirrors the strategy filter exactly (London 07-13 UTC skipped).
  const MIDAS_SESSIONS = [
    { key: 'asia',    label: 'Asya',            range: '22:00–07:00', on: true,  test: (h) => h >= 22 || h < 7 },
    { key: 'london',  label: 'Londra (açılış-öncesi)', range: '07:00–13:00', on: false, test: (h) => h >= 7 && h < 13 },
    { key: 'overlap', label: 'Londra–NY Overlap', range: '13:00–17:00', on: true,  test: (h) => h >= 13 && h < 17 },
    { key: 'ny',      label: 'NY öğleden sonra', range: '17:00–21:00', on: true,  test: (h) => h >= 17 && h < 21 },
  ];
  const renderMidasSessions = () => {
    if (!isTrailing) return null;
    const agg = {};
    filteredSignals.forEach((s) => {
      const h = new Date(s.dateObj).getUTCHours();
      const sess = MIDAS_SESSIONS.find((x) => x.test(h));
      if (!sess) return;
      const r = Number.isFinite(s.pnlR) ? s.pnlR : 0;
      agg[sess.key] = agg[sess.key] || { n: 0, R: 0 };
      agg[sess.key].n += 1; agg[sess.key].R += r;
    });
    return (
      <div className="session-card">
        <div className="session-card__head">
          <span className="session-card__title">🕐 {t('İşlem Seansları (UTC)')}</span>
          <span className="session-card__note">{t('Londra açılış-öncesi (07-13 UTC) atlanır · Cuma 16:00 ET düz · hafta sonu pozisyon yok')}</span>
        </div>
        <div className="session-card__grid">
          {MIDAS_SESSIONS.map((s) => {
            const a = agg[s.key] || { n: 0, R: 0 };
            return (
              <div key={s.key} className={`session-pill ${s.on ? 'session-pill--on' : 'session-pill--off'}`}>
                <div className="session-pill__name">{s.on ? '✅' : '⛔'} {s.label}</div>
                <div className="session-pill__range">{s.range} UTC</div>
                <div className="session-pill__stat">
                  {s.on
                    ? <>{a.n} {t('işlem')} · <b className={a.R >= 0 ? 'win' : 'loss'}>{a.R >= 0 ? '+' : ''}{a.R.toFixed(1)}R</b></>
                    : <span className="loss">{t('alınmaz')}</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // Per-period R-bar (scaled to the level's max |R|) + a downsampled cumulative
  // spark, so the Years→Months→Days drill is instantly comparable at a glance.
  const drillExtra = (bucket, maxAbs) => (
    <>
      <div className="drill-rbar">
        <div
          className="drill-rbar__fill"
          style={{
            width: `${Math.min(100, (Math.abs(bucket.totalR) / maxAbs) * 100)}%`,
            background: bucket.totalR >= 0 ? 'var(--win)' : 'var(--loss)',
          }}
        />
      </div>
      {bucket.list.length >= 2 && (
        <Sparkline
          className="drill-spark"
          values={downsample(cumulativeR(bucket.list, calculatePnL), 60)}
          width={150}
          height={20}
          variant="area"
        />
      )}
    </>
  );

  const renderTradeCards = (trades) => (
    <div className="trade-grid">
      {trades.filter(matchesStatus).map((sig) => {
        const pnl = calculatePnL(sig);
        const isNoFill = sig.status === 'NOFILL';   // entry never filled → 0R, no trade taken
        const liveStatus = mode === 'live' ? liveStatuses[sig.id]?.status : '';
        const liveLastPrice = mode === 'live' ? liveStatuses[sig.id]?.lastPrice : null;
        const liveMeta = resolveLiveMeta(liveStatus);

        const pnlClass = isNoFill
          ? 'nofill'
          : (mode === 'live'
            ? liveMeta.cls
            : (pnl > 0 ? 'win' : (pnl < 0 ? 'loss' : 'waiting')));

        const effDate = effectiveSignalTime(sig) || sig.dateObj;
        const timeLabel = effDate.toLocaleTimeString(locale, { timeZone: 'UTC', hour: '2-digit', minute: '2-digit' }) + ' UTC';
        // Realistic +0.5R entry for the ·0.5R streams in LIVE (backtest rows already store it).
        // TP/SL stay at the signal levels — only the entry moves, so R:R collapses (4 → ~2.33),
        // matching the chart. The breakout/signal price is shown separately on the card.
        const liveConfirm = mode === 'live' && isConfirmStrategy(strategy)
          && Number.isFinite(sig.entry) && Number.isFinite(sig.sl);
        const cardEntry = liveConfirm
          ? (sig.dir === 'LONG' ? sig.entry + 0.5 * Math.abs(sig.entry - sig.sl)
                                : sig.entry - 0.5 * Math.abs(sig.entry - sig.sl))
          : sig.entry;
        const rr = computeRR(sig, cardEntry);
        const targetPct = pctDist(cardEntry, sig.tp);
        const riskPct = pctDist(cardEntry, sig.sl);

        return (
          <div
            key={sig.id}
            className={`trade-card trade-card--${sig.dir === 'LONG' ? 'long' : 'short'}${isNoFill ? ' trade-card--nofill' : ''}`}
            onClick={() => {
              setChartView('journal');
              setActiveSignal(sig);
            }}
          >
            <div className="intel-head">
              <span className="symbol-box">{sig.symbol}</span>
              <span className={`dir-badge ${sig.dir.toLowerCase()}`}>
                <span className="dir-arrow" aria-hidden="true">{sig.dir === 'LONG' ? '↗' : '↘'}</span>
                {sig.dir}
              </span>
              <span className="time-detail">
                {timeLabel}
                {mode === 'live' && (
                  <span className="time-ago"> · {timeAgo(effDate, t)}</span>
                )}
              </span>
              {rr != null && !isTrailing && (
                <span className="rr-pill" title={`Risk-Reward · 1:${rr.toFixed(2)}`}>1:{rr.toFixed(2)}</span>
              )}
            </div>

            <div className="intel-exec">
              <div className="trade-body intel-exec__grid">
              <div className="trade-metric">
                <span className="metric-label">{t('Durum')}</span>
                {mode === 'live' ? (
                  (() => {
                    const sd = liveStatusDisplay(liveStatus);
                    return (
                      <span className={`status-text ${sd.cls}`}>
                        <span className={`status-dot ${sd.cls}`}>{sd.icon}</span>
                        {t(sd.label)}
                      </span>
                    );
                  })()
                ) : (
                  <span className={`status-text ${pnlClass}`}>{isNoFill ? t('İptal') : sig.status}</span>
                )}
              </div>
              <div className="trade-metric">
                <span className="metric-label">{t('P/L')}</span>
                {mode === 'live' ? (
                  liveMeta.label === 'AKTIF' ? (
                    <span className="pnl-text live-pnl-stack">
                      <span className="live-price">{formatLivePrice(liveLastPrice)}</span>
                      <span className={formatLiveDelta(sig, liveLastPrice, cardEntry).startsWith('-') ? 'loss' : 'win'}>
                        {formatLiveDelta(sig, liveLastPrice, cardEntry)}
                      </span>
                    </span>
                  ) : (
                    <span className={`pnl-text ${getLiveRLabel(sig, liveStatus, liveLastPrice).cls}`}>
                      {getLiveRLabel(sig, liveStatus, liveLastPrice).label}
                    </span>
                  )
                ) : (
                  <span className={`pnl-text ${pnlClass}`}>
                    {isNoFill ? '0R' : (pnl !== 0 ? formatBacktestPnl(sig, pnl) : '--')}
                  </span>
                )}
              </div>
              <div className="trade-metric">
                <span className="metric-label">{t('Entry')}{liveConfirm ? ' ·0.5R' : ''}</span>
                <span className="metric-value">
                  <CopyVal value={cardEntry} title={t('Kopyala')}>{formatPrice(cardEntry)}</CopyVal>
                  {liveConfirm && (
                    <span className="intel-pct" style={{ color: '#848E9C', fontWeight: 400 }}> · {t('Sinyal')} {formatPrice(sig.entry)}</span>
                  )}
                </span>
              </div>
              {isTrailing ? (
              <div className="trade-metric intel-exec__tpsl">
                <span className="metric-label">{t('Çıkış')}</span>
                <span className="metric-value">
                  {Number.isFinite(sig.exitPrice)
                    ? <CopyVal value={sig.exitPrice} title={t('Kopyala')}>{formatPrice(sig.exitPrice)}</CopyVal>
                    : '--'}
                </span>
              </div>
              ) : (
              <div className="trade-metric intel-exec__tpsl">
                <span className="metric-label">{t('Hedef')} / {t('Risk')}</span>
                <span className="metric-value">
                  <CopyVal value={sig.tp} className="win" title={t('Kopyala')}>{formatPrice(sig.tp)}</CopyVal>
                  {targetPct != null && <span className="intel-pct win"> {targetPct >= 0 ? '+' : ''}{targetPct.toFixed(2)}%</span>}
                  <span className="intel-sep"> · </span>
                  <CopyVal value={sig.sl} className="loss" title={t('Kopyala')}>{formatPrice(sig.sl)}</CopyVal>
                  {riskPct != null && <span className="intel-pct loss"> {riskPct.toFixed(2)}%</span>}
                </span>
              </div>
              )}
              </div>

              {(() => {
                if (isTrailing) return null;   // no fixed risk/reward to chart for a trailing exit
                const rk = Math.abs(riskPct ?? 0);
                const rw = Math.abs(targetPct ?? 0);
                if (!(rk > 0 && rw > 0)) return null;
                const riskW = (rk / (rk + rw)) * 100;
                let nowLeft = null;
                if (mode === 'live' && liveMeta.label === 'AKTIF'
                    && typeof liveLastPrice === 'number' && sig.tp !== sig.sl) {
                  const frac = sig.dir === 'LONG'
                    ? (liveLastPrice - sig.sl) / (sig.tp - sig.sl)
                    : (sig.sl - liveLastPrice) / (sig.sl - sig.tp);
                  nowLeft = Math.max(0, Math.min(1, frac)) * 100;
                }
                return (
                  <div className="rr-bar" title={t('Risk {risk}% · Ödül {reward}%', { risk: rk.toFixed(2), reward: rw.toFixed(2) })}>
                    <div className="rr-bar__track">
                      <div className="rr-bar__risk" style={{ width: `${riskW}%` }} />
                      <div className="rr-bar__reward" style={{ width: `${100 - riskW}%` }} />
                      <div className="rr-bar__entry" style={{ left: `${riskW}%` }} />
                      {nowLeft != null && (
                        <div
                          className={`rr-bar__now rr-bar__now--${formatLiveDelta(sig, liveLastPrice).startsWith('-') ? 'down' : 'up'}`}
                          style={{ left: `${nowLeft}%` }}
                        />
                      )}
                    </div>
                  </div>
                );
              })()}
            </div>

            <div className="trade-foot">
              {mode === 'live' ? (
                (() => {
                  const sd = liveStatusDisplay(liveStatus);
                  return (
                    <div className={`chip ${sd.cls}`}>
                      <span className={`status-dot ${sd.cls}`}>{sd.icon}</span>
                      {t(sd.label)}
                    </div>
                  );
                })()
              ) : (
                <div className={`chip ${pnlClass}`}>
                  {isNoFill ? t('İptal') : (pnlClass === 'waiting' ? t('BEKLEMEDE') : (pnl > 0 ? 'TP' : 'SL'))}
                </div>
              )}
            </div>

            <button
              className="live-graph-btn"
              onClick={(e) => {
                e.stopPropagation();
                setChartView('tv');
                setActiveSignal(sig);
              }}
            >
              Live <span className="live-graph-dot">•</span>
            </button>
          </div>
        );
      })}
    </div>
  );

  const yearsMaxR = Math.max(1, ...yearBuckets.map((b) => Math.abs(b.totalR)));
  const monthsMaxR = Math.max(1, ...monthBuckets.map((b) => Math.abs(b.totalR)));
  const daysMaxR = Math.max(1, ...dayBuckets.map((b) => Math.abs(b.totalR)));

  if (mode === 'backtest') {
    if (!isLoaded) {
      return (
        <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
          {renderError()}
          {renderSkeleton()}
        </div>
      );
    }
    return (
      <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
        <div className="backtest-flow">
          {renderError()}
          <StrategyIntro />
          {renderKpiHero()}
          <div className="drill-header">
            <div className="drill-path">
              {!selectedYear && t('Yıllar')}
              {selectedYear && !selectedMonth && `${selectedYear} / ${t('Aylar')}`}
              {selectedYear && selectedMonth && `${selectedYear} / ${parseIsoDate(`${selectedMonth}-01`).toLocaleDateString(locale, { timeZone: 'UTC', month: 'long' })} / ${t('Günler')}`}
            </div>
            <div className="drill-actions">
              {selectedMonth && (
                <button className="drill-back-btn" onClick={() => { setSelectedMonth(''); setSelectedDay(''); }}>
                  {t('Aylara Dön')}
                </button>
              )}
              {selectedYear && !selectedMonth && (
                <button className="drill-back-btn" onClick={() => { setSelectedYear(null); setSelectedMonth(''); setSelectedDay(''); }}>
                  {t('Yıllara Dön')}
                </button>
              )}
            </div>
          </div>

          {!selectedYear && (
            <div className="drill-grid years">
              {yearBuckets.map((y) => (
                <button key={y.year} className="drill-card" onClick={() => setSelectedYear(y.year)}>
                  <div className="drill-title">{y.year}</div>
                  <div className="drill-meta">{y.count} {t('işlem')}</div>
                  <div className="drill-meta">TP/SL: <span className="win">{y.tp}</span>/<span className="loss">{y.sl}</span></div>
                  <div className={`drill-r ${y.totalR >= 0 ? 'win' : 'loss'}`}>{y.totalR >= 0 ? '+' : ''}{y.totalR.toFixed(2)}R</div>
                  {drillExtra(y, yearsMaxR)}
                </button>
              ))}
            </div>
          )}

          {selectedYear && !selectedMonth && (
            <div className="drill-grid months">
              {monthBuckets.map((m) => (
                <button key={m.monthKey} className="drill-card" onClick={() => setSelectedMonth(m.monthKey)}>
                  <div className="drill-title">{m.label}</div>
                  <div className="drill-meta">{m.count} {t('işlem')}</div>
                  <div className="drill-meta">TP/SL: <span className="win">{m.tp}</span>/<span className="loss">{m.sl}</span></div>
                  <div className={`drill-r ${m.totalR >= 0 ? 'win' : 'loss'}`}>{m.totalR >= 0 ? '+' : ''}{m.totalR.toFixed(2)}R</div>
                  {drillExtra(m, monthsMaxR)}
                </button>
              ))}
            </div>
          )}

          {selectedYear && selectedMonth && (
            <>
              <div className="drill-grid days">
                {dayBuckets.map((d) => (
                  <button
                    key={d.dayKey}
                    className={`drill-card ${selectedDay === d.dayKey ? 'active' : ''}`}
                    onClick={() => setSelectedDay(d.dayKey)}
                  >
                    <div className="drill-title">{d.label}</div>
                    <div className="drill-meta">{d.count} {t('işlem')}</div>
                    <div className="drill-meta">TP/SL: <span className="win">{d.tp}</span>/<span className="loss">{d.sl}</span></div>
                    <div className={`drill-r ${d.totalR >= 0 ? 'win' : 'loss'}`}>{d.totalR >= 0 ? '+' : ''}{d.totalR.toFixed(2)}R</div>
                    {drillExtra(d, daysMaxR)}
                  </button>
                ))}
              </div>

              {selectedDayTrades.some(matchesStatus) && (() => {
                const dayCounts = summarizeBacktestCounts(selectedDayTrades);
                return (
                  <div className="day-notebook">
                    <div className="day-header">
                      <div className="day-title">{selectedDayLabel}</div>
                      <div className="day-summary">
                        <span>{selectedDayTrades.length} {t('işlem')}</span>
                        <WinLossBar tp={dayCounts.tp} sl={dayCounts.sl} />
                        <span className="tp-sl-ratio">
                          {t('Toplam R')}:{' '}
                          <span className={getTotalR(selectedDayTrades) >= 0 ? 'win' : 'loss'}>
                            {getTotalR(selectedDayTrades) >= 0 ? '+' : ''}{getTotalR(selectedDayTrades).toFixed(2)}
                          </span>
                        </span>
                      </div>
                    </div>
                    {renderTradeCards(selectedDayTrades)}
                  </div>
                );
              })()}
            </>
          )}
        </div>
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
        {renderError()}
        {renderSkeleton()}
      </div>
    );
  }

  return (
    <div id="dashboard" className="visible" style={{ opacity: 1, display: 'block' }}>
      {renderError()}
      <StrategyIntro />
      {renderKpiHero()}
      {renderMidasSessions()}
      {isTrailing && mode === 'live' && (
        <div style={{ height: 560, marginBottom: 16, border: '1px solid #1E2329', borderRadius: 10, overflow: 'hidden' }}>
          <MidasLiveChart />
        </div>
      )}
      {filteredSignals.length === 0 && (
        <div className="dash-empty">
          <PusuLogo size={46} className="dash-empty__logo" animated />
          <div className="dash-empty__title">{t('Sinyal yok.')}</div>
          <div className="dash-empty__sub">{t('Motor bir likidite tuzağı yakaladığında sinyal burada belirecek.')}</div>
        </div>
      )}
      {Object.keys(groupedLive).map((dateKey) => {
        const trades = groupedLive[dateKey];
        if (!trades.some(matchesStatus)) return null;
        const counts = summarizeLiveCounts(trades);

        return (
          <div key={dateKey} className="day-notebook">
            <div className="day-header">
              <div className="day-title">{dateKey}</div>
              <div className="day-summary">
                <span>{trades.length} {t('işlem')}</span>
                <WinLossBar tp={counts.tp} sl={counts.sl} />
                <span className="tp-sl-ratio">
                  TP/SL: {counts.tp}/{counts.sl} • R:{' '}
                  <span className={counts.rScore >= 0 ? 'win' : 'loss'}>
                    {counts.rScore >= 0 ? '+' : ''}{counts.rScore.toFixed(2)}
                  </span>
                </span>
              </div>
            </div>
            {renderTradeCards(trades)}
          </div>
        );
      })}
    </div>
  );
};

export default Dashboard;
