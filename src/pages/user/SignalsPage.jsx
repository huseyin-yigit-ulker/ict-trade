import { useState } from 'react';
import { useTradeContext } from '../../context/TradeContext';
import { useLang } from '../../context/LanguageContext';
import { LIVE_STREAM_KEYS, codenameFor } from '../../utils/streamMask';
import {
  scaleOutLiveR, isScaleOutStrategy, soCapFromStrategy, isConfirmStrategy, soBookFromStrategy,
} from '../../utils/liveR';
import SignalCard from '../../components/user/SignalCard';
import PusuLogo from '../../components/PusuLogo';

// Sinyaller — merkezî sinyal akışı, kod adlı. Veri tesisatı %100 TradeContext:
// akış çipi setView(key,'live') çağırır; fetch/poll/liveStatuses motoru orada.
// Kart tıklanınca setActiveSignal → UserShell'deki global ChartModal açılır.

const TRAILING = new Set(['midas', 'talos', 'talos_ichi']);

// signal_time = bar OPEN; sinyal bar CLOSE'da doğar — etiketler efektif anı gösterir.
const intervalMs = (tf) => {
  const m = String(tf || '1h').match(/^(\d+)([smhd])$/i);
  if (!m) return 3_600_000;
  const u = { s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000 };
  return Number(m[1]) * (u[m[2].toLowerCase()] || 0);
};
const effTimeOf = (sig) => new Date(sig.dateObj.getTime() + intervalMs(sig.ltfTimeframe));

const STATUS_CHIPS = [
  { key: 'all', label: 'Tümü' },
  { key: 'active', label: 'Aktif' },
  { key: 'tp', label: 'TP' },
  { key: 'sl', label: 'SL' },
  { key: 'cancelled', label: 'İptal' },
];

export default function SignalsPage() {
  const {
    filteredSignals, liveStatuses, setActiveSignal,
    strategy, setView, isLoaded, liveError,
  } = useTradeContext();
  const { t, locale } = useLang();
  const [statusFilter, setStatusFilter] = useState('all');
  // Gün etiketleri için sabit "şimdi" — render-purity (mount başına bir kez).
  const [nowTs] = useState(() => Date.now());
  const trailing = TRAILING.has(strategy);

  // Dashboard.statusOf'un canlı-mod eşlemesi (backtest bu sayfada yok).
  const statusOf = (sig) => {
    const s = liveStatuses[sig.id]?.status || '';
    if (s === 'TP Oldu' || s === 'BE Oldu') return 'tp';
    if (s === 'SL Oldu' || s === 'TP/SL Aynı Mum') return 'sl';
    if (s.startsWith('İptal')) return 'cancelled';
    if (s.startsWith('İşlem Aktif')) return 'active';
    return 'open';
  };

  const shown = filteredSignals.filter((sig) => statusFilter === 'all' || statusOf(sig) === statusFilter);

  // ── Son 7 gün istatistikleri (statusFilter'dan bağımsız — akışın haftalık karnesi) ──
  // R modeli Dashboard ile aynı: scale-out akışta scaleOutLiveR (statü-bazlı, ücret dahil);
  // iz-süren akışlarda (SIRIUS/MENKAR) nightly sync'in çözdüğü sig.pnlR kullanılır.
  const isSO = isScaleOutStrategy(strategy);
  const soCapR = soCapFromStrategy(strategy);
  const soConservative = isConfirmStrategy(strategy);
  const soBookFrac = soBookFromStrategy(strategy);
  const outcomeR = (sig, st) => {
    if (trailing) return Number.isFinite(sig.pnlR) ? sig.pnlR : null;
    if (!isSO) return null;
    const r = scaleOutLiveR(sig.entry, sig.sl, liveStatuses[sig.id]?.status, soCapR, soConservative, soBookFrac);
    return r == null ? (st === 'sl' ? -1 : null) : r;
  };
  const week = { r: 0, rKnown: false, tp: 0, sl: 0, active: 0, total: 0 };
  const weekStartTs = nowTs - 7 * 86_400_000;
  for (const sig of filteredSignals) {
    if (effTimeOf(sig).getTime() < weekStartTs) continue;
    const st = statusOf(sig);
    week.total += 1;
    if (st === 'tp') week.tp += 1;
    else if (st === 'sl') week.sl += 1;
    else if (st === 'active') week.active += 1;
    if (st === 'tp' || st === 'sl') {
      const r = outcomeR(sig, st);
      if (r != null) { week.r += r; week.rKnown = true; }
    }
  }
  const wr = week.tp + week.sl > 0 ? Math.round((week.tp / (week.tp + week.sl)) * 100) : null;

  // Gün gruplama — "Bugün / Dün / 9 Temmuz Cuma" (efektif sinyal zamanına göre).
  // Liste küçük (son ~2 günün sinyalleri) — memo gerektirmez.
  const fmt = new Intl.DateTimeFormat(locale || 'tr-TR', { day: 'numeric', month: 'long', weekday: 'long' });
  const dayKey = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  const today = dayKey(new Date(nowTs));
  const yest = dayKey(new Date(nowTs - 86_400_000));
  const groupMap = new Map();
  for (const sig of shown) {
    const eff = effTimeOf(sig);
    const k = dayKey(eff);
    if (!groupMap.has(k)) {
      const label = k === today ? t('Bugün') : k === yest ? t('Dün') : fmt.format(eff);
      groupMap.set(k, { label, items: [] });
    }
    groupMap.get(k).items.push({ sig, eff });
  }
  const groups = [...groupMap.values()];

  return (
    <div className="ush-signals">
      {/* Akış seçimi — kod adları (gizlilik sınırı: ham stream anahtarı asla basılmaz) */}
      <div className="ush-filterrow">
        {LIVE_STREAM_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            className={`ush-filter ush-filter--stream${strategy === key ? ' is-active' : ''}`}
            onClick={() => setView(key, 'live')}
          >
            {codenameFor(key)}
          </button>
        ))}
      </div>
      <div className="ush-filterrow ush-filterrow--status">
        {STATUS_CHIPS.map((c) => (
          <button
            key={c.key}
            type="button"
            className={`ush-filter${statusFilter === c.key ? ' is-active' : ''}`}
            onClick={() => setStatusFilter(c.key)}
          >
            {t(c.label)}
          </button>
        ))}
      </div>

      {/* Haftalık karne — Binance tarzı kompakt istatistik şeridi */}
      {isLoaded && week.total > 0 && (
        <div className="ush-card ush-tradesum ush-weekstats">
          <div>
            <span>{t('Son 7 gün')} · R</span>
            <b className={`mono ${!week.rKnown ? 'dim' : week.r >= 0 ? 'pos' : 'neg'}`}>
              {week.rKnown ? `${week.r >= 0 ? '+' : ''}${week.r.toFixed(2)}R` : '—'}
            </b>
          </div>
          <div>
            <span>{t('Kazanma')}</span>
            <b className={`mono ${wr == null ? 'dim' : wr >= 50 ? 'pos' : 'neg'}`}>{wr == null ? '—' : `%${wr}`}</b>
          </div>
          <div><span>TP / SL</span><b className="mono">{week.tp} / {week.sl}</b></div>
          <div><span>{t('Aktif')}</span><b className="mono">{week.active}</b></div>
        </div>
      )}

      {liveError && <div className="ush-error" role="alert">⚠ {t(liveError)}</div>}

      {!isLoaded ? (
        <div className="ush-cardlist" aria-hidden="true">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="ush-sigcard ush-skeleton">
              <div className="ush-skeleton__line w40" />
              <div className="ush-skeleton__line w70" />
              <div className="ush-skeleton__line w55" />
            </div>
          ))}
        </div>
      ) : groups.length === 0 ? (
        <div className="ush-empty ush-empty--signals">
          <PusuLogo size={44} animated />
          <p>{t('Motor bir likidite tuzağı yakaladığında sinyal burada belirecek.')}</p>
        </div>
      ) : (
        groups.map((g) => (
          <section key={g.label} className="ush-section">
            <div className="ush-section__head ush-section__head--sticky">
              <h2>{g.label}</h2>
              <span className="ush-count">{g.items.length}</span>
            </div>
            <div className="ush-cardlist">
              {g.items.map(({ sig, eff }) => (
                <SignalCard
                  key={sig.id}
                  sig={sig}
                  live={liveStatuses[sig.id]}
                  streamName={codenameFor(strategy)}
                  effTime={eff}
                  trailing={trailing}
                  onClick={() => setActiveSignal(sig)}
                />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
